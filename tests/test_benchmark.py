import asyncio
import gzip
import json
from types import SimpleNamespace

import pytest

from scripts.benchmark import main, ablation_config, analyze


def test_headless_batch_retains_all_tick_samples_and_supports_safe_resume(tmp_path):
    args = SimpleNamespace(
        output=str(tmp_path),
        families="normal",
        strategies="independent,adaptive",
        seed_start=100,
        seeds=1,
        size=16,
        agents=2,
        ticks=10,
        ablation="none",
        tick_batch=10,
        resume=False,
    )
    asyncio.run(main(args))
    for strategy in ("independent", "adaptive"):
        result = json.loads((tmp_path / f"run-normal-100-{strategy}.json").read_text())
        assert result["result"]["ticks"] == 10
        with gzip.open(
            tmp_path / result["timingsFile"], "rt", encoding="utf-8"
        ) as handle:
            assert [json.loads(line)["tick"] for line in handle] == list(range(1, 11))
        with gzip.open(
            tmp_path / result["eventsFile"], "rt", encoding="utf-8"
        ) as handle:
            events = [json.loads(line) for line in handle]
            assert any(e["type"] == "initialized" for e in events)
            assert any(e["type"] == "terminal" for e in events)
    args.resume = True
    asyncio.run(main(args))
    assert json.loads((tmp_path / "progress.json").read_text())["completed"] == 2
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["build"]["engineSha256"] = "changed"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="changed manifest or engine"):
        asyncio.run(main(args))


def test_ablation_parameters_are_explicit_and_do_not_mutate_the_frozen_scenario():
    base = {
        "adaptiveWeights": {
            "switching": -300,
            "reliability": 1000,
            "communication": 1000,
            "communicationCost": -300,
        }
    }
    assert ablation_config(base, "no-switching")["adaptiveWeights"]["switching"] == 0
    assert (
        ablation_config(base, "no-communication")["adaptiveWeights"][
            "communicationCost"
        ]
        == 0
    )
    assert (
        ablation_config(base, "no-reliability")["adaptiveWeights"]["reliability"] == 0
    )
    assert (
        ablation_config(base, "no-centralized")["adaptiveCoordinatorEnabled"] is False
    )
    assert base["adaptiveWeights"]["switching"] == -300


def test_censored_summaries_do_not_turn_missing_recovery_into_zero():
    rows = [
        {
            "family": "failure",
            "seed": 100,
            "strategy": "adaptive",
            "status": "TIMED_OUT",
            "progressRecoveryTicks": None,
            "progressRecoveryTicksMeasurementStatus": "CENSORED",
        }
    ]
    stats = analyze(rows, ["failure"], ["adaptive"])["failure/adaptive"]["metrics"][
        "progressRecoveryTicks"
    ]
    assert stats["n"] == 0 and stats["censored"] == 1 and "mean" not in stats
