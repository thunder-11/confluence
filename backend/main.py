import asyncio
from contextlib import asynccontextmanager
import csv
import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path
import platform
import random
import statistics
import sys
import uuid
import zipfile
import copy
import tempfile

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .engine import Engine, ROOT, build_info
from .models import CreateScenario, CreateRun, Command, CreateExperiment, InjectFault
from .store import Store
from .statistics import summarize
from .host import host_info

TERMINAL = {"COMPLETED", "EXHAUSTED", "TIMED_OUT", "STOPPED", "FAILED"}
store = Store()
runs = {}
batch_tasks = {}
execution_lock = asyncio.Lock()


def identifier():
    return uuid.uuid4().hex[:16]


def require_row(table, id):
    if table not in {"scenarios", "simulation_runs", "experiment_batches"}:
        raise ValueError("invalid internal table")
    row = store.query(f"SELECT * FROM {table} WHERE id=?", (id,), one=True)
    if row is None:
        raise HTTPException(
            404,
            detail={
                "code": "NOT_FOUND",
                "message": "Record not found",
                "details": {"id": id},
            },
        )
    return row


def scenario_view(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "config": json.loads(row["config_json"]),
        "mapHash": row["map_hash"],
        "createdAt": row["created_at"],
    }


class Run:
    def __init__(self, id, engine, result, config):
        self.id = id
        self.engine = engine
        self.config = config
        self.initial_config = copy.deepcopy(config)
        self.initial = result
        self.snapshot = result["snapshot"]
        self.state = "READY"
        self.speed = 10
        self.task = None
        self.control = asyncio.Lock()
        self.lifecycle = asyncio.Lock()
        self.sequence = 0
        self.clients = set()
        self.series = []
        self.wake = asyncio.Event()

    async def publish(self, events=()):
        self.sequence += 1
        envelope = {
            "schemaVersion": 1,
            "runId": self.id,
            "sequence": self.sequence,
            "tick": self.snapshot["tick"],
            "type": "snapshot",
            "payload": {
                "snapshot": self.snapshot,
                "events": list(events),
                "status": self.state,
            },
        }
        for queue in list(self.clients):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(envelope)

    async def advance(self):
        async with self.control:
            if self.state in TERMINAL:
                return
            try:
                result = await self.engine.call("advance", {"ticks": 1})
            except Exception as exc:
                await self.fail(str(exc))
                raise RuntimeError(str(exc)) from exc
            self.snapshot = result["snapshot"]
            if self.snapshot["status"] in TERMINAL:
                self.state = self.snapshot["status"]
            store.save_tick(self.id, self.snapshot, result["events"], self.state)
            self.series.append(
                {"tick": self.snapshot["tick"], **self.snapshot["metrics"]}
            )
            if len(self.series) > 2000:
                self.series = self.series[::2]
            await self.publish(result["events"])
            if self.state in TERMINAL:
                await self.engine.close()

    async def fail(self, message):
        self.state = "FAILED"
        sequence = store.query(
            "SELECT COALESCE(MAX(sequence),0)+1 AS n FROM events WHERE run_id=?",
            (self.id,),
            one=True,
        )["n"]
        event = {
            "sequence": sequence,
            "tick": self.snapshot["tick"],
            "type": "engine_error",
            "agentId": None,
            "payload": {"message": message},
        }
        store.save_tick(self.id, self.snapshot, [event], "FAILED")
        store.execute(
            "UPDATE simulation_runs SET termination_reason=? WHERE id=?",
            (message, self.id),
        )
        await self.publish([event])
        await self.engine.close()

    async def loop(self):
        try:
            while self.state == "RUNNING":
                start = asyncio.get_running_loop().time()
                await self.advance()
                delay = max(
                    0, 1 / self.speed - (asyncio.get_running_loop().time() - start)
                )
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                self.wake.clear()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self.state != "FAILED":
                await self.fail(str(exc))

    async def cancel_loop(self):
        # Let an in-flight deterministic tick finish before changing lifecycle state.
        task = self.task
        self.task = None
        self.wake.set()
        if task and task is not asyncio.current_task():
            await task


