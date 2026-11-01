"""Versioned, lossless structural deltas for replay checkpoints.

Patch tags belong to the storage envelope, never to simulation state. Array
indices are explicit so occupancy-grid edits remain small between checkpoints.
"""


def difference(previous, current):
    if isinstance(previous, dict) and isinstance(current, dict):
        changes = {}
        for key, value in current.items():
            patch = (
                difference(previous[key], value) if key in previous else {"set": value}
            )
            if patch is not None:
                changes[key] = patch
        result = {"object": changes}
        removed = sorted(previous.keys() - current.keys())
        if removed:
            result["delete"] = removed
        return result if changes or removed else None
    if isinstance(previous, list) and isinstance(current, list):
        changes = {}
        for index, value in enumerate(current):
            if (
                index < len(previous)
                and not isinstance(value, (dict, list))
                and type(previous[index]) is type(value)
                and previous[index] == value
            ):
                continue
            patch = (
                difference(previous[index], value)
                if index < len(previous)
                else {"set": value}
            )
            if patch is not None:
                changes[str(index)] = patch
        if len(current) > 32 and len(changes) > len(current) // 3:
            return {"set": current}
        return (
            {"array": changes, "length": len(current)}
            if changes or len(previous) != len(current)
            else None
        )
    if type(previous) is type(current) and previous == current:
        return None
    return {"set": current}


def apply_patch(state, patch):
    if patch is None:
        return state
    if "set" in patch:
        return patch["set"]
    if "object" in patch:
        for key in patch.get("delete", []):
            state.pop(key, None)
        for key, change in patch["object"].items():
            state[key] = apply_patch(state.get(key), change)
        return state
    if "array" in patch:
        length = patch["length"]
        del state[length:]
        if len(state) < length:
            state.extend([None] * (length - len(state)))
        for index, change in patch["array"].items():
            i = int(index)
            state[i] = apply_patch(state[i], change)
        return state
    raise ValueError("Unsupported replay patch")
