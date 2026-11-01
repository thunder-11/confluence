"""Censor aggregate recovery measurements when any applicable episode is unresolved."""

RECOVERY_FIELDS = {
    "failureDetectionTicks": "detectionTicks",
    "assignmentRecoveryTicks": "assignmentTicks",
    "progressRecoveryTicks": "progressTicks",
}


def normalize_measurement(name, value, snapshot):
    if name in RECOVERY_FIELDS:
        episodes = snapshot.get("recovery", [])
        if name != "failureDetectionTicks":
            episodes = [e for e in episodes if e.get("unfinishedTask", -1) >= 0]
        if not episodes:
            return None, "NOT_APPLICABLE"
        field = RECOVERY_FIELDS[name]
        if any(e.get(field) is None for e in episodes):
            return None, "CENSORED"
        return sum(e[field] for e in episodes) / len(episodes), "MEASURED"
    if value is not None:
        return value, "MEASURED"
    return None, "CENSORED" if name == "explorationCompletionTick" else "NOT_APPLICABLE"
