# PRD compliance and acceptance ledger

**Current direction:** the user stopped validation and switched to demo preparation. The study is cancelled after 153 primary runs; the completion automation is deleted. The full scientific study and final PRD acceptance remain uncompleted. Do not automatically resume them. See `docs/demo-guide.md` for the current deliverable.

The user requested completion of all P0/P1 work and notification after it is done. **Final acceptance is pending the frozen full study and its review.** Implementation presence, regression checks, engineering measurements, and research results are different kinds of evidence.

The approved `prd.md` is unchanged. The current audit closes the previously disclosed metric, streaming, CBS-limit, and validation gaps. It also fixes charging/sensing overlap, message-based CBS preparation, acknowledged-domain reservation/reconciliation, terminal event reasons, and restart finalization. These are concrete changes, not a claim of perfect behavior under arbitrary conditions.

## Functional requirements

| Requirement | Implementation | Acceptance evidence |
|---|---|---|
| FR-001 deterministic generation | Native `generate`, independent keyed random outcomes, materialized maps and hashes | `test_reproducible_generation_and_state_hashes`; exact density/target tests |
| FR-002 custom map validation/editor | Canvas brushes, advanced configuration, overlap/free-cell/dimension/zone checks, explicit disconnected confirmation | `test_validation`, overlap and disconnected-component tests; browser save workflow |
| FR-003 configurable agents | Ordered unique IDs, distinct free starts, initial observations, integer energy | initialization validation, agent snapshots, native invalid-input checks |
| FR-004 separate knowledge | `Knowledge`, restricted `AgentView`/`CoordinatorView`/`PlanningView`, private environment truth | hidden-obstacle isolation regression compares decisions, paths, features and alternatives |
| FR-005 progressive sensing | Graph-radius BFS, walls occlude propagation, timestamped observations | sensing/frontier checks, hidden-map tests, runtime knowledge inspections |
| FR-006 frontier tasks | Known-free unknown boundaries, four-neighbor components, overlap identities | native fixtures; `test_frontier_components_are_known_free_unknown_boundaries_with_stable_ids` |
| FR-007 BFS/A* | FIFO BFS and custom-heap Manhattan A* | native exhaustive small-map comparisons; 480 separate spatial study queries |
| FR-008 independent | Local feasible distance/gain selection, ignores assignments | five-strategy exploration tests, native implementation, headless paired runs |
| FR-009 greedy | Sorted delivered-information pairs; acknowledged tasks are reserved | native greedy/Hungarian distinguishing fixture; acknowledged-domain uniqueness tests |
| FR-010 Hungarian | Rectangular primal-dual matching, idle columns, forbidden entries | exhaustive small matrices, rectangular/forbidden/negative-utility fixtures |
| FR-011 decentralized auction | Bids, epochs, winning leased claims, releases, overlap reconciliation | partition/delay/local-progress regressions and actual message/event exports |
| FR-012 adaptive | All ten quantized factors, hold/threshold rules, offer/ack/commit and peer fallback | full score inspector, delayed-handshake regression, peer-only ablation test; full comparative evaluation pending |
| FR-013 collision prevention | Rolling vertex/edge reservations, priority rotation, simultaneous arbiter and rejection cascades | randomized native invariants and every strategy's run-state checks |
| FR-014 bounded CBS | 5,000 high-level nodes, 100,000 expansions per low-level replan, remaining run horizon; named reservation fallback | native optimum/oracle/budget fixtures, runtime message and outage tests; bounded constraint traces |
| FR-015 communications | Custom event heap, keyed delay/drop/range/partition, byte and message costs/counters | partition tests, by-type counters reconciled with events |
| FR-016 knowledge synchronization | `(observation tick, source ID)` ordering, receipts and bounded anti-entropy reports | out-of-order/equal-version/reopening native fixtures and reconnection tests |
| FR-017 failures | Scheduled/interactive failure, disable/restoration, partitions, postponed obstacles | dynamic/failure/next-tick injection tests and browser disruption workflow |
| FR-018 recovery | Separate suspicion, operational evidence, lease expiry, orphan work, replacement and progress milestones | failure/suspicion and repeated-episode tests, recovery events and censoring exports |
| FR-019 energy/charging | Auditable categorized costs and gains, known-return admission, FIFO station queues and staging | energy conservation, charging replaces sensing/movement, shared-station and exhaustion regressions |
| FR-020 targets | First discovery only through sensing; separate reachable/global flags | hidden-target tests, disconnected chamber test and discovery records |
| FR-021 lifecycle | Serialized tick-boundary start/pause/resume/step/stop/reset/speed, absolute wall-clock scheduling | lifecycle/reset/wake/concurrent-creation tests; measured controls |
| FR-022 fair comparison | Frozen materialized scenarios, common mechanisms and sequential strategies | API comparison hash equality, immutable batch tests, frozen study manifests |
| FR-023 metrics | Coverage, global/map coverage, targets, productivity, distance, energy, bytes/messages, utilization, churn, duplicate claims, recovery, expansions and stage timings | counter/event reconciliation tests and actual CSV/JSON exports |
| FR-024 persistence | SQLite WAL/FKs, transactional terminal checkpoints/events/metrics, explicit restart failure | restart, crash, connection closure, terminal-finalization and saved-reset tests |
| FR-025 replay | Tick-zero/every-50/terminal full checkpoints plus lossless structural deltas | exact engine states across checkpoint boundaries, old-format compatibility, browser seeking/event-time boundary checks |
| FR-026 inspection | Local maps, task/path/energy, revisions, update ages, peer bids/claims, score factors/alternatives, history and rejections | browser inspection and indexed agent-history endpoint tests |
| FR-027 exports | Streamed ZIP for app experiments; raw headless manifests, CSV, result JSON, gzip events/timings, versions and hashes | valid ZIP tests and browser download integrity; headless sample/resume tests |
| FR-028 termination | Distinct native completion/exhaustion/timeout; user stop, engine error and restart reason events | all-unavailable/exhaustion/timeout/crash/lifecycle tests and terminal counters |
| FR-029 headless execution | Sequential CLI and API scheduling, cancellation, partial evidence, strict same-build resume | native batched hash equality; headless gzip sample/resume and cancellation tests |
| FR-030 algorithm explanation | Scores/features, alternatives, bids/claims, expansion counters, bounded CBS constraint traces and fallback reasons | inspector/event log, native CBS trace fixture, planner-study exports |

