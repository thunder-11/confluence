# CONFLUENCE

**Many agents. One mission.** A local, software-only multi-agent exploration laboratory.

The C++20 engine performs sensing, frontier extraction, allocation, search, communication, energy management, and movement validation. FastAPI orchestrates engine subprocesses and records runs in SQLite. React/TypeScript renders the live Canvas workspace and Recharts analytics.

The agreed specification is [prd.md](prd.md). Implementation details and evidence are in [docs/architecture.md](docs/architecture.md) and [docs/validation.md](docs/validation.md).

## Run on Windows

Requires Python 3.11+ and Node 22+. A native C++ compiler is optional: setup installs Zig's C++ compiler inside the project virtual environment.

```powershell
./scripts/setup.ps1
./start.ps1
```

Open [CONFLUENCE](http://127.0.0.1:8000). Everything runs on your computer; there are no API keys, paid services, or hardware dependencies. Dependency installation needs internet access; normal execution does not.

If PowerShell policy prevents scripts, use the equivalent commands below instead of changing system policy.

```powershell
py -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe scripts/build.py
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
./.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Linux / macOS

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/build.py
cd frontend && npm ci && npm run build && cd ..
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

For a native C++ build, `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` followed by `cmake --build build --config Release` builds the engine and tests. Set `CONFLUENCE_ENGINE` to override the binary location, and `CONFLUENCE_DB` to override the database path.

## Use the laboratory

1. Open Simulation Studio and start exploration. The default uses a 64 × 64 map, four agents, and high energy capacity so coordination can be observed without early resource exhaustion.
2. Change the knowledge view to inspect an agent's incomplete map. The evaluator view is explicitly labeled.
3. Select an agent and inspect State, Decision trace, or Statistics. The inspector includes the categorized energy ledger, all score factors, and feasible local alternatives. Paths and assigned frontier cells use its stable color.
4. Test resilience by injecting a breakdown, temporary partition, or corridor closure.
5. Configure Resource Constraints for a 100,000-milliunit battery; charging stations have one occupied service cell and FIFO requests.
6. Paint a custom map in Scenario Builder. Save validation rejects invalid starts, walls under stations, and unconfirmed disconnected regions.
7. Stop the live run and launch a comparison. The engine runs the five strategies sequentially on frozen seed configurations.
8. Replay results side by side and download a ZIP containing manifests, raw metrics, run configurations, and events.

Reset creates a **new run ID** and retains the previous run as evidence. Changing playback speed does not change logical decisions. Saved runs are replayable after server restart; interrupted live runs are marked failed rather than silently resumed.

## Verify

```powershell
./build/confluence_tests.exe
./.venv/Scripts/python.exe -m pytest -q
cd frontend
npm.cmd run build
```

## Headless experiments

No running backend or browser is needed:

```powershell
./.venv/Scripts/python.exe scripts/benchmark.py --families normal --seeds 3 --size 32 --ticks 1000 --output data/benchmarks/smoke
```

Omit flags for the specified six families × 30 seeds × five strategies = 900-run study. This is a substantial experiment, not part of app startup. Outputs are written after every run so partial results survive interruption. Development seeds are 0–9; evaluation defaults to 100–129.

The adaptive strategy is a proposed policy, not an established improvement. Reports include unsuccessful runs and measured results. See the validation document for the actual checks performed and remaining limitations.

## Development

Run FastAPI on port 8000 and `npm run dev` inside `frontend` for Vite on port 5173. Vite proxies `/api` including WebSockets. API documentation is available at [Swagger UI](http://127.0.0.1:8000/docs).

The optional `frontend/e2e` workflow uses Playwright Chromium. Install its browser with `npx playwright install chromium`, then run `npm run test:e2e` in `frontend`. The configuration launches an isolated server on port 8010 with a separate database so it does not modify the normal workspace. See [docs/design.md](docs/design.md) for actual browser verification and the interface direction.

```
engine/include/   Custom heap, graph search, assignment, CBS, simulation
engine/src/       Versioned NDJSON subprocess entrypoint
engine/tests/     C++ correctness and invariant tests
backend/          FastAPI, validation, subprocess bridge, SQLite
frontend/src/     React dashboard, Canvas renderer, analytics
scripts/          Setup, build, headless experiments
tests/            Engine protocol and API integration tests
```

JSON serialization uses vendored nlohmann/json 3.12.0 under its MIT license. All core algorithms are implemented in this repository; no external solver supplies them.
