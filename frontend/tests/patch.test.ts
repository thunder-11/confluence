import assert from "node:assert/strict";
import { test } from "node:test";
import { applyStatePatch } from "../src/patch.ts";

test("delta preserves immutable nested state and exact scalar types", () => {
  const before = {
    tick: 0,
    cells: [0, -1, 1],
    agent: { active: 0, remove: 1 },
  };
  const after = applyStatePatch(before, {
    object: {
      tick: { set: 1 },
      cells: { array: { "1": { set: 0 } }, length: 2 },
      agent: { object: { active: { set: false } }, delete: ["remove"] },
    },
  });
  assert.deepEqual(after, { tick: 1, cells: [0, 0], agent: { active: false } });
  assert.deepEqual(before, {
    tick: 0,
    cells: [0, -1, 1],
    agent: { active: 0, remove: 1 },
  });
});
test("delta rejects invalid bases and indices instead of fabricating state", () => {
  assert.throws(() => applyStatePatch(null, { object: { tick: { set: 1 } } }));
  assert.throws(() =>
    applyStatePatch([], { array: { "-1": { set: 1 } }, length: 2 }),
  );
  assert.equal(applyStatePatch(0, { set: false }), false);
  assert.equal(applyStatePatch("same", null), "same");
});