async def create_run(body: CreateRun, batch_id=None, config_override=None):
    # Terminal runs remain in SQLite; retain only connected or actively executing processes.
    for old_id, old_run in list(runs.items()):
        if old_run.state in TERMINAL and not old_run.clients:
            runs.pop(old_id, None)
    scenario = require_row("scenarios", body.scenarioId)
    config = config_override or json.loads(scenario["config_json"])
    config = copy.deepcopy(
        {
            **config,
            "strategy": body.strategy,
            "planner": body.planner,
            "pathfinder": body.pathfinder,
        }
    )
    engine = await Engine().open()
    try:
        result = await engine.call("initialize", config)
    except Exception:
        await engine.close()
        raise
    id = identifier()
    version = "confluence-1.0.0+" + build_info()["engineSha256"][:12]
    store.execute(
        "INSERT INTO simulation_runs(id,batch_id,scenario_id,strategy,planner,config_json,engine_version,status,initial_hash) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            id,
            batch_id,
            body.scenarioId,
            body.strategy,
            body.planner,
            json.dumps(config),
            version,
            "READY",
            result["snapshot"]["stateHash"],
        ),
    )
    for a in result["snapshot"]["agents"]:
        store.execute(
            "INSERT INTO agents VALUES(?,?,?,?,?,?,?)",
            (
                id,
                a["id"],
                a["position"] % config["width"],
                a["position"] // config["width"],
                a["capacity"],
                a["energy"],
                "{}",
            ),
        )
    run = Run(id, engine, result, config)
    runs[id] = run
    store.save_tick(id, run.snapshot, result["events"], "READY")
    return run


@asynccontextmanager
async def lifespan(app):
    yield
    for task in batch_tasks.values():
        task.cancel()
    await asyncio.gather(*batch_tasks.values(), return_exceptions=True)
    for run in runs.values():
        if run.state == "RUNNING":
            run.state = "PAUSED"
    await asyncio.gather(
        *(r.cancel_loop() for r in runs.values()), return_exceptions=True
    )
    await asyncio.gather(
        *(r.engine.close() for r in runs.values()), return_exceptions=True
    )


app = FastAPI(title="CONFLUENCE", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_CONFIGURATION",
            "message": "Configuration validation failed",
            "details": json.loads(json.dumps(exc.errors(), default=str)),
        },
    )


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=(
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "REQUEST_ERROR", "message": str(exc.detail), "details": {}}
        ),
    )


@app.exception_handler(RuntimeError)
async def runtime_error(request, exc):
    return JSONResponse(
        status_code=503,
        content={"code": "ENGINE_ERROR", "message": str(exc), "details": {}},
    )


@app.exception_handler(ValueError)
async def input_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={"code": "INVALID_CONFIGURATION", "message": str(exc), "details": {}},
    )


@app.get("/api/v1/health")
async def health():
    from .engine import engine_path

    try:
        binary = str(engine_path())
    except RuntimeError:
        binary = None
    return {
        "status": "healthy" if binary else "engine_missing",
        "engine": binary,
        "version": "1.0.0",
    }


@app.post("/api/v1/scenarios/generate", status_code=201)
@app.post("/api/v1/scenarios", status_code=201)
async def save_scenario(body: CreateScenario):
    engine = await Engine().open()
    try:
        result = await engine.call("initialize", body.config.engine_payload())
        materialized = result["scenario"]
        config = materialized["config"]
        if not config["allowDisconnected"]:
            # Connectivity validation is performed by the C++ evaluator, not a Python planner.
            snapshot = result["snapshot"]
            free = sum(c == 0 for c in config["map"])
            if materialized["componentCount"] > 1:
                raise HTTPException(
                    422, "Disconnected free cells: set allowDisconnected to confirm"
                )
        id = identifier()
        store.execute(
            "INSERT INTO scenarios(id,name,schema_version,generator_version,seed,config_json,initial_map_json,map_hash) VALUES(?,?,?,?,?,?,?,?)",
            (
                id,
                body.name,
                1,
                materialized["generatorVersion"],
                config["seed"],
                json.dumps(config),
                json.dumps(config["map"]),
                materialized["mapHash"],
            ),
        )
        return scenario_view(require_row("scenarios", id))
    finally:
        await engine.close()


