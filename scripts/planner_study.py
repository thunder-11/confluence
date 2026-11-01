"""Run native spatial/CBS studies separately from allocation comparisons."""

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.engine import engine_path, build_info
from backend.host import host_info
from backend.statistics import summarize

if __name__ == "__main__":
    output = ROOT / "data" / "benchmarks" / "planners"
    output.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(engine_path()), "--planner-study"],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    raw = json.loads(completed.stdout)
    rows = raw["spatial"]
    # Pair seed-level means rather than treating correlated queries as independent seeds.
    grouped = {
        size: {
            seed: [r for r in rows if r["size"] == size and r["seed"] == seed]
            for seed in range(100, 130)
        }
        for size in (16, 32, 64, 128)
    }
    summary = {
        str(size): {
            name: summarize(
                [sum(r[name] for r in group) / len(group) for group in seeds.values()]
            )
            for name in ("bfsExpanded", "astarExpanded", "bfsMs", "astarMs")
        }
        for size, seeds in grouped.items()
    }
    result = {
        "build": build_info(),
        "referenceMachine": host_info(),
        "raw": raw,
        "summary": summary,
        "claim": "Static known-graph path subproblems only; no exploration optimality claim.",
    }
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"Saved {len(rows)} paired spatial queries and {len(raw['cbs'])} CBS/oracle fixtures to {output}"
    )
