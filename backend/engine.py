import asyncio
from collections import deque
import json
import os
from pathlib import Path
import uuid
import hashlib
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[1]


def engine_path():
    if os.environ.get("CONFLUENCE_ENGINE"):
        return Path(os.environ["CONFLUENCE_ENGINE"])
    for folder in (ROOT / "build", ROOT / "build" / "Release"):
        for name in ("confluence_engine.exe", "confluence_engine"):
            if (folder / name).exists():
                return folder / name
    raise RuntimeError("C++ engine not built. Run: python scripts/build.py")


def build_info():
    path = engine_path()
    return _build_info(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=4)
def _build_info(path, mtime):
    fingerprint = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    file = ROOT / "build" / "build-info.json"
    known = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    if known.get("engineSha256") != fingerprint:
        known = {}
    return {**known, "engineVersion": "confluence-1.0.0", "engineSha256": fingerprint}


class Engine:
    def __init__(self):
        self.process = None
        self.lock = asyncio.Lock()
        self.diagnostics = deque(maxlen=30)
        self.stderr_task = None

    async def open(self):
        self.process = await asyncio.create_subprocess_exec(
            str(engine_path()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=32 * 1024 * 1024,
        )

        async def read_errors():
            while line := await self.process.stderr.readline():
                self.diagnostics.append(line.decode(errors="replace").strip())

        self.stderr_task = asyncio.create_task(read_errors())
        return self

    async def call(self, kind, payload=None):
        async with self.lock:
            request_id = str(uuid.uuid4())
            wire = (
                json.dumps(
                    {
                        "protocolVersion": 1,
                        "requestId": request_id,
                        "type": kind,
                        "payload": payload or {},
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            if len(wire) > 32 * 1024 * 1024:
                raise RuntimeError("Engine request exceeds protocol limit")
            self.process.stdin.write(wire)
            await self.process.stdin.drain()
            line = await asyncio.wait_for(self.process.stdout.readline(), timeout=120)
            if not line:
                raise RuntimeError("Engine exited: " + " ".join(self.diagnostics))
            result = json.loads(line)
            if (
                result.get("requestId") != request_id
                or result.get("protocolVersion") != 1
            ):
                raise RuntimeError("Engine protocol mismatch")
            if result["type"] == "error":
                if result["error"]["code"] == "INVALID_INPUT":
                    raise ValueError(result["error"]["message"])
                raise RuntimeError(result["error"]["message"])
            return result

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                await asyncio.wait_for(self.call("shutdown"), timeout=2)
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except (Exception, asyncio.CancelledError):
                if self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
        if self.stderr_task:
            self.stderr_task.cancel()