@app.get("/api/v1/scenarios")
async def scenarios():
    return [
        scenario_view(row)
        for row in store.query(
            "SELECT * FROM scenarios ORDER BY created_at DESC LIMIT 100"
        )
    ]


@app.get("/api/v1/scenarios/{id}")
async def get_scenario(id: str):
    return scenario_view(require_row("scenarios", id))


@app.post("/api/v1/runs", status_code=201)
async def new_run(body: CreateRun):
    async with execution_lock:
        if any(r.state not in TERMINAL for r in runs.values()):
            raise HTTPException(
                409, "Stop the active simulation before creating another"
            )
        if any(not t.done() for t in batch_tasks.values()):
            raise HTTPException(409, "An experiment is already running")
        run = await create_run(body)
        return {"id": run.id, "snapshot": run.snapshot, "status": run.state}


@app.get("/api/v1/runs")
async def list_runs():
    return store.query(
        "SELECT id,batch_id,scenario_id,strategy,planner,status,tick,started_at,termination_reason FROM simulation_runs ORDER BY started_at DESC,rowid DESC LIMIT 100"
    )


@app.get("/api/v1/runs/{id}")
async def get_run(id: str):
    row = require_row("simulation_runs", id)
    return {**row, "snapshot": runs[id].snapshot if id in runs else store.snapshot(id)}


@app.post("/api/v1/runs/{id}/commands")
async def command(id: str, body: Command):
    run = runs.get(id)
    if run:
        async with run.lifecycle:
            return await _command(id, body)
    return await _command(id, body)


async def _command(id: str, body: Command):
    row = require_row("simulation_runs", id)
    if row["batch_id"]:
        raise HTTPException(
            409,
            "Experiment runs are read-only; cancel the experiment to stop execution",
        )
    if id not in runs:
        if body.command == "reset" and row["status"] in TERMINAL:
            async with execution_lock:
                if any(r.state not in TERMINAL for r in runs.values()) or any(
                    not t.done() for t in batch_tasks.values()
                ):
                    raise HTTPException(
                        409, "Stop the active simulation or experiment first"
                    )
                saved = json.loads(row["config_json"])
                fresh = await create_run(
                    CreateRun(
                        scenarioId=row["scenario_id"],
                        strategy=row["strategy"],
                        planner=row["planner"],
                        pathfinder=saved.get("pathfinder", "astar"),
                    )
                )
            return {"id": fresh.id, "status": fresh.state, "snapshot": fresh.snapshot}
        raise HTTPException(
            409, "Saved run is read-only; reset it to create a new execution"
        )
    run = runs[id]
    if body.command in {"start", "resume"}:
        expected = "READY" if body.command == "start" else "PAUSED"
        if run.state != expected:
            raise HTTPException(409, f"{body.command} requires {expected}")
        run.speed = body.speed
        run.state = "RUNNING"
        run.task = asyncio.create_task(run.loop())
    elif body.command == "pause":
        if run.state != "RUNNING":
            raise HTTPException(409, "pause requires RUNNING")
        run.state = "PAUSED"
        await run.cancel_loop()
    elif body.command == "step":
        if run.state not in {"READY", "PAUSED"}:
            raise HTTPException(409, "step requires READY or PAUSED")
        run.state = "PAUSED"
        await run.advance()
    elif body.command == "stop":
        if run.state in TERMINAL:
            raise HTTPException(409, "run already terminated")
        run.state = "STOPPED"
        await run.cancel_loop()
        await run.engine.close()
        store.save_tick(id, run.snapshot, [], "STOPPED")
    elif body.command == "reset":
        if run.state == "RUNNING":
            raise HTTPException(409, "pause before resetting")
        # Preserve the original run as evidence; reset creates a fresh run identity.
        if run.state not in TERMINAL:
            run.state = "STOPPED"
            await run.engine.close()
            store.save_tick(id, run.snapshot, [], "STOPPED")
        original = run.initial_config
        async with execution_lock:
            if any(r.state not in TERMINAL for r in runs.values()) or any(
                not t.done() for t in batch_tasks.values()
            ):
                raise HTTPException(
                    409, "Stop the active simulation or experiment first"
                )
            fresh = await create_run(
                CreateRun(
                    scenarioId=row["scenario_id"],
                    strategy=original["strategy"],
                    planner=original["planner"],
                    pathfinder=original["pathfinder"],
                ),
                config_override=original,
            )
        return {"id": fresh.id, "status": fresh.state, "snapshot": fresh.snapshot}
    elif body.command == "set_speed":
        run.speed = body.speed
        run.wake.set()
    store.execute("UPDATE simulation_runs SET status=? WHERE id=?", (run.state, id))
    await run.publish()
    return {"id": id, "status": run.state, "snapshot": run.snapshot}


