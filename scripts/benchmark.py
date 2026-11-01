"""Run reproducible allocation experiments without the web server or browser."""

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.engine import Engine, build_info
from backend.models import ScenarioConfig
from backend.statistics import summarize
from backend.host import host_info, process_memory
from backend.measurements import normalize_measurement

STRATEGIES = ["independent", "greedy", "hungarian", "decentralized", "adaptive"]
FAMILIES = ["normal", "unknown", "communication", "failure", "dynamic", "resources"]
ABLATIONS = [
    "none",
    "no-switching",
    "no-communication",
    "no-reliability",
    "no-centralized",
]


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def ablation_config(frozen, ablation):
    config = json.loads(json.dumps(frozen))
    weights = config.setdefault("adaptiveWeights", {})
    if ablation == "no-switching":
        weights["switching"] = 0
    if ablation == "no-communication":
        weights.update(communication=0, communicationCost=0)
    if ablation == "no-reliability":
        weights["reliability"] = 0
    if ablation == "no-centralized":
        config["adaptiveCoordinatorEnabled"] = False
    return config


def measurement_status(name, value, state):
    return normalize_measurement(name, value, state)[1]


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
    temporary = output / "metrics.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=identity + metrics)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(output / "metrics.csv")


async def run_case(output, family, seed, strategy, frozen, tick_batch=10):
    event_name = f"events-{family}-{seed}-{strategy}.ndjson.gz"
    engine = await Engine().open()
    samples = []
    stages = {}
    state = None
    error = ""
    memory = {}
    start = time.perf_counter()
    try:
        with gzip.open(
            output / event_name, "wt", encoding="utf-8", compresslevel=1
        ) as events, gzip.open(
            output / f"timings-{family}-{seed}-{strategy}.ndjson.gz",
            "wt",
            encoding="utf-8",
            compresslevel=1,
        ) as timings:
            result = await engine.call("initialize", {**frozen, "strategy": strategy})
            state = result["snapshot"]
            for event in result["events"]:
                events.write(json.dumps(event) + "\n")
            for offset in range(0, frozen["maxTicks"], tick_batch):
                result = await engine.call(
                    "advance", {"ticks": min(tick_batch, frozen["maxTicks"] - offset)}
                )
                state = result["snapshot"]
                for event in result["events"]:
                    events.write(json.dumps(event, separators=(",", ":")) + "\n")
                for sample in result["measurements"]:
                    timings.write(json.dumps(sample, separators=(",", ":")) + "\n")
                    samples.append(sample["tickMs"])
                    for name, value in sample.items():
                        if name != "tick":
                            stages.setdefault(name, []).append(value)
                if state["status"] != "RUNNING":
                    break
    except Exception as exc:
        error = str(exc)
    finally:
        if engine.process:
            memory = process_memory(engine.process.pid)
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
        **memory,
    }
    if state:
        row.update(
            {
                name: normalize_measurement(name, value, state)[0]
                for name, value in state["metrics"].items()
            }
        )
        for name, value in state["metrics"].items():
            if row[name] is None:
                row[name + "MeasurementStatus"] = measurement_status(name, value, state)
        if error:
            row["completion"] = 0
    detail = {
        "result": row,
        "recovery": state.get("recovery", []) if state else [],
        "targets": state.get("targets", []) if state else [],
        "eventsFile": event_name,
        "configSha256": hashlib.sha256(
            json.dumps({**frozen, "strategy": strategy}, sort_keys=True).encode()
        ).hexdigest(),
        "communicationCounters": (
            state.get("communicationCounters", {}) if state else {}
        ),
        "timingsFile": f"timings-{family}-{seed}-{strategy}.ndjson.gz",
        "stageDistributions": {
            name: {
                **summarize(values, bootstrap=False),
                "p95": sorted(values)[int(0.95 * (len(values) - 1))],
                "p99": sorted(values)[int(0.99 * (len(values) - 1))],
            }
            for name, values in stages.items()
        },
    }
    write_json(output / f"run-{family}-{seed}-{strategy}.json", detail)
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
            names = sorted(
                name
                for name in set().union(*(row.keys() for row in group)) - ignored
                if not name.endswith("MeasurementStatus")
            )
            metrics, paired = {}, {}
            for name in names:
                values = [
                    row[name]
                    for row in group
                    if isinstance(row.get(name), (int, float))
                ]
                metrics[name] = {**summarize(values)}
                metrics[name]["censored"] = sum(
                    row.get(name + "MeasurementStatus") == "CENSORED" for row in group
                )
                metrics[name]["notApplicable"] = sum(
                    row.get(name + "MeasurementStatus") == "NOT_APPLICABLE"
                    for row in group
                )
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
                "completionFraction": (
                    sum(row["status"] == "COMPLETED" for row in group) / len(group)
                    if group
                    else None
                ),
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
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        if not args.resume:
            raise ValueError(
                "Output already contains a manifest. Use a new folder or --resume."
            )
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        before = {k: v for k, v in old["parameters"].items() if k != "resume"}
        after = {k: v for k, v in vars(args).items() if k != "resume"}
        if before != after or old["build"] != manifest["build"]:
            raise ValueError("Cannot resume with a changed manifest or engine build")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
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
            frozen = ablation_config(generated["scenario"]["config"], args.ablation)
            (output / f"scenario-{family}-{seed}.json").write_text(
                json.dumps(frozen), encoding="utf-8"
            )
            for strategy in strategies:
                if (output / "CANCEL").exists():
                    write_json(
                        output / "progress.json",
                        {"status": "CANCELLED", "completed": len(rows)},
                    )
                    print(
                        "Cancellation marker found; completed runs are retained.",
                        flush=True,
                    )
                    return
                saved = output / f"run-{family}-{seed}-{strategy}.json"
                if args.resume and saved.exists():
                    rows.append(json.loads(saved.read_text(encoding="utf-8"))["result"])
                else:
                    rows.append(
                        await run_case(
                            output, family, seed, strategy, frozen, args.tick_batch
                        )
                    )
                write_csv(output, rows)
                (output / "progress.json").write_text(
                    json.dumps(
                        {
                            "status": "RUNNING",
                            "completed": len(rows),
                            "planned": len(families) * args.seeds * len(strategies),
                            "last": {
                                k: rows[-1][k]
                                for k in ("family", "seed", "strategy", "status")
                            },
                        }
                    ),
                    encoding="utf-8",
                )
    (output / "summary.json").write_text(
        json.dumps(analyze(rows, families, strategies), indent=2), encoding="utf-8"
    )
    print(f"Saved {len(rows)} measured runs to {output}", flush=True)
    (output / "progress.json").write_text(
        json.dumps(
            {
                "status": "COMPLETED",
                "completed": len(rows),
                "failed": sum(r["status"] == "FAILED" for r in rows),
            }
        ),
        encoding="utf-8",
    )


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
    parser.add_argument("--tick-batch", type=int, default=10, choices=range(1, 11))
    parser.add_argument("--ablation", default="none", choices=ABLATIONS)
    parser.add_argument("--resume", action="store_true")
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
