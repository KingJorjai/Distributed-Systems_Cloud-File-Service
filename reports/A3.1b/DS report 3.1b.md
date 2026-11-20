---
title: "Activity 3.1b: How to get consistent replication"
author: "Jorge Arévalo, Anne Baquedano, Jon González, and Laura Rodríguez"
---


## Introduction

Activity 3.1a led us to the conclusion that the cloud file service has to
behave as a single linearizable object: every operation must seem to take
effect atomically at some point between its invocation and its response, and
the real-time order between operations has to be respected. When the system is
replicated, linearizability can be obtained from two sufficient properties
(Notes, Topic 3, §3.5.2–3.5.3):

- **Order.** When two requests are issued on an object of a replicated system,
  all replicas have to treat them in the same order.
- **Atomicity.** When a request is issued on an object of a replicated system,
  if one replica handles it, then all the correct replicas have to handle it
  sooner or later.

This report compares the two classical replication techniques, active and
passive, taking into account (A) the basis of atomicity, (B) the basis of
order and (C) failure transparency, including the failure scenarios that the
statement asks for. The implementation of the basic passive technique belongs
to the Project, so it is out of the scope of this report.

![Figure 1. Communication steps in passive and active replication. Passive: request to the primary, update to each secondary, acknowledgement from each secondary, response to the client. Active: request to every replica; the client keeps the first response and discards the rest.](figures/fig-3.1b-models.png){width=5.2in}

## Active replication

**Operation**

The client sends every request to all the replicas. Each replica executes the
request concurrently and returns a response. The client keeps the first
response it receives and discards the rest, which should be identical. For
this to work, the replicas have to be deterministic and start from the same
initial state.

**(A) Basis of atomicity**

Here atomicity relies on **total order broadcast**. The communication layer
guarantees that every correct replica delivers every request, and that all of
them deliver the requests in the same order (all-or-none). Since
`TO-broadcast/TO-deliver` already satisfies the three properties of reliable
broadcast (validity, agreement and integrity) and adds a total order,
atomicity comes from the communication itself: it does not depend on the
client, on acknowledgements or on a coordinator. If one replica executes a
request, every correct replica will execute it too.

**(B) Basis of order**

In this case the order comes from the **communication support**, not from any
replica. If two correct replicas deliver messages `m1` and `m2`, they do it in
the same order. The price is high: total order broadcast is equivalent to
consensus, and consensus cannot be solved deterministically in an asynchronous
system with crash failures (FLP). In practice it needs partial synchrony, a
leader or a consensus protocol, with the latency and message cost that this
implies.

The file service helps to see the condition that order imposes on
communication. Suppose that two clients issue `modification(f, "v1")` and
`modification(f, "v2")` at the same time. If replica S1 applies `v1` and then
`v2`, while S2 applies `v2` and then `v1`, both replicas end in a different
state, and a later `consultation(f)` returns different contents depending on
which replica answers. Reliable delivery is not enough: the channel also has
to impose the same delivery order at every replica. This is exactly what the
order property demands, and the reason why active replication needs total
order broadcast instead of plain reliable broadcast.

**(C) Failure transparency**

Replica failures are transparent to the client as long as a correct quorum
remains. The client sends to all replicas and takes the first response, so it
does not need to know which replica has failed. Order and atomicity are
preserved by the broadcast layer, which has to remove the failed replica from
the group and transfer the state to it when it rejoins. If too many replicas
fail and there is no quorum, the service stops (availability is lost), but
safety is not violated. The client does not manage the failure, and this is
the main transparency advantage of this technique.

## Passive replication

**Operation**

One node acts as **primary** and the rest as **secondaries**. The client sends
every request to the primary. The primary executes the operation, broadcasts
the resulting update to the secondaries, waits for their acknowledgements and
only then responds to the client.

**(A) Basis of atomicity**

Atomicity relies on **reliable broadcast plus an acknowledgement barrier**.
The primary disseminates the update with a reliable primitive: either all
correct secondaries eventually deliver it or none does. Before replying, the
primary waits for the ACKs of all correct secondaries, which means that the
update has been applied at every correct replica when the client observes
success. Waiting for all ACKs, and not only sending the update, is what
turns reliable broadcast into the atomicity that linearizability requires.

**(B) Basis of order**

The order is provided by the **primary**, which acts as a single sequencer: it
receives all requests, assigns them an order and disseminates the updates in
that order. The secondaries do not reorder updates. They apply them as they
arrive from the primary. Therefore the communication semantics only needs to
be reliable (and FIFO per primary–secondary channel, or carry sequence
numbers), not totally ordered. This is the fundamental asymmetry with active
replication: order is centralised, so it is cheap in communication cost, but
the primary becomes a bottleneck and a single point of failure for progress.

The same example as before shows the condition imposed on the channel. If the
primary applies `v1` before `v2`, but the channel to S2 delivers `v2` before
`v1`, then S2 diverges from the primary. The primary orders the requests, but
the channel has to preserve that order for each sender. A per-channel FIFO
guarantee (or a sequence number checked on delivery) is enough, and it is much
weaker than total order broadcast.

