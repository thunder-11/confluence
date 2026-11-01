from backend.measurements import normalize_measurement


def test_partly_recovered_run_is_censored_instead_of_a_success_only_average():
    state = {
        "recovery": [
            {"unfinishedTask": 1, "progressTicks": 4},
            {"unfinishedTask": 2, "progressTicks": None},
        ]
    }
    assert normalize_measurement("progressRecoveryTicks", 4, state) == (
        None,
        "CENSORED",
    )


def test_no_work_and_no_denominator_are_not_zero_or_false_censoring():
    state = {
        "recovery": [{"unfinishedTask": -1, "progressTicks": None, "detectionTicks": 5}]
    }
    assert normalize_measurement("progressRecoveryTicks", None, state) == (
        None,
        "NOT_APPLICABLE",
    )
    assert normalize_measurement("failureDetectionTicks", 5, state) == (5, "MEASURED")
    assert normalize_measurement("energyPerObservedFreeCell", None, state) == (
        None,
        "NOT_APPLICABLE",
    )
    assert normalize_measurement("explorationCompletionTick", None, state) == (
        None,
        "CENSORED",
    )
