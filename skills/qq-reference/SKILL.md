---
name: qq-reference
description: Reference for the CQ-compatible `at`, `reply`, and local sticker image syntax used in Milky QQ Agent's outbound messages. Use when composing or explaining outbound QQ messages that need to notify a specific user, reply to a specific message, or send a sticker from a local file URI, and you need the exact CQ format, field order, or usage rules.
---

# Milky QQ CQ reference

本 skill 只说明 Agent 出站的 `at`、`reply` 和 `image` 三种 CQ-compatible 语法。它不是
OneBot v11 协议；不要据此调用 Action 或猜测其他 CQ 能力。

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

## image

- 如需单独发送本地贴纸（sticker），请使用如下 CQ 格式：
  `[CQ:image,file=file:///path/to/sticker.ext,type=sticker]`

- **注意**：
  - `image` 类型的 CQ 码不得与正文或其他 CQ 码混合使用。
  - 普通图片请使用 `MEDIA:<local_path>` 方式发送，**不要**使用 CQ `image`。

# 补充说明

`at` 和 `reply` 可以组合并保留顺序，例如：`[CQ:reply,id=9001][CQ:at,qq=10001]正文`。
`image` 必须单独发送。其他或格式错误的 CQ 片段不会在本参考中获得额外能力。