This table identifies concrete evidence. The complete scientific study is not replaced by the smaller regression suite.

## Non-functional requirements

| Requirements | Evidence / boundary |
|---|---|
| NFR-001 engine performance | Release per-tick distributions; separate default control throughput measurement. Final full-study timing results pending. |
| NFR-002 control responsiveness | Isolated local API measurements include actual command acknowledgments; absolute deadlines prevent cumulative Windows timer drift. Worst-case CBS tick-boundary completion can still be slower than ordinary controls and must be reported honestly. |
| NFR-003 rendering | Canvas uses its own animation clock. Actual default-size browser observations were 30.27 FPS running and 31.33 FPS paused, with approximately 1.6–1.7 ms draw time. This is a reference-machine observation, not a universal guarantee. |
| NFR-004/014 bounded resources | Finite grids, explicit search/message limits, bounded browser buffers and decision/constraint detail; envelope checks include up to 128 × 128 and 16 agents with measured native peak memory. |
| NFR-005 reproducibility | Repeated canonical hashes; batched versus single-tick identical hashes; manifests include exact binary and compiler identity. Wall-clock measurements are excluded. |
| NFR-006/010/011 reliability and reasons | Subprocess failures preserve diagnostics and release the slot; structured HTTP/protocol errors; named rejection, fallback, terminal and restart events. |
| NFR-007 isolation | Agent-facing algorithm interfaces have no environment handle. Scenario evaluation and movement execution retain private truth. |
| NFR-008 numbers | Integer costs, quantized utilities, bounded parameters, derived safe-integer validation, nonnegative energy and ledger reconciliation. |
| NFR-009 maintainability | Native algorithm headers and restricted interfaces, independent backend protocol/store/statistics, typed frontend API/delta handling. |
| NFR-012 durability | Transactional terminal state/events/metrics; restart reconstructs and finalizes the last committed checkpoint/delta chain. |
| NFR-013 portability | CMake C++20 and documented Windows/Linux setup; the actual reference-machine build is Windows/Zig. Linux has not been executed in this Windows-only validation environment. |
| NFR-015 accessibility | Labeled keyboard-operable controls, mobile navigation, visible focus, IDs beside colors; the Canvas editor also supports keyboard input. No formal assistive-technology certification is claimed. |

## Experimental acceptance still pending

The durable pipeline runs **900 primary comparisons** (six families × seeds 100–129 × five strategies), followed by **720 ablation runs** (four independent ablations × six families × thirty seeds). Default study maps are 64 × 64 with four agents and a 10,000-tick bound. It runs sequentially, retains every event and per-tick timing sample, and refuses a resume with a changed build or configuration.

The pipeline ends in `AWAITING_ACCEPTANCE_REVIEW`, not automatically “done.” Review must check counts, manifests/hashes, correctness failures and collisions, scenario outcomes, censored measurements, statistical summaries, and actual performance limitations. Poor adaptive performance is a research outcome; omitted errors or fabricated completion are not acceptable.

The active pipeline is referenced by `data/prd-validation/current.json`. Completion check: `finish-confluence-acceptance`. It must remain quiet during normal progress and notify the user after the final review or when attention is required.
