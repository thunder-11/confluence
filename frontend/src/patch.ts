export type StatePatch =
  | { set: unknown }
  | { object: Record<string, StatePatch>; delete?: string[] }
  | { array: Record<string, StatePatch>; length: number };

/** Lossless structural sharing. Never mutate a state already rendered by React. */
export function applyStatePatch(
  state: unknown,
  patch: StatePatch | null,
): unknown {
  if (patch === null) return state;
  if ("set" in patch) return patch.set;
  if ("object" in patch) {
    if (state === null || typeof state !== "object" || Array.isArray(state))
      throw new Error("Object delta requires an object base");
    const result = { ...(state as Record<string, unknown>) };
    for (const key of patch.delete || []) delete result[key];
    for (const [key, value] of Object.entries(patch.object))
      result[key] = applyStatePatch(result[key], value);
    return result;
  }
  if (!Array.isArray(state))
    throw new Error("Array delta requires an array base");
  const result = state.slice(0, patch.length);
  result.length = patch.length;
  for (const [key, value] of Object.entries(patch.array)) {
    const index = Number(key);
    if (!Number.isInteger(index) || index < 0 || index >= patch.length)
      throw new Error("Invalid array delta index");
    result[index] = applyStatePatch(result[index], value);
  }
  return result;
}
