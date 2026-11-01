import importlib
import io
import json
import zipfile
import time
import pytest
from fastapi.testclient import TestClient
from backend.models import ScenarioConfig


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DB", str(tmp_path / "test.sqlite3"))
    from backend import main

    main = importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def generate(client):
    response = client.post(
        "/api/v1/scenarios/generate",
        json={
            "name": "Test rooms",
            "config": {
                "width": 16,
                "height": 16,
                "agentCount": 2,
                "maxTicks": 50,
                "energy": {"capacity": 10000000},
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_validation(client):
    r = client.post("/api/v1/scenarios/generate", json={"config": {"width": 2}})
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_CONFIGURATION"
    assert client.get("/api/v1/runs/missing").status_code == 404


def test_lifecycle_persistence_and_replay(client):
    s = generate(client)
    r = client.post("/api/v1/runs", json={"scenarioId": s["id"]}).json()
    id = r["id"]
    assert (
        client.post(
            f"/api/v1/runs/{id}/commands", json={"command": "pause"}
        ).status_code
        == 409
    )
    step = client.post(f"/api/v1/runs/{id}/commands", json={"command": "step"})
    assert step.status_code == 200, step.text
    assert step.json()["snapshot"]["tick"] == 1
    saved = client.get(f"/api/v1/runs/{id}/snapshot?tick=1").json()
    assert saved["stateHash"] == step.json()["snapshot"]["stateHash"]
    assert client.get(f"/api/v1/runs/{id}/snapshot?tick=0").json()["tick"] == 0
    assert (
        client.post(
            f"/api/v1/runs/{id}/faults",
            json={"type": "agent_failure", "tick": 2, "agentId": 0},
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/runs/{id}/commands", json={"command": "step"}).json()[
            "snapshot"
        ]["agents"][0]["status"]
        == "FAILED"
    )
    fresh = client.post(f"/api/v1/runs/{id}/commands", json={"command": "reset"}).json()
    assert fresh["id"] != id
    assert fresh["snapshot"]["tick"] == 0
    reset_id = fresh["id"]
    for _ in range(2):
        reset_state = client.post(
            f"/api/v1/runs/{reset_id}/commands", json={"command": "step"}
        ).json()["snapshot"]
    assert (
        reset_state["agents"][0]["status"] == "ACTIVE"
    ), "Reset must discard interactive fault injections"


def test_websocket_initial_snapshot(client):
    s = generate(client)
    r = client.post("/api/v1/runs", json={"scenarioId": s["id"]}).json()
    with client.websocket_connect(f"/api/v1/runs/{r['id']}/stream") as socket:
        item = socket.receive_json()
        assert item["schemaVersion"] == 1
        assert item["payload"]["snapshot"]["tick"] == 0


def test_websocket_deltas_reconstruct_authoritative_snapshots(client):
    from backend.deltas import apply_patch
    import copy

    scenario = generate(client)
    run = client.post("/api/v1/runs", json={"scenarioId": scenario["id"]}).json()
    with client.websocket_connect(f"/api/v1/runs/{run['id']}/stream") as socket:
        initial = socket.receive_json()
        reconstructed = initial["payload"]["snapshot"]
        sequence = initial["sequence"]
        for _ in range(3):
            stepped = client.post(
                f"/api/v1/runs/{run['id']}/commands", json={"command": "step"}
            ).json()
            delta = socket.receive_json()
            assert delta["type"] == "delta"
            assert delta["payload"]["baseSequence"] == sequence
            assert delta["sequence"] == sequence + 1
            reconstructed = apply_patch(
                copy.deepcopy(reconstructed), delta["payload"]["patch"]
            )
            sequence = delta["sequence"]
            assert reconstructed == stepped["snapshot"]


def test_custom_map_rejects_overlapping_starts():
    with pytest.raises(ValueError):
        ScenarioConfig(
            width=16,
            height=16,
            agentCount=2,
            map=[0] * 256,
            starts=[{"agentId": 0, "x": 1, "y": 1}, {"agentId": 1, "x": 1, "y": 1}],
            chargingStations=[{"id": "s", "x": 1, "y": 1}],
        )


def test_summarize_small_samples():
    from backend.main import summarize

    r = summarize([1, 2, 3])
    assert r["mean"] == 2 and r["n"] == 3 and r["ci95"][0] <= 2 <= r["ci95"][1]


def test_sequential_experiment_and_export(client):
    s = generate(client)
    response = client.post(
        "/api/v1/experiments",
        json={"scenarioId": s["id"], "seeds": ["100"], "maxTicks": 8},
    )
    assert response.status_code == 201, response.text
    id = response.json()["id"]
    for _ in range(100):
        result = client.get(f"/api/v1/experiments/{id}").json()
        if result["status"] != "RUNNING":
            break
        time.sleep(0.03)
    assert result["status"] == "COMPLETED", result
    assert len(result["runs"]) == 5
    assert all(r["metrics"]["collisions"] == 0 for r in result["runs"])
    export = client.get(f"/api/v1/experiments/{id}/export")
    assert export.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        assert {"manifest.json", "results.json", "metrics.csv"} <= set(
            archive.namelist()
        )
        assert len([n for n in archive.namelist() if n.startswith("events/")]) == 5
    hashes = []
    for run in result["runs"]:
        initial = client.get(f"/api/v1/runs/{run['id']}/snapshot?tick=0").json()
        hashes.append(initial["truth"])
    assert all(h == hashes[0] for h in hashes)
    assert (
        client.post(
            f"/api/v1/runs/{result['runs'][0]['id']}/commands",
            json={"command": "reset"},
        ).status_code
        == 409
    )


def test_cancelled_batch_keeps_evidence_and_releases_the_slot(client):
    scenario = generate(client)
    result = client.post(
        "/api/v1/experiments",
        json={
            "scenarioId": scenario["id"],
            "seeds": ["100", "101"],
            "maxTicks": 100000,
        },
    ).json()
    batch_id = result["id"]
    assert client.post(f"/api/v1/experiments/{batch_id}/cancel").status_code == 200
    for _ in range(100):
        state = client.get(f"/api/v1/experiments/{batch_id}").json()
        if all(
            r["status"] in {"STOPPED", "COMPLETED", "TIMED_OUT", "EXHAUSTED", "FAILED"}
            for r in state["runs"]
        ):
            created = client.post("/api/v1/runs", json={"scenarioId": scenario["id"]})
            if created.status_code == 201:
                break
        time.sleep(0.02)
    else:
        pytest.fail("Cancelled batch did not release the execution slot")
    assert state["status"] == "CANCELLED" and len(state["runs"]) < 10
    evidence = client.get(f"/api/v1/experiments/{batch_id}/export")
    assert evidence.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(evidence.content)).testzip() is None


def test_disconnected_components_need_confirmation_even_with_two_starts(client):
    cells = [1] * 256
    cells[17] = 0
    cells[238] = 0
    config = {
        "width": 16,
        "height": 16,
        "agentCount": 2,
        "map": cells,
        "targetCount": 0,
        "starts": [{"agentId": 0, "x": 1, "y": 1}, {"agentId": 1, "x": 14, "y": 14}],
        "chargingStations": [
            {"id": "a", "x": 1, "y": 1},
            {"id": "b", "x": 14, "y": 14},
        ],
    }
    assert client.post("/api/v1/scenarios", json={"config": config}).status_code == 422
    config["allowDisconnected"] = True
    assert client.post("/api/v1/scenarios", json={"config": config}).status_code == 201


def test_engine_failure_releases_execution_slot(client, monkeypatch):
    from backend import main

    s = generate(client)
    run = client.post("/api/v1/runs", json={"scenarioId": s["id"]}).json()
    id = run["id"]
    original = main.runs[id].engine.call

    async def broken(kind, payload=None):
        if kind == "advance":
            raise RuntimeError("injected process failure")
        return await original(kind, payload)

    monkeypatch.setattr(main.runs[id].engine, "call", broken)
    assert (
        client.post(f"/api/v1/runs/{id}/commands", json={"command": "step"}).status_code
        == 503
    )
    assert client.get(f"/api/v1/runs/{id}").json()["status"] == "FAILED"
    assert client.post("/api/v1/runs", json={"scenarioId": s["id"]}).status_code == 201


def test_stopped_saved_run_can_reset_after_registry_eviction(client):
    from backend import main

    s = generate(client)
    run = client.post("/api/v1/runs", json={"scenarioId": s["id"]}).json()
    id = run["id"]
    client.post(f"/api/v1/runs/{id}/commands", json={"command": "stop"})
    main.runs.pop(id)
    response = client.post(f"/api/v1/runs/{id}/commands", json={"command": "reset"})
    assert response.status_code == 200, response.text
    assert response.json()["id"] != id


def test_event_filters_and_agent_history(client):
    s = generate(client)
    run = client.post("/api/v1/runs", json={"scenarioId": s["id"]}).json()
    id = run["id"]
    for _ in range(3):
        client.post(f"/api/v1/runs/{id}/commands", json={"command": "step"})
    events = client.get(
        f"/api/v1/runs/{id}/events?recent=true&category=communication&limit=5"
    ).json()
    assert all("agentId" in e and "payload_json" not in e for e in events)
    replay_events = client.get(
        f"/api/v1/runs/{id}/events?throughTick=0&recent=true"
    ).json()
    assert replay_events and all(e["tick"] == 0 for e in replay_events)
    assert client.get(f"/api/v1/runs/{id}/events?category=invalid").status_code == 422
    history = client.get(f"/api/v1/runs/{id}/agents/0/metrics").json()["series"]
    assert history[0]["tick"] == 0 and history[-1]["tick"] == 3


def test_database_connections_close_and_history_is_bounded(tmp_path):
    import sqlite3, zlib
    from backend.store import Store

    store = Store(tmp_path / "bounded.sqlite3")
    with store.connect() as db:
        db.execute("INSERT INTO scenarios(id,name) VALUES('s','s')")
        db.execute("INSERT INTO simulation_runs(id,scenario_id) VALUES('r','s')")
        blob = zlib.compress(json.dumps({"metrics": {"coverage": 0}}).encode())
        db.executemany(
            "INSERT INTO run_snapshots VALUES(?,?,?,?,?)",
            (("r", i, 1, blob, "hash") for i in range(10001)),
        )
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")
    series = store.series("r")
    assert (
        len(series) <= 1000 and series[0]["tick"] == 0 and series[-1]["tick"] == 10000
    )


def test_simultaneous_creation_allows_only_one_active_run(client):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    s = generate(client)
    barrier = threading.Barrier(2)

    def create():
        barrier.wait()
        return client.post("/api/v1/runs", json={"scenarioId": s["id"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: create(), range(2)))
    assert sorted(statuses) == [201, 409]


def test_pause_wakes_the_scheduler_without_waiting_for_speed_interval():
    import asyncio
    from backend.main import Run

    async def check():
        run = Run("test", None, {"snapshot": {}}, {})
        advanced = asyncio.Event()

        async def advance():
            advanced.set()

        run.advance = advance
        run.speed = 1
        run.state = "RUNNING"
        run.task = asyncio.create_task(run.loop())
        await advanced.wait()
        await asyncio.sleep(0)
        run.state = "PAUSED"
        await asyncio.wait_for(run.cancel_loop(), timeout=0.25)

    asyncio.run(check())


def test_next_tick_fault_is_resolved_under_the_tick_lock(client):
    s = generate(client)
    run = client.post("/api/v1/runs", json={"scenarioId": s["id"]}).json()
    id = run["id"]
    for _ in range(3):
        client.post(f"/api/v1/runs/{id}/commands", json={"command": "step"})
    response = client.post(
        f"/api/v1/runs/{id}/faults",
        json={"type": "agent_failure", "tick": 1, "agentId": 0, "nextTick": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["fault"]["tick"] == 4
    state = client.post(f"/api/v1/runs/{id}/commands", json={"command": "step"}).json()[
        "snapshot"
    ]
    assert state["agents"][0]["status"] == "FAILED"