@app.post("/api/v1/runs/{id}/faults")
async def inject(id: str, body: InjectFault):
    require_row("simulation_runs", id)
    if id not in runs or runs[id].state in TERMINAL:
        raise HTTPException(409, "run is not active")
    run = runs[id]
    if require_row("simulation_runs", id)["batch_id"]:
        raise HTTPException(409, "comparison manifests are frozen")
    if not body.nextTick and body.tick <= run.snapshot["tick"]:
        raise HTTPException(422, "fault must be scheduled after the current tick")
    if body.agentId is not None and body.agentId >= len(run.snapshot["agents"]):
        raise HTTPException(422, "unknown agent")
    if body.x is not None and (
        body.x >= run.config["width"] or body.y >= run.config["height"]
    ):
        raise HTTPException(422, "cell outside map")
    fault = body.model_dump(exclude_none=True, exclude={"nextTick"})
    async with run.control:
        if run.state in TERMINAL:
            raise HTTPException(409, "Run has terminated")
        if body.nextTick:
            delta = run.snapshot["tick"] + 1 - fault["tick"]
            fault["tick"] += delta
            for key in ("endTick", "unblockTick", "restorationTick"):
                if key in fault:
                    fault[key] += delta
        elif fault["tick"] <= run.snapshot["tick"]:
            raise HTTPException(
                422, "Requested tick has passed; queue the fault for the next tick"
            )
        result = await run.engine.call("queue_fault", fault)
        run.config["faultSchedule"].append(fault)
        run.config["interactive"] = True
        store.execute(
            "UPDATE simulation_runs SET config_json=? WHERE id=?",
            (json.dumps(run.config), id),
        )
        store.save_tick(id, run.snapshot, result["events"], run.state)
    return {"status": "queued", "fault": fault}


@app.get("/api/v1/runs/{id}/snapshot")
async def snapshot(id: str, tick: int | None = None):
    require_row("simulation_runs", id)
    result = store.snapshot(id, tick)
    if result is None:
        raise HTTPException(404, "No snapshot at requested tick")
    return result


