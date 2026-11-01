# Validation record

This document records checks actually performed. It does not certify flawless behavior, universal completion, or an adaptive-policy advantage.

Final delivered engine: `ac5c99aba6e3f1b620dcbdc41a8f0ee3bc2207da5202a09ee68d033ad353c477`. Final verification passes 52 pytest tests, 16,995 native assertions, and the production TypeScript/Vite build. Browser verification confirms tick-zero replay contains only its two recorded initialization/discovery events; the complete event log follows the selected replay tick. The final preview emits no browser console errors. The temporary viewport override was reset. [Recorded-state screenshot](studio.png).

## Correctness and integration

The release uses the native C++20 engine, FastAPI subprocess orchestration, SQLite persistence, and the built React dashboard. There is no Python solver or browser simulation substitute.

Commands:

```powershell
./.venv/Scripts/python.exe scripts/build.py
./build/confluence_tests.exe
./.venv/Scripts/python.exe -m pytest -q
npm.cmd run build --prefix frontend
```

The C++ suite passes **16,995 assertions**. It checks randomized heap ordering, exhaustive small-map BFS/A* agreement, exhaustive small assignment costs, rectangular Hungarian inputs, randomized movement invariants, CBS conflicts and tiny-instance optimum, global search budgets, map ordering, observed failure/restoration, reproducibility, and a rolling-horizon wall-detour regression.

The Python suite passes **52 tests** covering the actual engine protocol and HTTP/WebSocket integration: all five strategies, hidden-map isolation, delayed handshakes and fallback, partition progress, obstacle changes, failure episodes, energy balance and categorized costs, FIFO charging, resource exhaustion, runtime CBS messages, disconnected target chambers, deterministic hashes, exact checkpoint/delta replay, reset semantics, restart persistence, engine crashes, concurrent creation, interactive fault boundaries, immutable comparisons, event filtering, bounded charts, cancellation behavior, and ZIP evidence. A dependency deprecation warning from Starlette/AnyIO is emitted by the test client; the tests pass.

The production frontend passes TypeScript checking and the Vite build. Browser checks use the real local application and real saved states, including configuration cancellation, run/pause/step/resume, agent knowledge, event history, replay seeking, custom-map validation, comparison tables/curves, and exports. The checked widths are 390, 768, and 1440 pixels. Automated Playwright source is supplied separately; it is not counted as executed browser automation in this report.

## Paired functional batch

The recorded batch in `data/benchmarks/product-validation` contains six families × two held-out seeds (100–101) × five strategies, **60 runs**, on 32 × 32 maps with four agents and a 1,500-tick limit. Warm-up uses development seed zero and is excluded. Each strategy shares the frozen scenario for its seed. Events, metrics CSV, per-run results, manifest, and deterministic bootstrap summaries are retained.

| Family | Completed | Timed out | Engine failures | Committed collisions |
|---|---:|---:|---:|---:|
| Normal | 10 | 0 | 0 | 0 |
| Unknown, radius one | 10 | 0 | 0 | 0 |
| Communication delay/drop/partition | 10 | 0 | 0 | 0 |
| Agent failure | 10 | 0 | 0 | 0 |
| Dynamic obstacle | 10 | 0 | 0 | 0 |
| Resource constraints | 0 | 10 | 0 | 0 |

The resource cases are incomplete outcomes, not correctness failures or omitted observations. Final coverage ranges from 45.92% to 99.51%; the restricted batteries and communication cost matter. A longer run is not assumed to complete. No superiority claim follows from two seeds. The full 900-run study specified in the PRD has **not** been executed.

This batch's engine SHA-256 is `139731886f879879c50d7eea41ad889bc040250abe46f4dcdcc1a05c2e90dcd1`. Subsequent changes add categorized energy-ledger, global-coverage, and bounded alternative-choice trace output. `build/build-info.json` identifies the final delivered binary. Older development batches are retained separately and are not pooled with this one.

