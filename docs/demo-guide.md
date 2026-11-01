# Lightweight presentation scenarios

Open **Demo scenarios** in the persistent left navigation. Choose **Load demo**, then **Start exploration** in the studio. Loading creates a fresh saved scenario and run; it stops any active interactive run first. All six scenes use the native C++ engine, a fixed hand-built 16 × 16 map, known station coordinates, hidden targets, A*, and reservation planning. Nothing is prerecorded.

| Scene | Agents / allocation | Presentation cue | Tick limit |
|---|---|---|---|
| First discovery | 2 / independent | Switch between collective and selected-agent knowledge | 400 |
| Four-room team | 4 / greedy | Show frontier destinations and planned paths through connecting doors | 500 |
| Radio silence | 4 / decentralized auction | Partition starts at 12 and ends at 42; inspect claims and knowledge synchronization | 500 |
| Agent recovery | 4 / adaptive | Agent 2 fails at 20 and restores at 65; inspect failure suspicion and lease events | 600 |
| Changing route | 4 / greedy | Door (8, 4) closes at 18 and reopens at 55; occupied placement may be postponed | 500 |
| Charging break | 2 / independent | 35,000-milliunit batteries, 5,000 reserve, two nearby chargers; inspect returning/charging and the ledger | 600 |

The initial playback setting is 20 ticks per second, so configured limits represent 20–30 seconds of logical playback, excluding setup, pauses and machine overhead. Runs may finish earlier or terminate incomplete. These are demonstration configurations, not benchmark claims. The charging scene sets transmit/receive energy costs to zero to make battery movement and charging easy to explain; other scenes use the normal costs with nonbinding capacity.

Use pause and single-step to explain a decision. Reset repeats the frozen scene. Saved runs support replay; the scenario can also be selected in Compare for a small five-strategy demonstration. A run is initially ready, so the presenter decides when movement starts.

Navigation uses real hash links with active-page indication and browser back/forward support. Labels remain visible in a compact left rail on narrow screens; Expand navigation opens the full-width menu. Escape, Close menu, clicking outside, or selecting a page closes it.

At the user's request, the long PRD study was cancelled after 153 completed primary runs and its completion automation was deleted. Partial research evidence is preserved; the full scientific study is not claimed complete. No further benchmark or regression validation was run for this demo-focused change; the frontend was built to publish it locally.
