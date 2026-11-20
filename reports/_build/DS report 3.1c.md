---
title: "Activity 3.1c: Consistency and performance"
subtitle: "Distributed Systems (2026/27) · University of the Basque Country (UPV/EHU)"
author: "Jorge Arévalo, Anne Baquedano, Jon González, and Laura Rodríguez"
date: "19 November 2026"
lang: en-GB
---

::: {.small}
Report weight: 3% of the final grade · Deadline: Tuesday, 24 November 2026
:::

## 1. Baseline: the original passive technique

The original passive replication technique works as follows. The client sends
every request to the primary. For an update, the primary applies it, broadcasts
the new state to all secondaries, waits for **all** their acknowledgements and
then responds to the client. The primary sequences all requests, so the order
property is guaranteed; the acknowledgement barrier guarantees that every
correct secondary has applied the update before the client sees success, which
provides atomicity. The result is a linearizable service.

Two costs motivate the proposals analysed here: the primary is the bottleneck
for every request, including consultations that do not change the state; and
the client observes the latency of the slowest acknowledged secondary.

## 2. Method

Each proposal is analysed with the same four questions: (i) does it preserve
the order property? (ii) does it preserve atomicity? (iii) which consistency
criterion does the service provide? (iv) what happens when a failure occurs?
Each case is illustrated with a chronogram; the violated property is marked
explicitly. In the figures, `W(x=v)` is a write, `R(x)` a read, and the value
returned by the read is shown on the response arrow.

## 3. Proposition 1 — consultations served by secondaries

The colleague proposes that read-only requests go directly to a secondary,
while updates continue to go to the primary. Two alternatives are considered:
(1a) any secondary may serve a client's reads; (1b) the same secondary always
serves the reads of a given client.

### 3.1 Variant 1a — any secondary

**Order.** Reads are requests too. If two reads of the same object are served
by different secondaries, there is no single order for the read/write mix:
S1 may serve a read after applying an update while S2 serves a later read
before applying the same update. The system no longer has one global order;
each secondary only has its own local order.

**Atomicity.** The updates themselves are still atomic: they continue to use
reliable broadcast and the ACK barrier, so every correct secondary eventually
applies them. But a read served by a single secondary is not "handled by all
correct replicas"; read-only operations must therefore be treated separately
when arguing linearizability.

**Consistency criterion.** Linearizability is lost. Figure 1 shows the
counterexample. While the primary is still waiting for S2's acknowledgement,
C2 reads `x` at S1 and obtains the new value `1`. Immediately afterwards, C2
reads `x` at S2 and obtains the old value `0`. The first read ends before the
second one starts, so any legal total order must place the first read before
the second. The first read forces the write to precede it; the second read
forces the write to follow it. There is no such total order, so the execution
is not linearizable. Each secondary is sequentially consistent on its own, but
the service as a whole only provides a weak, convergent (eventual/prefix)
consistency.

![Figure 1. Proposition 1a: a client reads the new value from S1 and then the old value from S2](figures/fig-3.1c-1a.png){width=6.3in}

**Failures.** If a secondary fails, the client simply sends its next read to
another one. The update protocol is unaffected. The consistency anomaly,
however, becomes permanent rather than transient: a client can read a value
from a secondary that has the update, and after that secondary fails read an
older value from another one. The state observed by the client can move
backwards.

### 3.2 Variant 1b — the same secondary for each client

**Order.** Per client, the reads now have a well-defined order: they all come
from the same secondary, which applies updates in the primary's order.
Therefore monotonic reads and read-your-writes hold for that client, provided
the write response implies that all secondaries have applied the update (which
is the case with the ACK barrier). Across clients, however, there is still no
global order: each client follows its own secondary.

**Atomicity.** Unchanged with respect to the original technique: updates keep
the reliable broadcast and the ACK barrier.

**Consistency criterion.** The service provides session guarantees per client,
but not linearizability. Figure 2 shows that the cross-replica anomaly remains:
C1 reads `1` from S1 while C2 reads `0` from S2, and C1's read ends before C2's
starts. Pinning each client to one secondary fixes per-client monotonicity; it
does not fix the global order.

![Figure 2. Proposition 1b: each client is monotonic, but two clients still observe contradictory values](figures/fig-3.1c-1b.png){width=6.3in}

**Failures.** The cost of 1b appears precisely when the pinned secondary fails.
The client must be reassigned to another secondary. Until the new secondary has
caught up, the client can read values older than the ones it had already
observed, which breaks monotonic reads and read-your-writes across the
failover. Reassigning only after the new secondary has applied the missing log
(or validating a version number) avoids the regression but adds latency and
requires tracking the client's last observed version.

### 3.3 Assessment

Variant 1a balances load better but loses per-client monotonicity. Variant 1b
preserves session guarantees at the cost of stickiness, uneven load and a more
complex failure handling. Neither restores linearizability while reads can be
answered by a replica that has not yet applied the latest committed update.
Restoring it requires one of: reads at the primary, a read lease that prevents
the secondary from serving until it has caught up, or a version check that
makes the read wait for the version it needs.

## 4. Proposition 2 — replying before the acknowledgement barrier

