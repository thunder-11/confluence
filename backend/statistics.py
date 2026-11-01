"""Deterministic summaries shared by the HTTP service and headless runner."""

from functools import lru_cache
import random
import statistics


def summarize(values, bootstrap=True):
    return _summarize(tuple(values), bootstrap)


@lru_cache(maxsize=1024)
def _summarize(values, bootstrap):
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    n = len(values)
    if len(set(values)) == 1:
        return {
            "n": n,
            "mean": values[0],
            "stddev": 0,
            "median": values[0],
            "q1": values[0],
            "q3": values[0],
            "iqr": 0,
            "ci95": [values[0], values[0]] if bootstrap else None,
        }
    interval = None
    if bootstrap:
        rng = random.Random(2026)
        samples = sorted(
            statistics.mean(rng.choices(values, k=n)) for _ in range(10000)
        )
        interval = [samples[249], samples[9749]]
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "n": n,
        "mean": statistics.mean(values),
        "stddev": statistics.stdev(values),
        "median": statistics.median(values),
        "q1": quartiles[0],
        "q3": quartiles[2],
        "iqr": quartiles[2] - quartiles[0],
        "ci95": interval,
    }
