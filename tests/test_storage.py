import copy
import json
import zlib
import pytest
from backend.deltas import difference, apply_patch
from backend.store import Store
from test_engine import execute


@pytest.mark.parametrize(
    "before,after",
    [
        ({"cells": [0, 0, 1, -1]}, {"cells": [0, 1, 1, 0]}),
        (
            {"nested": {"remove": 1, "stay": True}},
            {"nested": {"stay": False, "add": None}},
        ),
        (
            [{"id": 0, "path": [1, 2, 3]}],
            [{"id": 0, "path": [1, 4]}, {"id": 1, "path": []}],
        ),
        ({"flag": 0}, {"flag": False}),
        ([1, 0, True], [1, False, 1]),
        ([1, 2, 3], []),
        (None, {"new": [1, 2]}),
    ],
)
def test_lossless_structural_patches(before, after):
    patch = difference(before, after)
    actual = apply_patch(copy.deepcopy(before), json.loads(json.dumps(patch)))
    assert json.dumps(actual, sort_keys=True) == json.dumps(after, sort_keys=True)


def test_real_engine_replay_across_checkpoint_boundary(tmp_path):
    width, height = 64, 16
    cells = [1] * (width * height)
    for x in range(1, width - 1):
        cells[width + x] = 0
    config = {
        "width": width,
        "height": height,
        "agentCount": 1,
        "targetCount": 0,
        "map": cells,
        "targets": [0] * len(cells),
        "starts": [{"agentId": 0, "x": 1, "y": 1}],
        "chargingStations": [{"id": "s", "x": 1, "y": 1}],
        "sensorRadius": 1,
        "strategy": "independent",
        "energy": {"capacity": 100000000},
        "maxTicks": 1000,
    }
    _, states, events = execute(config, 100)
    assert states[-1]["tick"] > 50
    store = Store(tmp_path / "replay.sqlite3")
    store.execute("INSERT INTO scenarios(id,name) VALUES('s','corridor')")
    store.execute("INSERT INTO simulation_runs(id,scenario_id) VALUES('r','s')")
    store.execute("INSERT INTO agents VALUES('r',0,1,1,100000000,100000000,'{}')")
    for state in states:
        store.save_tick("r", state, [e for e in events if e["tick"] == state["tick"]])
    versions = store.query(
        "SELECT tick,schema_version FROM run_snapshots ORDER BY tick"
    )
    assert any(row["schema_version"] == 2 for row in versions)
    assert next(row for row in versions if row["tick"] == 50)["schema_version"] == 1
    for expected in states:
        assert store.snapshot("r", expected["tick"]) == expected
    assert store.snapshot("r") == states[-1]
    assert len(store.series("r")) == len(states)


def test_legacy_full_snapshots_remain_readable(tmp_path):
    store = Store(tmp_path / "legacy.sqlite3")
    store.execute("INSERT INTO scenarios(id,name) VALUES('s','old')")
    store.execute("INSERT INTO simulation_runs(id,scenario_id) VALUES('r','s')")
    state = {
        "tick": 3,
        "stateHash": "legacy",
        "metrics": {"coverage": 42},
        "agents": [],
    }
    store.execute(
        "INSERT INTO run_snapshots VALUES(?,?,?,?,?)",
        ("r", 3, 1, zlib.compress(json.dumps(state).encode()), "legacy"),
    )
    assert store.snapshot("r", 3) == state
    assert store.series("r") == [{"tick": 3, "coverage": 42}]


def test_restart_preserves_committed_state_and_marks_interrupted_work(tmp_path):
    path = tmp_path / "restart.sqlite3"
    store = Store(path)
    store.execute("INSERT INTO scenarios(id,name) VALUES('s','restart')")
    store.execute("INSERT INTO experiment_batches(id,status) VALUES('b','RUNNING')")
    store.execute(
        "INSERT INTO simulation_runs(id,scenario_id,batch_id,status) VALUES('r','s','b','RUNNING')"
    )
    state = {
        "tick": 0,
        "stateHash": "checkpoint",
        "width": 16,
        "metrics": {"coverage": 1},
        "agents": [],
        "targets": [],
    }
    store.save_tick("r", state, [], "RUNNING")
    reopened = Store(path)
    assert reopened.snapshot("r", 0) == state
    assert reopened.query(
        "SELECT status,termination_reason FROM simulation_runs", one=True
    ) == {"status": "FAILED", "termination_reason": "SERVER_RESTART"}
    assert (
        reopened.query("SELECT status FROM experiment_batches", one=True)["status"]
        == "INTERRUPTED"
    )
    assert (
        reopened.query("SELECT type,payload_json FROM events", one=True)["type"]
        == "terminal"
    )
    assert (
        reopened.query("SELECT schema_version FROM run_snapshots", one=True)[
            "schema_version"
        ]
        == 1
    )
    assert (
        reopened.query("SELECT metric_name FROM benchmark_results", one=True)[
            "metric_name"
        ]
        == "coverage"
    )