**(C) Failure transparency**

**Secondary failure.** The primary detects it with a timeout, removes the
secondary from the acknowledgement set and continues serving. The client is
not involved. Membership changes have to be consistent, and a secondary that
recovers must receive the missing log or a snapshot and catch up before it is
counted again.

**Primary failure.** It is not transparent by itself. The client receives no
response, times out and has to retry. A secondary has to be promoted through
an election algorithm, and the client has to discover the new primary (through
a name service or a `PRIM`-style query). Transparency therefore requires four
mechanisms: failure detection (heartbeats), election, fencing of the old
primary so that a stale primary cannot keep serving, and exactly-once
semantics for client retries (request identifiers and a cache of
`(invocation, response)` pairs).

## Failure analysis

**Failure of a replica in active replication**

**(A) Order and atomicity.** Both are preserved while a correct quorum exists.
The failed replica stops delivering messages, but total order broadcast
continues to deliver the same sequence to every correct replica. A request
that the failed replica had already delivered is delivered by the others as
well, so atomicity holds.

**(B) Actions.** Detect the failure, remove the replica from the group and
continue with the remaining quorum. When the replica rejoins, transfer the
state (log plus snapshot) and incorporate it into the group only when it is up
to date. The client is unaffected and does not even need to know which replica
failed.

**Failure of a secondary in passive replication**

**(A) Order and atomicity.** Order is not affected, because the primary keeps
sequencing. Atomicity is preserved as long as the primary stops waiting for
the failed secondary and commits with the live set: the failed replica is not
correct, so the definition of atomicity does not require it to apply the
update. If, on the contrary, the primary kept counting a dead secondary as
acknowledged, it could reply without the update being applied at all correct
replicas, and a read served by the recovered secondary would return stale
data.

**(B) Actions.** Detect the failure with a heartbeat/timeout, update the
membership and define the commit rule on the current live set. On recovery,
transfer the log or a snapshot and let the secondary catch up. There is a
subtlety in an asynchronous system: a slow secondary cannot be distinguished
from a failed one. Removing a live but slow secondary preserves safety (it
will catch up), but it may reduce the set of replicas that are up to date.

**Failure of the primary in passive replication**

The notes distinguish three situations:

**(a) The failure occurs outside the interval of a request.** A secondary
detects the absence of heartbeats, starts an election and a new primary is
chosen. No client request is in doubt.

**(b) The failure occurs after receiving the request but before broadcasting
the update.** The update never left the primary. The client times out and
retries against the new primary, which executes the request once. If the old
primary had applied the operation locally but had not disseminated it, the
retry could duplicate the effect. The client request identifier and the
per-client response cache are needed to detect and suppress the duplicate.

**(c) The failure occurs after broadcasting the update.** Reliable broadcast
guarantees all-or-none among correct secondaries: either all of them have the
update or none does. The new primary cannot know whether the client received
the response. The client retry may therefore be either a new request or a
reinvocation. Labelling requests with a client order number and storing the
`(invocation, response)` pairs at every node solves the ambiguity: if the
operation is already in the log, the stored response is returned instead of
executing it again.

**Measures.** Heartbeats for detection, election with terms and fencing to
prevent split brain, a durable log so that the new primary inherits all
committed updates, request identifiers and a response cache for exactly-once
retries, and a client that retries with a timeout.

## Comparison

| Criterion | Active replication | Passive replication |
|---|---|---|
| Basis of atomicity | Total order broadcast (all-or-none) | Reliable broadcast + ACK of all correct secondaries |
| Basis of order | Total order broadcast | Primary sequencing; FIFO channels |
| Communication support | Strong (total order, consensus) | Weak (reliable, FIFO) |
| Client interaction | Sends to all replicas; first response wins | Sends only to the primary |
| Determinism | Required at every replica | Not required; state transfer is possible |
| Secondary/replica failure | Transparent while a quorum remains | Transparent; detected by timeout |
| Primary failure | Not applicable (no primary) | Election, fencing, client retry and deduplication |
| Bottleneck | None, but every update is executed everywhere | Primary is a bottleneck and a single point of failure |
| Message cost per update | O(n) plus the consensus overhead | 2n messages (update + ACK), no consensus |

## Conclusions

After comparing both techniques, we consider that passive replication is the
better fit for our service. Updates are much less frequent than consultations,
files are large, and active replication would force every replica to store
every file and to execute every operation deterministically. Passive
replication concentrates the order in the primary and uses a cheap reliable
channel, and it still provides linearizability thanks to the ACK barrier. The
price we pay is the failover protocol: election, fencing and exactly-once
retries, which the Project implements with terms, a durable replication log
and request identifiers.

## References

- Lafuente, A., Larrea, M. *Distributed Systems*, course notes, Topic 3,
  §3.4.2.1 (reliable broadcast), §3.5.2 (consistency criteria), §3.5.3.1
  (passive replication) and §3.5.3.2 (active replication).
- Activity statement 3.1b, Part 3, course HTML (P03).
