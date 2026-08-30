---
name: qq-reference
description: Milky QQ Agent 出站 at 和 reply CQ-compatible 语法参考
---

# Milky QQ CQ reference

本 skill 是 `hermes-plugin-milky:qq-reference` 的只读参考资料，按需加载。CQ-compatible
语法只供 Agent 出站适配层使用，不是 OneBot v11 传输协议，也不会让 Milky 支持任意
OneBot Action、WebSocket RPC 或未注册工具。

## at

`[CQ:at,qq=<uid>]`：在消息中提及一个用户。`<uid>` 必须原样取自当前消息或
`channel_context` 消息头中的 `uid`。没有真实 `uid` 时不要猜测、补造或从昵称和正文推断。

## reply

`[CQ:reply,id=<msg_id>]`：在消息中引用一条消息。`<msg_id>` 必须原样取自当前消息或
`channel_context` 消息头中的 `msg_id`。没有真实 `msg_id` 时不要猜测、补造或从昵称和正文
推断。