@app.get("/api/v1/runs/{id}/events")
async def events(
    id: str,
    afterSequence: int = 0,
    beforeSequence: int | None = None,
    throughTick: int | None = None,
    recent: bool = False,
    category: str = "all",
    limit: int = 500,
):
    require_row("simulation_runs", id)
    if not 1 <= limit <= 1000:
        raise HTTPException(422, "limit must be 1..1000")
    groups = {
        "all": None,
        "decisions": ["decision", "bid", "claim_expired", "assignment_acknowledged"],
        "communication": [
            "message_delivered",
            "message_dropped",
            "peer_reconnected",
            "peer_suspected",
            "partition_started",
        ],
        "resources": [
            "charge_started",
            "charge_complete",
            "station_queue_entered",
            "energy_depleted",
        ],
        "failures": [
            "peer_unavailable_observed",
            "fault_ignored",
            "agent_failure",
            "agent_disable",
            "failure_detection",
            "assignment_recovery",
            "progress_recovery",
            "agent_restored",
            "energy_depleted",
        ],
        "discoveries": ["target_discovered"],
        "planning": [
            "movement_rejected",
            "planner_fallback",
            "obstacle_blocked",
            "obstacle_unblocked",
        ],
    }
    if category not in groups:
        raise HTTPException(422, "Unknown event category")
    sql = "SELECT * FROM events WHERE run_id=? AND sequence>?"
    args = [id, afterSequence]
    if throughTick is not None:
        if throughTick < 0:
            raise HTTPException(422, "throughTick must be nonnegative")
        sql += " AND tick<=?"
        args.append(throughTick)
    if beforeSequence is not None:
        sql += " AND sequence<?"
        args.append(beforeSequence)
    if groups[category]:
        kinds = groups[category]
        sql += " AND type IN (" + ",".join("?" for _ in kinds) + ")"
        args.extend(kinds)
    sql += " ORDER BY sequence " + ("DESC" if recent else "ASC") + " LIMIT ?"
    args.append(limit)
    rows = store.query(sql, args)
    if recent:
        rows.reverse()
    return [
        {
            "sequence": row["sequence"],
            "tick": row["tick"],
            "type": row["type"],
            "agentId": row["agent_id"],
            "payload": json.loads(row["payload_json"]),
        }
        for row in rows
    ]


@app.get("/api/v1/runs/{id}/metrics")
async def metrics(id: str):
    require_row("simulation_runs", id)
    return {
        "series": store.series(id),
        "final": store.query("SELECT * FROM benchmark_results WHERE run_id=?", (id,)),
    }


@app.get("/api/v1/runs/{id}/agents/{agent_id}/metrics")
async def agent_metrics(id: str, agent_id: int):
    require_row("simulation_runs", id)
    if not store.query(
        "SELECT agent_id FROM agents WHERE run_id=? AND agent_id=?",
        (id, agent_id),
        one=True,
    ):
        raise HTTPException(404, "Agent not found")
    return {"series": await asyncio.to_thread(store.agent_series, id, agent_id)}


@app.websocket("/api/v1/runs/{id}/stream")
async def stream(ws: WebSocket, id: str):
    await ws.accept()
    if id not in runs:
        snap = store.snapshot(id)
        if snap:
            await ws.send_json(
                {
                    "schemaVersion": 1,
                    "runId": id,
                    "sequence": 0,
                    "tick": snap["tick"],
                    "type": "snapshot",
                    "payload": {
                        "snapshot": snap,
                        "events": [],
                        "status": require_row("simulation_runs", id)["status"],
                    },
                }
            )
        await ws.close()
        return
    run = runs[id]
    queue = asyncio.Queue(maxsize=2)
    run.clients.add(queue)
    try:
        await ws.send_json(
            {
                "schemaVersion": 1,
                "runId": id,
                "sequence": run.sequence,
                "tick": run.snapshot["tick"],
                "type": "snapshot",
                "payload": {
                    "snapshot": run.snapshot,
                    "events": [],
                    "status": run.state,
                },
            }
        )
        while True:
            item = await queue.get()
            await ws.send_json(item)
            await asyncio.sleep(0.1)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        run.clients.discard(queue)


