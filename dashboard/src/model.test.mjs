import test from "node:test";
import assert from "node:assert/strict";
import { changedKeys, parseField, selectedTargets } from "./model.mjs";
test("只提交变化键并保留 false / 0 / 空列表", () => {
  assert.deepEqual(
    changedKeys(
      { enabled: true, size: 10, list: ["a"], untouched: 2 },
      { enabled: false, size: 0, list: [], untouched: 2 },
    ),
    { enabled: false, size: 0, list: [] },
  );
});
test("部分选择不包含其他页且携带版本", () => {
  assert.deepEqual(
    selectedTargets(
      [
        { sticker_id: "a", version: "v1" },
        { sticker_id: "b", version: "v2" },
      ],
      ["a", "old"],
    ),
    [{ sticker_id: "a", version: "v1" }],
  );
});
test("数值与对象拒绝非法文本", () => {
  assert.throws(() => parseField("session_buffer_size", "1e4"));
  assert.throws(() => parseField("will_policy", "{bad}"));
  assert.deepEqual(parseField("allowed_chats", "[]"), []);
});
