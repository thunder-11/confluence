"""Measure supported envelopes and default API controls on an isolated local server."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.engine import Engine, build_info
from backend.host import host_info, process_memory


def p95(values):
    return sorted(values)[int(0.95 * (len(values) - 1))] if values else None


async def envelopes():
    rows = []
    for size, count in [(16, 1), (16, 16), (32, 8), (64, 4), (128, 1), (128, 16)]:
        engine = await Engine().open()
        try:
            config = {
                "width": size,
                "height": size,
                "agentCount": count,
                "seed": "7",
                "strategy": "adaptive",
                "maxTicks": 100,
                "energy": {"capacity": 100000000},
            }
            result = await engine.call("initialize", config)
            timings = []
            for _ in range(10):
                result = await engine.call("advance", {"ticks": 10})
                timings.extend(m["tickMs"] for m in result["measurements"])
                if result["snapshot"]["status"] != "RUNNING":
                    break
            state = result["snapshot"]
            assert state["metrics"]["collisions"] == 0
            assert state["status"] in {"COMPLETED", "TIMED_OUT", "EXHAUSTED"}
            rows.append(
                {
                    "size": size,
                    "agents": count,
                    "tick": state["tick"],
                    "status": state["status"],
                    "coverage": state["metrics"]["coverage"],
                    "tickP95Ms": p95(timings),
                    **process_memory(engine.process.pid),
                }
            )
        finally:
            await engine.close()
    return rows


def controls(output):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = {
        **os.environ,
        "CONFLUENCE_DB": str(output / f"controls-{int(time.time())}.sqlite3"),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}/api/v1", timeout=120
        ) as client:
            for _ in range(100):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Isolated acceptance server failed to start")
            scenario = client.post(
                "/scenarios/generate",
                json={
                    "name": "Default control acceptance",
                    "config": {
                        "seed": "7",
                        "width": 64,
                        "height": 64,
                        "agentCount": 4,
                        "maxTicks": 1000,
                        "energy": {"capacity": 100000000},
                    },
                },
            )
            scenario.raise_for_status()
            run = client.post("/runs", json={"scenarioId": scenario.json()["id"]})
            run.raise_for_status()
            run_id = run.json()["id"]
            latencies = []
            began = time.perf_counter()
            client.post(
                f"/runs/{run_id}/commands", json={"command": "start", "speed": 20}
            ).raise_for_status()
            while True:
                row = next(r for r in client.get("/runs").json() if r["id"] == run_id)
                if row["tick"] >= 80:
                    break
                time.sleep(0.05)
            throughput = row["tick"] / (time.perf_counter() - began)
            for command in [
                "pause",
                "step",
                "resume",
                "set_speed",
                "pause",
                "step",
                "resume",
                "pause",
                "step",
                "stop",
            ]:
                start = time.perf_counter()
                response = client.post(
                    f"/runs/{run_id}/commands", json={"command": command, "speed": 20}
                )
                response.raise_for_status()
                response.json()
                latencies.append(
                    {
                        "command": command,
                        "acknowledgmentMs": 1000 * (time.perf_counter() - start),
                    }
                )
            return {
                "runId": run_id,
                "database": environment["CONFLUENCE_DB"],
                "configuredTicksPerSecond": 20,
                "observedTicksPerSecond": throughput,
                "controlP95Ms": p95([r["acknowledgmentMs"] for r in latencies]),
                "controlSamples": latencies,
            }
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    output = ROOT / "data" / "acceptance"
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "build": build_info(),
        "referenceMachine": host_info(),
        "envelopes": asyncio.run(envelopes()),
        "controls": controls(output),
    }
    (output / "performance.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
