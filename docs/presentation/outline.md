# Final Presentation Outline

**Duration:** 15 minutes + 5 minutes of questions.

**Speakers:** one block per group member. Demo is integrated, not a separate
long block.

## Block 1 — Problem, objectives, and architecture (5 minutes)

Speaker: Jorge Arévalo Fernández

1. Problem: cloud file service, transparent client, failures, sharing.
2. Project objectives and proof-of-concept scope.
3. Overall architecture: GUI/daemon, TLS client, server cluster, admin.
4. Client path: watcher, durable outbox, startup reconciliation.
5. Key design choice: owned files at the root, shared files under
   `shared/<owner>/<path>`.

Demo: register/login and show a local file reaching the server.

## Block 2 — Replication, election, and failover (5 minutes)

Speaker: Jon Gonzalez Fernandez

1. Passive replication and the primary/secondary roles.
2. Deterministic operations and the durable `(term, index)` log.
3. Reliable broadcast: `RB`, `ACK`, `COMMIT`, and 2/3 quorum.
4. Failure detection, election, terms, fencing, and `PRIM`.
5. Rejoin through snapshots.
6. Client reconnection and reconciliation after failover.

Demo: stop the primary, wait for election, upload through the new primary.

## Block 3 — Sharing, GUI, admin, results, and conclusions (5 minutes)

Speaker: Anne Baquedano Mella / Laura Rodríguez Rodríguez

1. Cross-user shares with `ro`/`rw` ACLs.
2. Notifications: `SUBS`/`UPDT`, conflict copies, revocation, offline sync.
3. Desktop GUI and daemon: tray, autostart, CLI control.
4. HTTPS admin: users, shares, settings, status, step-down.
5. Test results: 171 tests, Docker cluster, failover, notifications.
6. Limitations and pending work.
7. Conclusions and lessons learned.

## Anticipated questions

- Why passive replication instead of active replication?
- What happens without quorum? (`ER12`, no local apply.)
- How are conflicts detected and preserved?
- What happens if the client is offline during a change?
- How is the old primary fenced when it returns?
- Why no TLS fallback?
- What remains for a production service?

## Timing checks

- 0:00–1:00 problem and objectives
- 1:00–5:00 architecture and client
- 5:00–10:00 replication and failover + demo
- 10:00–14:30 sharing, GUI, admin, results, limitations
- 14:30–15:00 conclusions and questions handoff

## Slide file

The Beamer source is `docs/presentation/slides.tex`. Build it with:

```sh
scripts/build_slides.sh
```
