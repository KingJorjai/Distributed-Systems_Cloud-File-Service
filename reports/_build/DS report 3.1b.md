---
title: "Activity 3.1b: How to get consistent replication"
subtitle: "Distributed Systems (2026/27) · University of the Basque Country (UPV/EHU)"
author: "Jorge Arévalo, Anne Baquedano, Jon González, and Laura Rodríguez"
date: "19 November 2026"
lang: en-GB
---

::: {.small}
Report weight: 2% of the final grade · Deadline: Tuesday, 24 November 2026
:::

## 1. Objective and properties to preserve

Activity 3.1a concluded that the cloud file service must behave as a single
linearizable object: every operation must appear to take effect atomically at
some point between its invocation and its response, respecting the real-time
order between operations. In a replicated system, linearizability is obtained
from two sufficient properties (Notes, Topic 3, §3.5.2–3.5.3):

- **Order.** Given two requests on an object in a replicated system, all
  replicas treat these requests in the same order.
- **Atomicity.** Given a request on an object in a replicated system, if a
  replica handles the request, then all the correct replicas handle it sooner
  or later.

This report compares the two classical replication techniques, active and
passive, with respect to (A) the basis of atomicity, (B) the basis of order, and
(C) failure transparency, including the specific failure scenarios requested in
the statement. The implementation of the basic passive technique belongs to the
Project and is therefore out of the scope of this report.

![Figure 1. Active and passive replication: communication structure. Solid arrows carry client requests and updates; dashed green arrows are acknowledgements and responses](figures/fig-3.1b-models.png){width=6.4in}

## 2. Active replication

### 2.1 Operation

The client sends every request to all replicas. Replicas execute the request
concurrently and return a response; the client keeps the first response and
discards the rest, which must be identical. This requires deterministic
replicas and the same initial state.

### 2.2 (A) Basis of atomicity

Atomicity relies on **total order broadcast**. The communication layer
guarantees that every correct replica delivers every request, and that all of
them deliver the requests in the same order (all-or-none). Because
`TO-broadcast/TO-deliver` already satisfies the three reliable-broadcast
properties (validity, agreement and integrity) and adds a total order,
atomicity is structural: it does not depend on the client, on acknowledgements
or on a coordinator. If one replica executes a request, every correct replica
will execute it as well.

### 2.3 (B) Basis of order

The order comes from the **communication support**, not from any replica. If two
correct replicas deliver messages `m1` and `m2`, they do so in the same order.
The price is high: total order broadcast is equivalent to consensus, and
consensus is impossible to solve deterministically in an asynchronous system
with crash failures (FLP). In practice it requires partial synchrony, a leader
or a consensus protocol, with the associated latency and message cost.

The file service illustrates the condition that order imposes on
communication. Suppose two clients concurrently issue
`modification(f, "v1")` and `modification(f, "v2")`. If replica S1 applies
`v1` then `v2` while S2 applies `v2` then `v1`, both replicas end in a different
state, and a later `consultation(f)` returns different contents depending on
which replica answers. Reliable delivery alone is not enough: the channel must
also impose the same delivery order at every replica. This is precisely what
the order property demands, and why active replication needs total order
broadcast instead of plain reliable broadcast.

### 2.4 (C) Failure transparency

Replica failures are transparent to the client as long as a correct quorum
remains. The client sends to all replicas and takes the first response, so it
does not need to know which replica failed. Order and atomicity are preserved
by the broadcast layer, which must remove the failed replica from the group and
transfer state to it when it rejoins. If too many replicas fail and no quorum
exists, the service stops (availability is lost), but safety is not violated.
The client does not manage the failure, which is the main transparency
advantage of this technique.

## 3. Passive replication

### 3.1 Operation

One node acts as **primary** and the rest as **secondaries**. The client sends
every request to the primary. The primary executes the operation, broadcasts
the resulting update to the secondaries, waits for their acknowledgements, and
only then responds to the client.

### 3.2 (A) Basis of atomicity

Atomicity relies on **reliable broadcast plus an acknowledgement barrier**. The
primary disseminates the update with a reliable primitive: either all correct
secondaries eventually deliver it or none does. Before replying, the primary
waits for the ACKs of all correct secondaries, which means that the update has
been applied at every correct replica when the client observes success. Waiting
for all ACKs — and not merely sending the update — is what turns reliable
broadcast into the atomicity required by linearizability.

