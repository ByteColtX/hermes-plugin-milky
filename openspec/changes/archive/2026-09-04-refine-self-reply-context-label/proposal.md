## Why

当前 Milky 入站消息在给 Agent 的单行 header 中始终展示引用消息的数字 ID，即使
`reply.data.sender_id` 已确认该消息来自 Bot。这个数字对 Agent 的语义帮助有限，而
`your_previous_msg` 能直接表达“用户正在引用我之前的消息”；同时，真实 ID 仍需要保留在
Hermes 内部字段中，供现有引用上下文和其他边界使用。

## What Changes

- 当前 trigger 消息和 wait 历史消息的 Agent-facing header，在实际引用目标是 Bot 时将
  `reply_to <message_seq>` 展示为 `reply_to your_previous_msg`。
- 保留当前消息自身的 `msg_id` 展示和内部真实消息 ID；`MessageEvent.reply_to_message_id`
  继续使用 Milky 的真实引用 `message_seq`，不改 Hermes 内部引用语义。
- 当引用目标不是 Bot 时，继续展示 `reply_to <message_seq>`，不改变普通用户互引行为。
- 只有被实际渲染的引用目标确认 `sender_id == self_id` 时才使用该文案；不得从 Bot 名称、
  正文、嵌套 mention 或其他 reply 推断目标。
- 不改变 canonical、dedup、Gate、Will、资源查询、出站 reply 或 `reply_to_is_own_message`
  的既有行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `chat-session-buffer`: 修改 Agent-facing 普通消息历史/current header 中自引用消息的
  `reply_to` 展示规则，并保持普通他人引用、字段顺序、转义和上下文边界不变。

## Impact

- 影响入站 header renderer、current MessageEvent 映射和历史 context renderer 的安全视图，
  以及对应的单元和 pipeline 集成测试。
- 不新增 Milky Action、网络请求、配置项、依赖或 Hermes core 修改。
- 现有依赖真实数字 `reply_to_message_id` 的 Hermes 引用正文注入、日志和出站边界继续获得
  原始 `message_seq`；只有交给 Agent 的 `text`/`channel_context` 展示标签发生变化。
