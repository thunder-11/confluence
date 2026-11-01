"""Build with CMake and an available native compiler, or pip-installed Zig."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import hashlib
import json
import platform

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
build = ROOT / "build"
build.mkdir(exist_ok=True)
compiler = next(
    (shutil.which(c) for c in ("g++", "clang++", "cl") if shutil.which(c)), None
)
cmake = shutil.which("cmake") or str(Path(sys.executable).parent / "cmake.exe")
if compiler and Path(cmake).exists():
    subprocess.run(
        [cmake, "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"], check=True
    )
    subprocess.run([cmake, "--build", "build", "--config", "Release"], check=True)
else:
    import ziglang

    zig = Path(ziglang.__file__).parent / ("zig.exe" if os.name == "nt" else "zig")
    for source, name in (
        ("engine/src/main.cpp", "confluence_engine"),
        ("engine/tests/tests.cpp", "confluence_tests"),
    ):
        target = build / (name + (".exe" if os.name == "nt" else ""))
        subprocess.run(
            [
                str(zig),
                "c++",
                "-std=c++20",
                "-O2",
                "-DNDEBUG",
                "-Iengine/include",
                "-Iengine/vendor",
                source,
                "-o",
                str(target),
            ],
            check=True,
        )
binary = next(
    p
    for p in (
        build / "confluence_engine.exe",
        build / "confluence_engine",
        build / "Release" / "confluence_engine.exe",
    )
    if p.exists()
)
info = {
    "engineVersion": "confluence-1.0.0",
    "engineSha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "buildConfiguration": "Release",
    "compiler": compiler or "Zig 0.15.2 C++ (Clang)",
    "platform": platform.platform(),
}
(build / "build-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
print("Engine and tests built in", build)
