"""Run reproducible allocation experiments without the web server or browser."""

import argparse
import asyncio
import csv
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.engine import Engine, build_info
from backend.models import ScenarioConfig
from backend.statistics import summarize
from backend.host import host_info

STRATEGIES = ["independent", "greedy", "hungarian", "decentralized", "adaptive"]
FAMILIES = ["normal", "unknown", "communication", "failure", "dynamic", "resources"]


def family_config(family, seed, size, agents, ticks):
    config = {
        "scenarioFamily": family,
        "width": size,
        "height": size,
        "agentCount": agents,
        "seed": str(seed),
        "maxTicks": ticks,
        "energy": {"capacity": 100000000},
    }
    if family == "unknown":
        config.update(obstacleDensity=0.55, sensorRadius=1)
    if family == "communication":
        config["communication"] = {"delayMaxTicks": 5, "dropProbability": 0.1}
    if family == "resources":
        config["energy"]["capacity"] = 100000
    return ScenarioConfig.model_validate(config).engine_payload()


def write_csv(output, rows):
    identity = ["family", "seed", "strategy", "status", "ticks", "stateHash", "error"]
    metrics = sorted(set().union(*(row.keys() for row in rows)) - set(identity))
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=identity + metrics)
        writer.writeheader()
        writer.writerows(rows)


async def run_case(output, family, seed, strategy, frozen):
    event_name = f"events-{family}-{seed}-{strategy}.ndjson"
    engine = await Engine().open()
    samples = []
    state = None
    error = ""
    start = time.perf_counter()
    try:
        with (output / event_name).open("w", encoding="utf-8") as events:
            result = await engine.call("initialize", {**frozen, "strategy": strategy})
            state = result["snapshot"]
            for event in result["events"]:
                events.write(json.dumps(event) + "\n")
            for _ in range(frozen["maxTicks"]):
                result = await engine.call("advance", {"ticks": 1})
                state = result["snapshot"]
                for event in result["events"]:
                    events.write(json.dumps(event) + "\n")
                samples.append(state["metrics"]["tickMs"])
                if state["status"] != "RUNNING":
                    break
    except Exception as exc:
        error = str(exc)
    finally:
        await engine.close()
    row = {
        "family": family,
        "seed": seed,
        "strategy": strategy,
        "status": "FAILED" if error else state["status"],
        "ticks": state["tick"] if state else 0,
        "stateHash": state["stateHash"] if state else "",
        "error": error,
        "wallSeconds": time.perf_counter() - start,
        "tickP95Ms": (
            sorted(samples)[int(0.95 * (len(samples) - 1))] if samples else None
        ),
    }
    if state:
        row.update(state["metrics"])
        if error:
            row["completion"] = 0
    detail = {
        "result": row,
        "recovery": state.get("recovery", []) if state else [],
        "targets": state.get("targets", []) if state else [],
        "eventsFile": event_name,
    }
    (output / f"run-{family}-{seed}-{strategy}.json").write_text(
        json.dumps(detail, indent=2), encoding="utf-8"
    )
    coverage = row.get("coverage")
    display = f"{coverage:.2f}%" if coverage is not None else "unavailable"
    print(
        f'{family} seed={seed} {strategy}: {row["status"]} '
        f'coverage={display} ticks={row["ticks"]}',
        flush=True,
    )
    return row


def analyze(rows, families, strategies):
    result = {}
    ignored = {"family", "seed", "strategy", "status", "stateHash", "error"}
    for family in families:
        baseline = {
            row["seed"]: row
            for row in rows
            if row["family"] == family and row["strategy"] == "independent"
        }
        for strategy in strategies:
            group = [
                row
                for row in rows
                if row["family"] == family and row["strategy"] == strategy
            ]
            names = sorted(set().union(*(row.keys() for row in group)) - ignored)
            metrics, paired = {}, {}
            for name in names:
                values = [
                    row[name]
                    for row in group
                    if isinstance(row.get(name), (int, float))
                ]
                metrics[name] = summarize(values)
                differences = [
                    row[name] - baseline[row["seed"]][name]
                    for row in group
                    if row["seed"] in baseline
                    and isinstance(row.get(name), (int, float))
                    and isinstance(baseline[row["seed"]].get(name), (int, float))
                ]
                if differences:
                    paired[name] = summarize(differences)
            result[f"{family}/{strategy}"] = {
                "n": len(group),
                "completionFraction": sum(row["status"] == "COMPLETED" for row in group)
                / len(group),
                "failedRuns": sum(row["status"] == "FAILED" for row in group),
                "metrics": metrics,
                "pairedVsIndependent": paired,
            }
    return result


async def main(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    families, strategies = args.families.split(","), args.strategies.split(",")
    manifest = {
        "build": build_info(),
        **host_info(),
        "parameters": vars(args),
        "analysisSeed": 2026,
        "bootstrapResamples": 10000,
        "warmupTicks": 30,
        "claim": "Measured outcomes only; no assumed adaptive improvement.",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    # Development-only warmup is never included in evaluation samples.
    for strategy in strategies:
        warmup = await Engine().open()
        try:
            config = family_config("normal", 0, args.size, args.agents, 30)
            await warmup.call("initialize", {**config, "strategy": strategy})
            for _ in range(3):
                await warmup.call("advance", {"ticks": 10})
        finally:
            await warmup.close()
    rows = []
    for family in families:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            generator = await Engine().open()
            try:
                generated = await generator.call(
                    "initialize",
                    family_config(family, seed, args.size, args.agents, args.ticks),
                )
            finally:
                await generator.close()
            frozen = generated["scenario"]["config"]
            (output / f"scenario-{family}-{seed}.json").write_text(
                json.dumps(frozen), encoding="utf-8"
            )
            for strategy in strategies:
                rows.append(await run_case(output, family, seed, strategy, frozen))
                write_csv(output, rows)
    (output / "summary.json").write_text(
        json.dumps(analyze(rows, families, strategies), indent=2), encoding="utf-8"
    )
    print(f"Saved {len(rows)} measured runs to {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--families", default=",".join(FAMILIES))
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--ticks", type=int, default=10000)
    parser.add_argument("--output", default="data/benchmarks/primary")
    arguments = parser.parse_args()
    for value, allowed in (
        (arguments.families, FAMILIES),
        (arguments.strategies, STRATEGIES),
    ):
        parts = value.split(",")
        if not set(parts) <= set(allowed) or len(parts) != len(set(parts)):
            parser.error("Families and strategies must be distinct supported names")
    if not (
        arguments.seeds >= 1
        and 0 <= arguments.seed_start
        and arguments.seed_start + arguments.seeds <= 2**64
        and 16 <= arguments.size <= 256
        and 1 <= arguments.agents <= 32
        and 1 <= arguments.ticks <= 100000
    ):
        parser.error("Invalid seed range, dimensions, population, or tick limit")
    asyncio.run(main(arguments))