async def execute_batch(id, body, base_config, custom=False):
    current = None
    try:
        for seed in body.seeds:
            # Generate once per seed, then freeze that materialized scenario for every strategy.
            config = (
                dict(base_config)
                if custom
                else {
                    k: v
                    for k, v in base_config.items()
                    if k
                    not in {"map", "targets", "zones", "starts", "chargingStations"}
                }
            )
            config.update(seed=seed, maxTicks=body.maxTicks)
            engine = await Engine().open()
            try:
                generated = await engine.call("initialize", config)
            finally:
                await engine.close()
            frozen = generated["scenario"]["config"]
            for strategy in body.strategies:
                if require_row("experiment_batches", id)["status"] == "CANCELLED":
                    return
                run = await create_run(
                    CreateRun(scenarioId=body.scenarioId, strategy=strategy),
                    batch_id=id,
                    config_override=frozen,
                )
                current = run
                run.state = "RUNNING"
                while run.state not in TERMINAL:
                    if require_row("experiment_batches", id)["status"] == "CANCELLED":
                        run.state = "STOPPED"
                        store.save_tick(run.id, run.snapshot, [], "STOPPED")
                        await run.engine.close()
                        return
                    await run.advance()
                    await asyncio.sleep(0)
                runs.pop(run.id, None)
                current = None
        store.execute(
            "UPDATE experiment_batches SET status='COMPLETED' WHERE id=?", (id,)
        )
    except asyncio.CancelledError:
        store.execute(
            "UPDATE experiment_batches SET status='INTERRUPTED' WHERE id=?", (id,)
        )
        raise
    except Exception as exc:
        store.execute(
            "UPDATE experiment_batches SET status='FAILED',manifest_json=json_set(manifest_json,'$.error',?) WHERE id=?",
            (str(exc), id),
        )
    finally:
        if current:
            if current.state not in TERMINAL:
                await current.fail("EXPERIMENT_INTERRUPTED")
            await current.engine.close()
            runs.pop(current.id, None)


@app.post("/api/v1/experiments", status_code=201)
async def experiment(body: CreateExperiment):
    async with execution_lock:
        if any(r.state not in TERMINAL for r in runs.values()) or any(
            not t.done() for t in batch_tasks.values()
        ):
            raise HTTPException(409, "Stop the active simulation or experiment first")
        scenario = require_row("scenarios", body.scenarioId)
        if len(set(body.seeds)) != len(body.seeds) or len(set(body.strategies)) != len(
            body.strategies
        ):
            raise HTTPException(422, "seeds and strategies must be unique")
        for seed in body.seeds:
            if not seed.isdecimal() or not 0 <= int(seed) < 2**64:
                raise HTTPException(422, "invalid seed")
        id = identifier()
        manifest = body.model_dump()
        manifest.update(
            build=build_info(),
            referenceMachine=host_info(),
            scenario=json.loads(scenario["config_json"]),
            analysisSeed=2026,
        )
        wire = json.dumps(manifest, sort_keys=True)
        store.execute(
            "INSERT INTO experiment_batches(id,name,manifest_json,manifest_hash,status) VALUES(?,?,?,?,?)",
            (id, body.name, wire, hashlib.sha256(wire.encode()).hexdigest(), "RUNNING"),
        )
        batch_tasks[id] = asyncio.create_task(
            execute_batch(
                id,
                body,
                json.loads(scenario["config_json"]),
                custom=scenario["generator_version"] == "custom-1",
            )
        )
        return {
            "id": id,
            "status": "RUNNING",
            "totalRuns": len(body.seeds) * len(body.strategies),
        }


@app.get("/api/v1/experiments")
async def experiments():
    return store.query(
        "SELECT id,name,status,created_at FROM experiment_batches ORDER BY created_at DESC LIMIT 100"
    )