A separate default-size smoke study in `data/benchmarks/release-smoke` exercises 64 × 64 maps, four agents, seed 100, and a 3,000-tick bound. All five strategies complete with zero committed collisions. Completion ticks are 728 (independent), 1,752 (greedy), 1,677 (Hungarian), 1,932 (decentralized), and 2,712 (adaptive). Per-run tick p95 ranges from 13.56 to 19.94 ms. This is one seed under development-machine load, not the 900-run evaluation or a rendering-rate certification. Its manifest records binary `2975b143c26ee9cc1d90323a3aa1704f6901bdda784167d97faab6bb16295092`; the subsequent trace-only change exposes alternatives and leaves allocation rules unchanged.

Reference machine: Windows 11 build 26300, AMD64 Family 25 Model 116 Stepping 1, 16 logical CPUs, 16 GiB installed RAM, Python 3.14.3, Zig 0.15.2 C++/Clang, Release `-O2 -DNDEBUG`. Node 24 builds the frontend. The largest per-run engine tick p95 in the 60-run batch is **7.2936 ms**. This is a development-machine observation on 32 × 32 configurations, not validation of every standard envelope or a controlled 64 × 64 performance study. Browser rendering and persistence are excluded from engine tick timings.

## Requirement evidence map

| PRD requirements | Implementation and evidence |
|---|---|
| FR-001–005: maps, starts, isolation, sensing | Native deterministic room generator; strict custom-map validation; independent knowledge and graph-radius sensors; generation and hidden-obstacle tests |
| FR-006–010: frontiers and baseline algorithms | Stable-overlap frontier components; FIFO BFS, A*, independent, greedy and rectangular Hungarian; native oracle tests and exploration runs |
| FR-011–012: auction and adaptive allocation | Delivered bids, leased claims, deterministic conflicts, offer/ack/commit, integer score features, hold/switch rules, delayed-coordinator regression |
| FR-013–014: multi-agent planning | Rolling reservations, rejection cascades, observed blocker projection, staging, bounded message-backed CBS and named fallback tests |
| FR-015–018: communication and recovery | Event heap, keyed drops, delays, partitions, versioned merge, suspicion versus failure, lease expiry, repeated recovery episodes |
| FR-019–020: resources and targets | Integer energy, categorized ledger, feasible known return routes, station queue/staging, target discovery through sensors |
| FR-021–025: lifecycle, evaluation, persistence, replay | Locked tick boundaries; immutable paired runs; SQLite atomic commits; full checkpoints plus exact deltas; saved seeks and crash tests |
| FR-026–028: inspection, exports, termination | Local-map inspector, features and decisions, indexed history, streaming ZIP, distinct terminal states and discovery flags |
| FR-029–030: headless work and explanations | Sequential CLI runner, cancellable backend scheduler, retained partial evidence, expansion counters, messages, score traces and fallback events |

This map identifies implementations and tests; it is not a claim that every PRD acceptance permutation or every performance target was measured.

## Operational limits

- Reservation planning and staging do not guarantee deadlock freedom. A blocked failed occupant can make completion impossible.
- CBS is deliberately bounded and can fall back. Runtime joint planning is static between observation-driven replans; it does not optimize exploration.
- Charging admission uses current known routes and conservative queue estimates. Future closures can strand agents.
- Reconnection convergence needs actual deliveries, energy, and sufficient time. Partitions can produce duplicate claims and false suspicions.
- Saved replay reconstructs recorded states. Restart marks interrupted active processes failed; it does not restore an engine's pending queue for live continuation.
- The 128 × 128 / 16-agent envelope has been exercised for bounded progress, but its complete-run performance has not been exhaustively validated. The larger envelope is visibly experimental.
- Wire streaming sends coalesced authoritative full states. Database persistence uses checkpoint deltas. The distinction is documented in architecture.md.
- No guarantee of adaptive improvement is made. Full experimental claims require the frozen 900-run study and the requested ablations.