### 3.3 (B) Basis of order

Order is provided by the **primary**, which is the single sequencer: it receives
all requests, assigns them an order and disseminates the updates in that order.
Secondaries do not reorder updates; they apply them as they arrive from the
primary. Consequently, the communication semantics only needs to be reliable
(and FIFO per primary–secondary channel, or carry sequence numbers), not
totally ordered. This is the fundamental asymmetry with active replication:
order is centralised and therefore cheap in communication cost, but the primary
becomes a bottleneck and a single point of failure for progress.

The same example as above shows the condition imposed on the channel. If the
primary applies `v1` before `v2` but the channel to S2 delivers `v2` before
`v1`, S2 diverges from the primary. The primary orders the requests, but the
channel must preserve that order per sender; a per-channel FIFO guarantee (or a
sequence number checked on delivery) is sufficient and much weaker than total
order broadcast.

### 3.4 (C) Failure transparency

**Secondary failure.** The primary detects it with a timeout, removes the
secondary from the acknowledgement set, and continues serving. The client is
not involved. Membership changes must be consistent, and a secondary that
recovers must receive the missing log or a snapshot and catch up before it is
counted again.

**Primary failure.** It is not transparent by itself. The client receives no
response, times out and must retry; a secondary must be promoted through an
election algorithm, and the client must discover the new primary (through a
name service or a `PRIM`-style query). Transparency therefore requires four
mechanisms: failure detection (heartbeats), election, fencing of the old primary
so that a stale primary cannot continue serving, and exactly-once semantics for
client retries (request identifiers and a cache of `(invocation, response)`
pairs).

## 4. Failure analysis

### 4.1 Failure of a replica in active replication

**(A) Order and atomicity.** They are preserved while a correct quorum exists.
The failed replica stops delivering messages, but total order broadcast
continues to deliver the same sequence to every correct replica. A request that
the failed replica had already delivered is delivered by the others as well, so
atomicity holds.

**(B) Actions.** Detect the failure, remove the replica from the group, and
continue with the remaining quorum. When the replica rejoins, transfer the
state (log plus snapshot) and incorporate it into the group only when it is up
to date. The client is unaffected and does not even need to know which replica
failed.

### 4.2 Failure of a secondary in passive replication

**(A) Order and atomicity.** Order is unaffected, because the primary keeps
sequencing. Atomicity is preserved provided that the primary stops waiting for
the failed secondary and commits with the live set: the failed replica is not
correct, so the definition of atomicity does not require it to apply the
update. If, on the contrary, the primary kept counting a dead secondary as
acknowledged, it could reply without the update being applied at all correct
replicas, and a read served by the recovered secondary would return stale data.

**(B) Actions.** Detect the failure with a heartbeat/timeout, update the
membership, and define the commit rule on the current live set. On recovery,
transfer the log or a snapshot and let the secondary catch up. A subtlety of an
asynchronous system is that a slow secondary is indistinguishable from a failed
one: removing a live but slow secondary preserves safety (it will catch up) but
may reduce the set of replicas that are up to date.

### 4.3 Failure of the primary in passive replication

The notes distinguish three situations:

**(a) The failure occurs outside the interval of a request.** A secondary
detects the absence of heartbeats, starts an election and a new primary is
chosen. No client request is in doubt.

**(b) The failure occurs after receiving the request but before broadcasting
the update.** The update never left the primary. The client times out and
retries against the new primary, which executes the request once. If the old
primary had applied the operation locally but had not disseminated it, the
retry could duplicate the effect; the client request identifier and the
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

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

## 5. Comparison

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

## 6. Conclusions for the cloud file service

Passive replication is the better fit for our service. Updates are much less
frequent than consultations, files are large, and active replication would
require every replica to store every file and to execute every operation
deterministically. Passive replication concentrates the order in the primary and
uses a cheap reliable channel, while still providing linearizability thanks to
the ACK barrier. The price is the failover protocol: election, fencing and
exactly-once retries, which the Project implements with terms, a durable
replication log and request identifiers.

## References

- Lafuente, A., Larrea, M. *Distributed Systems — Course notes*, Topic 3,
  §3.4.2.1 (reliable broadcast), §3.5.2 (consistency criteria), §3.5.3.1
  (passive replication) and §3.5.3.2 (active replication).
- Activity statement 3.1b, Part 3, course HTML (P03).
