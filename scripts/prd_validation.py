"""Durable sequential PRD study: 900 primary runs and 720 independent ablations.

Use --resume after interruption. The frozen binary fingerprint is checked by
every study, so results from different builds cannot silently be combined.
"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.engine import build_info
from backend.host import host_info
from backend.statistics import summarize
from scripts.benchmark import main as study, write_json, ABLATIONS, FAMILIES, STRATEGIES


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def read_results(folder):
    return [
        json.loads(p.read_text(encoding="utf-8"))["result"]
        for p in sorted(folder.glob("run-*.json"))
    ]


def report(output, state):
    primary = read_results(output / "primary")
    paired = {}
    baseline = {
        (r["family"], r["seed"]): r for r in primary if r["strategy"] == "adaptive"
    }
    for ablation in ABLATIONS[1:]:
        rows = read_results(output / ablation)
        by_family = {}
        for family in FAMILIES:
            group = [r for r in rows if r["family"] == family]
            metrics = {}
            for metric in (
                "coverage",
                "completion",
                "distance",
                "energyConsumed",
                "nonproductiveMovement",
                "bytesAttempted",
                "assignmentChurn",
                "progressRecoveryTicks",
                "targetDiscoveryRestrictedTicks",
                "tickP95Ms",
            ):
                differences = [
                    r[metric] - baseline[(family, r["seed"])][metric]
                    for r in group
                    if isinstance(r.get(metric), (int, float))
                    and isinstance(
                        baseline.get((family, r["seed"]), {}).get(metric), (int, float)
                    )
                ]
                metrics[metric] = summarize(differences)
            by_family[family] = metrics
        paired[ablation] = by_family
    write_json(output / "ablation-comparisons.json", paired)
    lines = [
        "# Frozen PRD experiment results",
        "",
        f"Engine SHA-256: `{state['build']['engineSha256']}`.",
        "",
        "All runs execute sequentially with the same frozen scenario for each paired seed. Timing samples and every event are retained in gzip NDJSON files. Each study directory contains its manifest, scenarios, per-run results, metrics CSV and deterministic bootstrap summaries.",
        "",
        "| Family | Strategy | Runs | Completed | Exhausted | Timed out | Failed | Mean coverage |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for family in FAMILIES:
        for strategy in STRATEGIES:
            group = [
                r
                for r in primary
                if r["family"] == family and r["strategy"] == strategy
            ]
            counts = Counter(r["status"] for r in group)
            coverage = [
                r["coverage"]
                for r in group
                if isinstance(r.get("coverage"), (int, float))
            ]
            mean = f"{sum(coverage)/len(coverage):.2f}%" if coverage else "N/A"
            lines.append(
                f"| {family} | {strategy} | {len(group)} | {counts['COMPLETED']} | {counts['EXHAUSTED']} | {counts['TIMED_OUT']} | {counts['FAILED']} | {mean} |"
            )
    lines += [
        "",
        "The primary study uses the required seeds 100–129, 64 × 64 maps, four agents, and a 10,000-tick limit. Earlier correctness debugging used seeds 100–101; this exposure is disclosed rather than presenting the entire set as unseen. The default adaptive weights and switching thresholds were not tuned on these evaluation seeds.",
        "",
        "Four separate 180-run ablations remove the switching weight, both communication weights, the reliability weight, and centralized adaptive coordination. Other sensors, energy, communication, movement safety and planning settings remain identical. The no-switching-weight ablation retains the declared hold period and improvement threshold; it tests the score factor rather than simultaneously changing three mechanisms.",
        "",
        "`ablation-comparisons.json` reports paired ablation-minus-full-adaptive differences with measured sample counts and 95% bootstrap intervals. Missing recovery observations are not zero. Censored and not-applicable counts are included in each study's summaries. Incomplete target discovery uses the common restricted tick limit. Interpret intervals as descriptive evidence; these results do not establish general adaptive superiority.",
        "",
        f"Evidence directory: `{output}`.",
        "",
        "Negative, incomplete and failed outcomes remain in the raw exports. A completed experimental schedule is distinct from acceptance review of correctness and product requirements.",
    ]
    (ROOT / "docs" / "experiment-results.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


async def execute(args):
    build = build_info()
    output = Path(
        args.output or ROOT / "data" / "prd-validation" / build["engineSha256"][:12]
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    state_file = output / "pipeline.json"
    if state_file.exists() and not args.resume:
        raise ValueError(
            "Pipeline already exists; resume explicitly or choose a new directory"
        )
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {
            "createdAt": timestamp(),
            "build": build,
            "referenceMachine": host_info(),
            "plannedPrimaryRuns": 900,
            "plannedAblationRuns": 720,
            "phases": {},
        }
    )
    if state["build"] != build:
        raise ValueError("Frozen pipeline build differs from the current engine")
    state.update(
        status="RUNNING", pid=os.getpid(), updatedAt=timestamp(), output=str(output)
    )
    write_json(state_file, state)
    pointer = ROOT / "data" / "prd-validation" / "current.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        pointer,
        {"pipeline": str(state_file), "pid": os.getpid(), "build": build},
    )
    try:
        if not state["phases"].get("preflight", {}).get("completed"):
            state.update(phase="preflight", updatedAt=timestamp())
            write_json(state_file, state)
            commands = [
                [
                    str(
                        ROOT
                        / "build"
                        / (
                            "confluence_tests.exe"
                            if os.name == "nt"
                            else "confluence_tests"
                        )
                    )
                ],
                [sys.executable, "-m", "pytest", "-q"],
                [
                    "npm.cmd" if os.name == "nt" else "npm",
                    "run",
                    "test:unit",
                    "--prefix",
                    "frontend",
                ],
                [
                    "npm.cmd" if os.name == "nt" else "npm",
                    "run",
                    "build",
                    "--prefix",
                    "frontend",
                ],
                [sys.executable, "scripts/planner_study.py"],
                [sys.executable, "scripts/verify_release.py"],
            ]
            with (output / "preflight.log").open("a", encoding="utf-8") as log:
                for command in commands:
                    log.write(f"\n{timestamp()} {command}\n")
                    log.flush()
                    subprocess.run(
                        command,
                        cwd=ROOT,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
            shutil.copyfile(
                ROOT / "data" / "acceptance" / "performance.json",
                output / "performance.json",
            )
            shutil.copyfile(
                ROOT / "data" / "benchmarks" / "planners" / "results.json",
                output / "planner-study.json",
            )
            state["phases"]["preflight"] = {
                "completed": True,
                "finishedAt": timestamp(),
            }
        for name in ["primary", *ABLATIONS[1:]]:
            if (output / "CANCEL").exists():
                state["status"] = "CANCELLED"
                return
            state.update(phase=name, updatedAt=timestamp())
            write_json(state_file, state)
            folder = output / name
            if state["phases"].get(name, {}).get("completed"):
                continue
            await study(
                SimpleNamespace(
                    output=str(folder),
                    families=",".join(FAMILIES),
                    strategies=(
                        ",".join(STRATEGIES) if name == "primary" else "adaptive"
                    ),
                    seed_start=100,
                    seeds=30,
                    size=64,
                    agents=4,
                    ticks=10000,
                    ablation="none" if name == "primary" else name,
                    tick_batch=10,
                    resume=(folder / "manifest.json").exists(),
                )
            )
            progress = json.loads(
                (folder / "progress.json").read_text(encoding="utf-8")
            )
            if progress["status"] != "COMPLETED":
                state["status"] = progress["status"]
                return
            rows = read_results(folder)
            state["phases"][name] = {
                "completed": True,
                "runs": len(rows),
                "statuses": dict(Counter(r["status"] for r in rows)),
                "collisions": sum(r.get("collisions", 0) for r in rows),
                "finishedAt": timestamp(),
            }
            write_json(state_file, state)
        report(output, state)
        state.update(
            status="AWAITING_ACCEPTANCE_REVIEW", phase="review", finishedAt=timestamp()
        )
    except BaseException as error:
        state.update(
            status=(
                "INTERRUPTED"
                if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError))
                else "FAILED"
            ),
            error=str(error),
            updatedAt=timestamp(),
        )
        raise
    finally:
        write_json(state_file, state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--resume", action="store_true")
    asyncio.run(execute(parser.parse_args()))
