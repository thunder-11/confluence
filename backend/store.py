import json
import os
from pathlib import Path
import sqlite3
import zlib
from contextlib import contextmanager
from .deltas import difference, apply_patch

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY,name TEXT NOT NULL,schema_version INTEGER,generator_version TEXT,seed TEXT,config_json TEXT,initial_map_json TEXT,map_hash TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS experiment_batches(id TEXT PRIMARY KEY,name TEXT,manifest_json TEXT,manifest_hash TEXT,status TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS simulation_runs(id TEXT PRIMARY KEY,batch_id TEXT REFERENCES experiment_batches(id),scenario_id TEXT REFERENCES scenarios(id),strategy TEXT,planner TEXT,config_json TEXT,engine_version TEXT,status TEXT,tick INTEGER DEFAULT 0,termination_reason TEXT,initial_hash TEXT,final_hash TEXT,started_at TEXT DEFAULT CURRENT_TIMESTAMP,finished_at TEXT);
CREATE TABLE IF NOT EXISTS agents(run_id TEXT REFERENCES simulation_runs(id),agent_id INTEGER,initial_x INTEGER,initial_y INTEGER,capacity INTEGER,initial_energy INTEGER,config_json TEXT,PRIMARY KEY(run_id,agent_id));
CREATE TABLE IF NOT EXISTS run_snapshots(run_id TEXT REFERENCES simulation_runs(id),tick INTEGER,schema_version INTEGER,state_blob BLOB,state_hash TEXT,PRIMARY KEY(run_id,tick));
CREATE TABLE IF NOT EXISTS agent_snapshots(run_id TEXT,tick INTEGER,agent_id INTEGER,x INTEGER,y INTEGER,energy INTEGER,operational_status TEXT,activity TEXT,task_id INTEGER,map_revision INTEGER,PRIMARY KEY(run_id,tick,agent_id),FOREIGN KEY(run_id,agent_id) REFERENCES agents(run_id,agent_id));
CREATE TABLE IF NOT EXISTS events(run_id TEXT REFERENCES simulation_runs(id),sequence INTEGER,tick INTEGER,type TEXT,agent_id INTEGER,payload_json TEXT,PRIMARY KEY(run_id,sequence));
CREATE TABLE IF NOT EXISTS discovered_targets(run_id TEXT REFERENCES simulation_runs(id),target_id TEXT,agent_id INTEGER,discovery_tick INTEGER,x INTEGER,y INTEGER,PRIMARY KEY(run_id,target_id));
CREATE TABLE IF NOT EXISTS benchmark_results(run_id TEXT REFERENCES simulation_runs(id),metric_name TEXT,value REAL,unit TEXT,measurement_status TEXT,PRIMARY KEY(run_id,metric_name));
CREATE TABLE IF NOT EXISTS metric_samples(run_id TEXT REFERENCES simulation_runs(id),tick INTEGER,metrics_json TEXT,PRIMARY KEY(run_id,tick));
CREATE INDEX IF NOT EXISTS event_ticks ON events(run_id,tick);
CREATE INDEX IF NOT EXISTS run_batches ON simulation_runs(batch_id,status);
CREATE INDEX IF NOT EXISTS agent_history ON agent_snapshots(run_id,agent_id,tick);
"""


class Store:
    def __init__(self, path=None):
        self.path = Path(
            path
            or os.environ.get("CONFLUENCE_DB", ROOT / "data" / "confluence.sqlite3")
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_state = {}
        with self.connect() as db:
            db.executescript(SCHEMA)
            columns = {
                row["name"] for row in db.execute("PRAGMA table_info(agent_snapshots)")
            }
            if "metrics_json" not in columns:
                db.execute(
                    "ALTER TABLE agent_snapshots ADD COLUMN metrics_json TEXT NOT NULL DEFAULT '{}'"
                )
            db.execute("PRAGMA user_version=2")
            db.execute(
                "UPDATE simulation_runs SET status='FAILED',termination_reason='SERVER_RESTART',finished_at=CURRENT_TIMESTAMP WHERE status IN ('READY','RUNNING','PAUSED')"
            )
            db.execute(
                "UPDATE experiment_batches SET status='INTERRUPTED' WHERE status='RUNNING'"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def query(self, sql, args=(), one=False):
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        result = [dict(row) for row in rows]
        return (result[0] if result else None) if one else result

    def execute(self, sql, args=()):
        with self.connect() as db:
            db.execute(sql, args)

    def save_tick(self, run_id, snapshot, events, status=None):
        tick, width = snapshot["tick"], snapshot["width"]
        state = status or snapshot["status"]
        terminal = state in {"COMPLETED", "EXHAUSTED", "TIMED_OUT", "STOPPED", "FAILED"}
        previous = self._last_state.get(run_id)
        checkpoint = (
            previous is None or tick % 50 == 0 or terminal or previous["tick"] >= tick
        )
        schema_version = 1 if checkpoint else 2
        document = (
            snapshot
            if checkpoint
            else {"baseTick": previous["tick"], "patch": difference(previous, snapshot)}
        )
        blob = zlib.compress(json.dumps(document, separators=(",", ":")).encode())
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO run_snapshots VALUES(?,?,?,?,?)",
                (run_id, tick, schema_version, blob, snapshot["stateHash"]),
            )
            db.execute(
                "INSERT OR REPLACE INTO metric_samples VALUES(?,?,?)",
                (run_id, tick, json.dumps(snapshot["metrics"], separators=(",", ":"))),
            )
            db.execute(
                "UPDATE simulation_runs SET tick=?,status=?,final_hash=?,termination_reason=?,finished_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?",
                (
                    tick,
                    state,
                    snapshot["stateHash"],
                    state if terminal else None,
                    terminal,
                    run_id,
                ),
            )
            for a in snapshot["agents"]:
                measurements = {
                    "energy": a["energy"],
                    "energySpent": a["energySpent"],
                    "distance": a["distance"],
                    "knownCells": sum(v >= 0 for v in a["map"]),
                    "pathLength": max(0, len(a["path"]) - 1),
                    "utilization": a.get("utilization", 0),
                    "sensedCells": a.get("sensedCells", 0),
                }
                db.execute(
                    "INSERT OR REPLACE INTO agent_snapshots(run_id,tick,agent_id,x,y,energy,operational_status,activity,task_id,map_revision,metrics_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        tick,
                        a["id"],
                        a["position"] % width,
                        a["position"] // width,
                        a["energy"],
                        a["status"],
                        a["activity"],
                        a["task"],
                        a["mapRevision"],
                        json.dumps(measurements, separators=(",", ":")),
                    ),
                )
            for event in events:
                db.execute(
                    "INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)",
                    (
                        run_id,
                        event["sequence"],
                        event["tick"],
                        event["type"],
                        event.get("agentId"),
                        json.dumps(event["payload"]),
                    ),
                )
                if event["type"] == "target_discovered":
                    p = event["payload"]["cell"]
                    db.execute(
                        "INSERT OR IGNORE INTO discovered_targets VALUES(?,?,?,?,?,?)",
                        (
                            run_id,
                            event["payload"]["targetId"],
                            event["agentId"],
                            event["tick"],
                            p % width,
                            p // width,
                        ),
                    )
            if terminal:
                for name, value in snapshot["metrics"].items():
                    measurement = (
                        "MEASURED"
                        if value is not None
                        else (
                            "CENSORED" if snapshot.get("recovery") else "NOT_APPLICABLE"
                        )
                    )
                    if value is None and name == "explorationCompletionTick":
                        measurement = "CENSORED"
                    if (
                        value is None
                        and name in {"assignmentRecoveryTicks", "progressRecoveryTicks"}
                        and not any(
                            e["unfinishedTask"] >= 0
                            for e in snapshot.get("recovery", [])
                        )
                    ):
                        measurement = "NOT_APPLICABLE"
                    specific = {
                        "coverage": "percent",
                        "mappingCoverage": "percent",
                        "globalCoverage": "percent",
                        "globalFreeCells": "cells",
                        "observedObstacleCells": "cells",
                        "agentUtilization": "percent",
                        "distance": "steps",
                        "observedCells": "cells",
                        "reachableCells": "cells",
                        "targetsFound": "targets",
                        "targetCount": "targets",
                        "completion": "ratio",
                    }
                    unit = specific.get(
                        name,
                        (
                            "milliunits"
                            if name.startswith("energy")
                            else (
                                "bytes"
                                if name.startswith("bytes")
                                else (
                                    "ticks"
                                    if name.endswith(("Ticks", "Tick"))
                                    else (
                                        "ms"
                                        if name.endswith("Ms")
                                        else (
                                            "ratio"
                                            if name.endswith("Ratio")
                                            or name.endswith("Fraction")
                                            else "count"
                                        )
                                    )
                                )
                            )
                        ),
                    )
                    db.execute(
                        "INSERT OR REPLACE INTO benchmark_results VALUES(?,?,?,?,?)",
                        (run_id, name, value, unit, measurement),
                    )
        if terminal:
            self._last_state.pop(run_id, None)
        else:
            self._last_state[run_id] = snapshot

    def snapshot(self, run_id, tick=None):
        with self.connect() as db:
            limit = tick if tick is not None else 2**31 - 1
            checkpoint = db.execute(
                "SELECT tick,state_blob,state_hash FROM run_snapshots WHERE run_id=? AND schema_version=1 AND tick<=? ORDER BY tick DESC LIMIT 1",
                (run_id, limit),
            ).fetchone()
            if not checkpoint:
                return None
            rows = db.execute(
                "SELECT tick,schema_version,state_blob,state_hash FROM run_snapshots WHERE run_id=? AND tick>? AND tick<=? ORDER BY tick",
                (run_id, checkpoint["tick"], limit),
            ).fetchall()
        result = json.loads(zlib.decompress(checkpoint["state_blob"]))
        for row in rows:
            document = json.loads(zlib.decompress(row["state_blob"]))
            if row["schema_version"] == 1:
                result = document
            elif row["schema_version"] == 2:
                if document["baseTick"] != result["tick"]:
                    raise RuntimeError("Replay delta chain is incomplete")
                result = apply_patch(result, document["patch"])
            else:
                raise RuntimeError("Unsupported replay storage version")
            if result["stateHash"] != row["state_hash"]:
                raise RuntimeError("Replay state hash does not match its record")
        return result

    def series(self, run_id):
        with self.connect() as db:
            sample_count, last_tick = db.execute(
                "SELECT COUNT(*),MAX(tick) FROM metric_samples WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if sample_count:
                stride = max(1, (sample_count + 998) // 999)
                rows = db.execute(
                    "SELECT tick,metrics_json FROM metric_samples WHERE run_id=? AND (tick % ?=0 OR tick=?) ORDER BY tick LIMIT 1000",
                    (run_id, stride, last_tick),
                ).fetchall()
                return [
                    {"tick": row["tick"], **json.loads(row["metrics_json"])}
                    for row in rows
                ]
            count, last = db.execute(
                "SELECT COUNT(*),MAX(tick) FROM run_snapshots WHERE run_id=?", (run_id,)
            ).fetchone()
            stride = max(1, (count + 998) // 999)
            rows = db.execute(
                "SELECT tick,state_blob FROM run_snapshots WHERE run_id=? AND (tick % ? = 0 OR tick=?) ORDER BY tick LIMIT 1000",
                (run_id, stride, last),
            ).fetchall()
        return [
            {"tick": row[0], **json.loads(zlib.decompress(row[1]))["metrics"]}
            for row in rows
        ]

    def agent_series(self, run_id, agent_id):
        with self.connect() as db:
            count, last = db.execute(
                "SELECT COUNT(*),MAX(tick) FROM agent_snapshots WHERE run_id=? AND agent_id=?",
                (run_id, agent_id),
            ).fetchone()
            stride = max(1, (count + 998) // 999)
            rows = db.execute(
                "SELECT tick,metrics_json FROM agent_snapshots WHERE run_id=? AND agent_id=? AND (tick % ? = 0 OR tick=?) ORDER BY tick LIMIT 1000",
                (run_id, agent_id, stride, last),
            ).fetchall()
        result = []
        for tick, measurements in rows:
            values = json.loads(measurements)
            if values:
                result.append({"tick": tick, **values})
                continue
            state = self.snapshot(run_id, tick)
            agent = next((a for a in state["agents"] if a["id"] == agent_id), None)
            if agent:
                result.append(
                    {
                        "tick": tick,
                        "energy": agent["energy"],
                        "energySpent": agent["energySpent"],
                        "distance": agent["distance"],
                        "knownCells": sum(v >= 0 for v in agent["map"]),
                        "pathLength": max(0, len(agent["path"]) - 1),
                        "utilization": agent.get("utilization", 0),
                        "sensedCells": agent.get("sensedCells", 0),
                    }
                )
        return result
