## Why

当前 friend 和 group 的历史 `channel_context` 共用同一套普通消息 header。对于一对一私聊，sender、uid、message ID 和 reply 元信息通常是重复噪音，挤占了 Agent 可读上下文；群聊仍需要这些字段来区分同一群中的多个发送者。现在应将私聊历史上下文与群聊 renderer 解耦，同时保持既有单行编码和群聊行为稳定。实现中至少有 detached batch 属性、资源解析后的 pipeline 组装路径和公开 renderer helper 三个出口，必须一并收敛，否则最终交给 Hermes 的内容会与直接访问结果不一致。

## What Changes

- 为私聊历史普通消息定义独立的 `channel_context` renderer：每条记录只输出经过现有正文转义规则处理的 `body`，不生成普通消息 header。
- 让 `DetachedTriggerBatch.channel_context`、pipeline 的 `_render_resolved_history()`、公开的 `render_channel_context()` 及其有序合并路径使用同一套已确认 chat namespace 选择规则；资源解析后的 pipeline 路径继续使用解析后的正文。
- 私聊历史仍按 ingress sequence 排序，并以换行拼接为多条单行记录；空历史继续返回 `None`。
- 私聊中的 context-only system event 继续使用现有 `<event <event_type>> <body>` 格式，不与普通私聊正文混淆。
- 群聊历史 `channel_context` 的 renderer、字段顺序、转义规则和输出格式保持不变；不引入 timestamp。
- 当前 trigger 的 `MessageEvent.text` 保持现有 renderer，不因本 change 改变私聊当前消息、reply metadata、canonical、dedup、Gate、Will 或资源解析行为。
- **BREAKING**：私聊历史普通消息不再向 Agent-facing `channel_context` 提供 sender、uid、`msg_id` 或 `reply_to` header 字段；这些字段仍保留在 canonical 和当前消息的内部/事件 metadata 中。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `chat-session-buffer`：区分 group 与 dm 的历史普通消息渲染；dm 记录只保留转义后的正文，system context 和顺序/空值语义不变。
- `hermes-message-pipeline`：明确当前 `MessageEvent.text` 继续使用现有单行 header，而 dm 历史 `channel_context` 使用 body-only 记录。

## Impact

- 影响入站历史上下文的 renderer 选择、detached batch 属性、资源解析后的 pipeline 映射和公开 `render_channel_context()` API 边界；`render_ordered_context()` 继续负责普通历史与 system event 的有序合并。
- 需要补充 dm wait/trigger、dm 普通历史与 system context 混排、换行转义、空历史和 group 不变性的回归测试。
- 需要同步更新 `ARCHITECTURE.md` 及相关主规范，避免继续把所有 chat 的 `channel_context` 描述为同一套普通消息 header。
- 不改变 Milky 协议解析、canonical 字段、资源下载/缓存边界、Hermes reply metadata、群聊输出或任何远端 Action。