The colleague also proposes removing the wait for ACKs to reduce latency. Two
alternatives are considered: (2a) respond to the client before disseminating
the update; (2b) disseminate the update and respond without waiting for the
ACKs.

### 4.1 Variant 2a — respond before disseminating

**Order.** While the primary is alive, updates are still sequenced by the
primary, so the order among updates is preserved. The response, however, is no
longer ordered with the dissemination: a subsequent read served by a secondary
may not see the value that the client has just been told was written.

**Atomicity.** Atomicity is violated. Figure 3 shows the failure: the primary
applies the update locally, responds `OK`, and crashes before sending it to any
secondary. The client has observed a successful write, but no correct replica
has the value; the new primary serves `0`. A request was handled by a replica
but will never be handled by the correct replicas, which is exactly the
negation of atomicity. Durability is also violated: an acknowledged write is
lost.

![Figure 3. Proposition 2a: the primary replies and crashes before disseminating; the acknowledged write disappears](figures/fig-3.1c-2a.png){width=6.3in}

**Failures.** Any crash in the window between the local apply and the end of
the dissemination loses the write. The only safe fixes are to replicate before
replying, or to wait for at least one durable copy (and then the variant is no
longer 2a).

### 4.2 Variant 2b — respond after sending, without waiting for ACKs

**Order.** Preserved: the primary still sequences the updates, and the
per-channel FIFO order keeps the secondaries aligned.

**Atomicity.** Not guaranteed. "Sent" is not "delivered": the quasi-reliable
channels only guarantee delivery if the sender does not fail. Suppose the
primary sends the update to S1 and S2, S1 receives it, the primary responds
`OK`, and then the primary and S1 crash before S2 receives anything. S2 is the
only survivor and is promoted, but it never had the update (Figure 4). The
client saw a success that the new primary cannot reproduce, so atomicity and
durability are violated. Reliable broadcast does not save this case either: it
guarantees all-or-none among the correct processes that participate, but if the
sender crashes before any correct process delivers the message, the message can
be lost.

![Figure 4. Proposition 2b: replying after sending but before ACKs; the only replica that received the update also fails](figures/fig-3.1c-2b.png){width=6.3in}

**Failures.** There is a window between the send and the acknowledgements. A
primary failure inside that window can leave the new primary without an update
that the client already considers committed. The fix is a commit rule: reply
only after a quorum (or all) of the secondaries have persisted the update. Then
the latency improves by at most one RTT — waiting for the fastest secondary
instead of the slowest — while durability is preserved. Waiting for all ACKs,
as in the original technique, is the strongest version of this rule.

## 5. Combining propositions 1 and 2

If reads are served by secondaries **and** the primary replies before the ACK
barrier, the two anomalies compose and become worse (Figure 5). The client
writes, receives `OK`, and immediately reads from a secondary that has not yet
received the update: read-your-writes is violated. A moment later the update
arrives at that secondary and the same client reads the new value, so its
observation jumps from `0` to `1` after having been told that the write
succeeded. If the primary fails before disseminating, the acknowledged value
disappears permanently. The combination is not linearizable even without
failures, and it violates atomicity and durability as soon as a failure occurs.

![Figure 5. Combination of 1 and 2: the client reads an old value after a successful write](figures/fig-3.1c-combined.png){width=6.3in}

The combination could only be made safe by adding mechanisms that reintroduce
the cost the proposals tried to remove: reads at the primary, version-checked
reads that wait for the required update, and a commit rule that waits for
enough acknowledgements before replying.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

## 6. Summary and conclusions

| Variant | Order | Atomicity | Consistency | Behaviour under failures |
|---|---|---|---|---|
| Original | Preserved (primary sequencing) | Preserved (all ACKs) | Linearizable | Election, retry and deduplication needed |
| 1a — any secondary | Not global; local order per replica | Preserved for updates | Weak (convergent); not linearizable | Reads can move backwards |
| 1b — fixed secondary | Per client only | Preserved for updates | Session guarantees; not linearizable | Failover breaks monotonic reads |
| 2a — reply then disseminate | Preserved while alive | Violated | Not linearizable | Acknowledged writes can be lost |
| 2b — send then reply | Preserved | Violated unless a quorum ACKs | Not linearizable | Acknowledged writes can be lost |
| 1 + 2 | Not global | Violated | Broken | Read-your-writes fails; lost updates on failover |

The original passive technique is the only variant that preserves
linearizability. Proposition 1 can be acceptable only if the application
explicitly tolerates stale reads, and then variant 1b is preferable to 1a
because it at least preserves session guarantees. Proposition 2 trades
durability for latency and is not acceptable for a fault-tolerant file service
unless it is strengthened with a quorum commit rule. For the Project we keep
the original technique: primary sequencing, reliable dissemination, a durable
log and a response only after the required acknowledgements.

::: {.small}
Note on group work: the chronograms and the conclusions above are a proposal
to be reviewed and agreed with the rest of the group before submission.
:::

## References

- Lafuente, A., Larrea, M. *Distributed Systems — Course notes*, Topic 3,
  §3.5.2 (consistency criteria) and §3.5.3.1 (passive replication, including
  the relaxed variants).
- Activity statement 3.1c, Part 3, course HTML (P03).