@app.get("/api/v1/experiments/{id}")
async def experiment_result(id: str):
    batch = require_row("experiment_batches", id)
    rows = store.query(
        "SELECT id,strategy,status,tick,json_extract(config_json,'$.seed') AS seed FROM simulation_runs WHERE batch_id=? ORDER BY started_at,rowid",
        (id,),
    )
    summary = {}
    paired = {}
    by_seed = {}
    all_measurements = store.query(
        "SELECT b.* FROM benchmark_results b JOIN simulation_runs r ON r.id=b.run_id WHERE r.batch_id=?",
        (id,),
    )
    grouped = {}
    for measurement in all_measurements:
        grouped.setdefault(measurement["run_id"], []).append(measurement)
    for row in rows:
        measurements = grouped.get(row["id"], [])
        row["metrics"] = {m["metric_name"]: m["value"] for m in measurements}
        row["measurements"] = {
            m["metric_name"]: {
                "value": m["value"],
                "unit": m["unit"],
                "status": m["measurement_status"],
            }
            for m in measurements
        }
        if row["metrics"]:
            by_seed[(row["strategy"], row["seed"])] = row["metrics"]

    def calculate():
        for strategy in sorted(set(r["strategy"] for r in rows)):
            names = sorted({name for row in rows for name in row["metrics"]})
            summary[strategy] = {
                name: summarize(
                    [
                        r["metrics"][name]
                        for r in rows
                        if r["strategy"] == strategy
                        and r["metrics"].get(name) is not None
                    ],
                    bootstrap=batch["status"] != "RUNNING",
                )
                for name in names
            }
            differences = [
                values["coverage"] - by_seed[("independent", seed)]["coverage"]
                for (s, seed), values in by_seed.items()
                if s == strategy and ("independent", seed) in by_seed
            ]
            paired[strategy] = summarize(
                differences, bootstrap=batch["status"] != "RUNNING"
            )

    await asyncio.to_thread(calculate)
    return {
        **batch,
        "manifest": json.loads(batch["manifest_json"]),
        "runs": rows,
        "summary": summary,
        "pairedCoverageVsIndependent": paired,
    }


@app.post("/api/v1/experiments/{id}/cancel")
async def cancel_experiment(id: str):
    row = require_row("experiment_batches", id)
    if row["status"] != "RUNNING":
        raise HTTPException(409, "experiment is not running")
    store.execute("UPDATE experiment_batches SET status='CANCELLED' WHERE id=?", (id,))
    return {"status": "CANCELLED"}


def write_export(result):
    buffer = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(result["manifest"], indent=2))
        archive.writestr("results.json", json.dumps(result, indent=2))
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "run_id",
                "seed",
                "strategy",
                "status",
                "metric",
                "value",
                "unit",
                "measurement_status",
            ]
        )
        for run in result["runs"]:
            for name, value in run["metrics"].items():
                measurement = run["measurements"][name]
                writer.writerow(
                    [
                        run["id"],
                        run["seed"],
                        run["strategy"],
                        run["status"],
                        name,
                        value,
                        measurement["unit"],
                        measurement["status"],
                    ]
                )
            with archive.open(
                f"events/{run['id']}.ndjson", "w", force_zip64=True
            ) as output_events:
                with store.connect() as db:
                    for event in db.execute(
                        "SELECT * FROM events WHERE run_id=? ORDER BY sequence",
                        (run["id"],),
                    ):
                        output_events.write((json.dumps(dict(event)) + "\n").encode())
            archive.writestr(
                f"runs/{run['id']}.json",
                json.dumps(require_row("simulation_runs", run["id"]), indent=2),
            )
        archive.writestr("metrics.csv", output.getvalue())
    buffer.seek(0)
    return buffer


@app.get("/api/v1/experiments/{id}/export")
async def export(id: str):
    if require_row("experiment_batches", id)["status"] == "RUNNING":
        raise HTTPException(
            409, "Finish or cancel the experiment before exporting its evidence"
        )
    result = await experiment_result(id)
    buffer = await asyncio.to_thread(write_export, result)

    def chunks():
        try:
            while chunk := buffer.read(65536):
                yield chunk
        finally:
            buffer.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="confluence-{id}.zip"'},
    )


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
