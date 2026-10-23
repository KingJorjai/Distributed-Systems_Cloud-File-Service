"""Heartbeats, failure detection, elections, and leader fencing."""

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from replication import PeerConnection, parse_peers


class Role:
    """Cluster roles used by :class:`ClusterNode`."""

    Follower = "follower"
    Candidate = "candidate"
    Leader = "leader"


class ClusterNode:
    """Own the dynamic role, term, heartbeat loop, and election state."""

    def __init__(self, config, store, log, snapshot_lock=None):
        self.config = config
        self.store = store
        self.log = log
        self.snapshot_lock = snapshot_lock or threading.RLock()
        self.peers = parse_peers(config.peers)
        self.quorum = (1 + len(self.peers)) // 2 + 1
        self.location = "{}:{}".format(
            config.host or "localhost", config.port
        )
        self.local_endpoint = (config.host or "localhost", config.port)
        self.client_addresses = {}
        for peer in parse_peers(config.client_addresses):
            self.client_addresses[peer.server_id] = (peer.host, peer.port)
        self._role = Role.Follower
        self.current_leader = None
        self.last_heartbeat = time.monotonic()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._jitter = (
            int(hashlib.sha256(config.server_id.encode("utf-8")).hexdigest(), 16)
            % 1000
        ) / 1000.0

    @property
    def role(self):
        with self._lock:
            return self._role

    def is_leader(self):
        return self.role == Role.Leader

    def set_local_endpoint(self, host, port):
        with self._lock:
            self.local_endpoint = (host, int(port))

    def advertised_endpoint(self):
        return self.client_addresses.get(
            self.config.server_id, self.local_endpoint
        )

    def client_endpoint(self):
        """Return the current primary's client endpoint, if known."""
        with self._lock:
            if self._role == Role.Leader:
                target = self.config.server_id
            else:
                target = self.current_leader
        if target is None:
            return None
        if target == self.config.server_id:
            return self.advertised_endpoint()
        return self.client_addresses.get(target)

    def start(self):
        """Start the cluster monitor and elect the initial primary."""
        initialized = self.log.get_meta("initialized")
        if self.config.role == "primary" and not initialized:
            self.log.set_meta("initialized", "1")
            self._become_leader()
        elif not self.peers and self.config.role == "primary":
            self._become_leader()
        self._thread = threading.Thread(
            target=self._monitor, name="cluster-node", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _hello(self):
        return {
            "id": self.config.server_id,
            "role": self.role,
            "term": self.log.term(),
            "last_term": self.log.last_term(),
            "last_index": self.log.last_index(),
            "commit_index": self.log.commit_index(),
            "token": self.config.cluster_token,
        }

    def _send(self, peer, message):
        connection = PeerConnection(self.config, peer, hello=self._hello())
        try:
            connection.connect()
            connection.send(message)
            return connection.recv()
        except (OSError, EOFError, ValueError):
            return None
        finally:
            connection.close()

    def _broadcast(self, message):
        if not self.peers:
            return []
        with ThreadPoolExecutor(max_workers=len(self.peers)) as executor:
            return list(executor.map(lambda peer: self._send(peer, message), self.peers))

    def _become_leader(self):
        with self._lock:
            self._role = Role.Leader
            self.current_leader = self.config.server_id
            self.last_heartbeat = time.monotonic()
        self.log.set_voted_for(self.config.server_id)
        self._announce()

    def _become_follower(self, leader=None):
        with self._lock:
            self._role = Role.Follower
            self.current_leader = leader
            self.last_heartbeat = time.monotonic()

    def _announce(self):
        host, port = self.advertised_endpoint()
        message = {
            "type": "COORD",
            "term": self.log.term(),
            "leader": self.config.server_id,
            "client_host": host,
            "client_port": port,
        }
        for response in self._broadcast(message):
            if response is not None and int(response.get("term", 0)) > self.log.term():
                self.log.advance_term(int(response["term"]))
                self._become_follower()

    def _monitor(self):
        while not self._stop.is_set():
            role = self.role
            if role == Role.Leader:
                self._heartbeat_round()
                self._stop.wait(self.config.heartbeat_interval)
            elif role == Role.Follower:
                if (
                    time.monotonic() - self.last_heartbeat
                    > self.config.failure_timeout + self._jitter
                ):
                    self._start_election()
                self._stop.wait(min(0.05, self.config.heartbeat_interval))
            else:
                self._stop.wait(
                    self.config.election_timeout + self._jitter
                )
                if self.role == Role.Candidate:
                    self._start_election()

    def _heartbeat_round(self):
        term = self.log.term()
        host, port = self.advertised_endpoint()
        message = {
            "type": "HB",
            "term": term,
            "leader": self.config.server_id,
            "client_host": host,
            "client_port": port,
            "last_index": self.log.last_index(),
            "commit_index": self.log.commit_index(),
        }
        responses = self._broadcast(message)
        acknowledged = 0
        for peer, response in zip(self.peers, responses):
            if response is None:
                continue
            response_term = int(response.get("term", 0))
            if response_term > term:
                self.log.advance_term(response_term)
                self._become_follower()
                return
            if response.get("type") == "HB_OK" and response_term == term:
                acknowledged += 1
                if int(response.get("last_index", 0)) < self.log.commit_index():
                    self._send_snapshot(peer, response_term)
        if 1 + acknowledged < self.quorum:
            self._become_follower()

    def _send_snapshot(self, peer, term):
        with self.snapshot_lock:
            index = int(
                self.log.get_meta("last_applied", self.log.commit_index())
            )
            snapshot = self.store.export_snapshot()
            response = self._send(
                peer,
                {
                    "type": "SNAP",
                    "term": term,
                    "leader": self.config.server_id,
                    "index": index,
                    "snapshot": snapshot,
                },
            )
        if response is not None and int(response.get("term", 0)) > self.log.term():
            self.log.advance_term(int(response["term"]))
            self._become_follower()

    def _start_election(self):
        if not self.peers:
            self._become_leader()
            return
        with self._lock:
            term = self.log.term() + 1
            self.log.advance_term(term)
            self.log.set_voted_for(self.config.server_id)
            self._role = Role.Candidate
            self.current_leader = None
        votes = 1
        message = {
            "type": "VOTE",
            "term": term,
            "candidate": self.config.server_id,
            "last_term": self.log.last_term(),
            "last_index": self.log.last_index(),
        }
        responses = self._broadcast(message)
        for response in responses:
            if response is None:
                continue
            response_term = int(response.get("term", 0))
            if response_term > term:
                self.log.advance_term(response_term)
                self._become_follower()
                return
            if response.get("type") == "VOTE_OK" and response.get("granted"):
                votes += 1
        if votes >= self.quorum:
            self._become_leader()
        else:
            self._become_follower()

    def step_down(self):
        with self._lock:
            if self._role != Role.Leader:
                return False
            self._role = Role.Follower
            self.current_leader = None
            self.last_heartbeat = time.monotonic()
            return True

    def handle_hb(self, message):
        term = int(message["term"])
        leader = message.get("leader")
        with self._lock:
            if term < self.log.term():
                return False
            if term > self.log.term():
                self.log.advance_term(term)
                self._role = Role.Follower
                self.current_leader = None
            if self._role == Role.Leader and leader != self.config.server_id:
                self._role = Role.Follower
            self.current_leader = leader
            if message.get("client_host") is not None:
                self.client_addresses[leader] = (
                    message["client_host"],
                    int(message["client_port"]),
                )
            self.last_heartbeat = time.monotonic()
        return True

    def handle_vote(self, message):
        term = int(message["term"])
        candidate = message.get("candidate")
        candidate_term = int(message.get("last_term", 0))
        candidate_index = int(message.get("last_index", 0))
        with self._lock:
            if term < self.log.term():
                return False
            if term > self.log.term():
                self.log.advance_term(term)
                self._role = Role.Follower
                self.current_leader = None
            if self._role == Role.Leader:
                return False
            voted = self.log.voted_for()
            up_to_date = (candidate_term, candidate_index) >= (
                self.log.last_term(),
                self.log.last_index(),
            )
            if up_to_date and (voted is None or voted == candidate):
                self.log.set_voted_for(candidate)
                self.last_heartbeat = time.monotonic()
                return True
            return False

    def handle_coord(self, message):
        term = int(message["term"])
        leader = message.get("leader")
        with self._lock:
            if term < self.log.term():
                return False
            if term > self.log.term():
                self.log.advance_term(term)
            if leader == self.config.server_id:
                self._role = Role.Leader
            else:
                self._role = Role.Follower
            self.current_leader = leader
            if message.get("client_host") is not None:
                self.client_addresses[leader] = (
                    message["client_host"],
                    int(message["client_port"]),
                )
            self.last_heartbeat = time.monotonic()
        return True

    def observe_term(self, term):
        with self._lock:
            if term > self.log.term():
                self.log.advance_term(term)
                self._role = Role.Follower
                self.current_leader = None

    def observe_leader(self, term, leader):
        with self._lock:
            if term < self.log.term():
                return False
            if term > self.log.term():
                self.log.advance_term(term)
            if leader != self.config.server_id:
                self._role = Role.Follower
            self.current_leader = leader
            self.last_heartbeat = time.monotonic()
        return True
