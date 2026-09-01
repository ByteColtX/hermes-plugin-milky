---
name: qq-reference
description: Reference for the CQ-compatible `at` and `reply` syntax used in Milky QQ Agent's outbound messages. Use when composing or explaining outbound QQ messages that need to notify a specific user or reply to a specific message, and you need the exact [CQ:at,...] / [CQ:reply,...] format, field order, or usage rules.
---

# Milky QQ CQ reference

本 skill 只说明 Agent 出站的 `at` 和 `reply` 两种 CQ-compatible 语法。它不是 OneBot
v11 协议；不要据此调用 Action 或猜测其他 CQ 能力。

## at

`[CQ:at,qq=<uid>]`

- `qq` 必填，使用当前消息或 `channel_context` 消息头中的真实 `uid`。
- 必须是无前导零的十进制 QQ 号 `10001..4294967295`；不支持 `qq=all`。
- 没有真实 `uid` 时不要从昵称、正文或模糊描述猜测，也不要自动 @ 用户。

## reply

`[CQ:reply,id=<msg_id>]`

- `id` 必填，使用当前消息或 `channel_context` 消息头中的真实 `msg_id`。
- `id` 必须是无前导零的十进制 Milky 消息序号 `0..9007199254740991`；不是时间戳或随机数。
- 没有真实且可转换为数字的 `msg_id` 时不要调用；不会自动引用当前消息。

两者可以组合，顺序会保留，例如：`[CQ:reply,id=9001][CQ:at,qq=10001]正文`。其他或
格式错误的 CQ 片段不会在本参考中获得额外能力。
