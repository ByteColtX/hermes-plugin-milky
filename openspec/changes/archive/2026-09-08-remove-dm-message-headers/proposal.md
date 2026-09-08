## Why

当前实现只移除了 dm 历史 `channel_context` 的普通消息 header，但当前触发消息的
`MessageEvent.text` 仍使用 `<sender uid ... msg_id ...>` 格式。Hermes 日志和 Agent 输入因此仍
会在私聊中看到身份 header；预期的私聊体验是普通 dm 消息在当前正文和历史上下文中都不带
Agent-facing header，同时继续保留内部身份和 reply metadata。

## What Changes

- 将普通 dm 当前消息的 `MessageEvent.text` 改为只输出经过既有 body 编码的正文，不再输出
  sender、uid、`msg_id`、`reply_to` 或其他普通消息 header。
- 保持普通 dm 历史 `channel_context` 的 body-only 格式，并让当前消息与历史消息使用一致的
  dm 普通消息 renderer。
- 普通 group 当前消息和历史消息继续使用既有 header、字段顺序和转义行为。
- dm 中的 system event 继续使用 `<event <event_type>> <body>`，以保持事件边界可识别；该
  event header 不属于普通 dm 消息 header。
- 保留 dm 当前消息和历史消息的 canonical、dedup、Gate、Will、真实 Milky message ID、
  Hermes reply metadata、资源解析和媒体字段；仅改变 Agent-facing 普通消息文本。
- **BREAKING**：私聊普通消息不再向 Agent-facing `MessageEvent.text` 或
  `channel_context` 提供 sender、uid、`msg_id`、`reply_to` header 字段。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `chat-session-buffer`：明确 dm 普通历史 body-only，并补充 dm 当前消息不生成普通消息
  header 的稳定契约；group 和 system event 行为保持不变。
- `hermes-message-pipeline`：明确 dm 当前 `MessageEvent.text` 与历史
  `channel_context` 均使用 body-only 普通消息文本，同时保留内部 reply metadata 和当前
  group 文本格式。

## Impact

- 影响 `session.buffer` 的 dm 普通消息渲染选择和 `inbound.hermes_mapper` 的当前消息文本
  组装；`inbound.pipeline` 继续使用 resolved history body。
- 需要补充 dm 当前消息、dm 历史与当前消息混合、dm reply metadata、system event、换行编码
  和 group 不变性的回归测试。
- 需要同步 `ARCHITECTURE.md`、两个主 OpenSpec capability spec 和 change evidence。
- 不改变 Milky Action、SSE、canonical、dedup、Gate、Will、资源下载/缓存、媒体去重或出站
  能力。
