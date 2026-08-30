---
name: qq-tools
description: Milky QQ Agent 显式 ToolSpec 参考：名片点赞、好友/群戳一戳、群消息撤回、群信息与成员查询、群成员禁言和全员禁言；说明 operationId、参数、权限、目标和副作用边界。
metadata:
  short-description: Milky QQ 工具参数、权限与调用边界
  keywords: "Milky, QQ, Hermes, ToolSpec, operationId, 好友, 群聊, 群成员, 名片点赞, 戳一戳, 撤回消息, 群管理, 禁言, 全员禁言, group_id, user_id, message_seq"
---

# Milky QQ tools

本 skill 面向需要发现、选择或调用 Milky QQ Agent 工具的场景，包括：发送名片点赞、好友
或群戳一戳、撤回群消息、查询群和群成员、设置群成员禁言、设置群全员禁言。

工具名称与 Milky API 的 `operationId` 一致。本 skill 只解释当前已注册的 9 个 Hermes
ToolSpec，不注册工具、不授予权限，也不把未列出的 Milky Action 变成可用能力。实际可用性、
参数校验和服务端返回结果始终以 Hermes 当前发现的 ToolSpec 与 Milky 响应为准。

## 先看：权限与副作用速查

| 工具 | 类型 | 关键权限或前置条件 |
| --- | --- | --- |
| `send_profile_like` | 写操作 | 目标 QQ 号必须明确；点赞数量受服务端限制和频控约束。 |
| `send_friend_nudge` | 写操作 | 目标应为好友私聊对象；`is_self` 只表示是否戳自己，默认 `false`。 |
| `send_group_nudge` | 写操作 | `user_id` 应是目标群成员；Bot 的群成员关系和其他权限由服务端判断。 |
| `recall_group_message` | 写操作 | 普通成员只能在 2 分钟内撤回 Bot 自己的群消息；Bot 为群管理员时可不限时间撤回任何人的群消息，包括自己发送的消息。 |
| `get_group_info` | 只读查询 | OpenAPI 未声明额外群管理权限；能否查询目标群由 Milky 服务端的账号可见范围决定。 |
| `get_group_member_list` | 只读查询 | OpenAPI 未声明额外群管理权限；目标群和可见成员范围由 Milky 服务端判断。 |
| `get_group_member_info` | 只读查询 | OpenAPI 未声明额外群管理权限；目标群成员关系和可见范围由 Milky 服务端判断。 |
| `set_group_member_mute` | 写操作 | Bot 必须具备目标群管理权限（群主或管理员）；`duration=0` 表示取消禁言。 |
| `set_group_whole_mute` | 写操作 | Bot 必须具备目标群管理权限（群主或管理员）；`is_mute=false` 表示取消全员禁言。 |

撤回、戳一戳、点赞和禁言都会产生外部副作用。调用前必须确认目标和动作来自当前用户
意图；权限不足、目标不合法或服务端拒绝时，不应改用其他 Action 猜测或重试。

## 通用参数规则

- `group_id`、`user_id` 必须是整数 `10001..4294967295`，不接受字符串伪装。
- `message_seq` 必须是整数 `0..9007199254740991`，使用 Milky 远端消息序号，不使用本地时间或随机值替代。
- `no_cache` 是可选布尔值，默认 `false`；为 `true` 时要求 Milky 绕过服务端缓存读取。
- 可选的 `count`、`duration` 和布尔参数可以省略；不要传入未声明字段。
- `group_id`、`user_id` 和 `message_seq` 必须来自当前上下文或用户明确提供的目标；不能从昵称、正文或模糊描述猜测。
- 临时会话目标、缺失参数和未注册 Action 不因本 skill 的文字说明而获得支持。

## 工具说明

### `send_profile_like`

给指定 QQ 号发送名片点赞。

- 必填：`user_id`。
- 可选：`count`，整数 `0..9007199254740991`，默认 `1`。
- 这是写操作；目标、频控和服务端可执行次数由 Milky 校验。不要把它当作好友关系变更或权限提升工具。

### `send_friend_nudge`

向指定好友发送好友戳一戳。

- 必填：`user_id`。
- 可选：`is_self`，布尔值，表示是否戳自己，默认 `false`。
- 这是好友私聊 Action；不要把群成员参数传给它，也不要用它代替 `send_group_nudge`。

### `send_group_nudge`

向指定群内成员发送戳一戳。

- 必填：`group_id`、`user_id`。
- Bot 必须能访问目标群，目标 `user_id` 应属于该群；不满足时由服务端拒绝。
- 不接受 `is_self` 或统一 `target` 参数。

### `recall_group_message`

撤回指定群消息。

- 必填：`group_id`、`message_seq`。
- 这是群消息专用工具，不能用来撤回私聊消息。
- Milky 的撤回规则是：普通账号在私聊或群聊中，只能在消息发送后 2 分钟内撤回自己发送的消息。
- 群管理员权限：Bot 为目标群群主或管理员时，可不限时间撤回群内任何人的消息，也包括 Bot 自己发送的消息。
- 是否具备管理员身份由 Milky 服务端判断；权限不足时应保留失败结果，不要盲目重试或改用其他撤回接口。
- 当前只注册了群消息撤回工具；私聊撤回 Action 未注册，不能凭本节说明调用。

### `get_group_info`

查询指定群的信息。

- 必填：`group_id`。
- 可选：`no_cache`。
- 这是只读查询，不等同于群管理权限；不要因为查询成功就推断 Bot 具有管理员身份。

### `get_group_member_list`

查询指定群的成员列表。

- 必填：`group_id`。
- 可选：`no_cache`。
- 这是只读查询；返回内容和可见范围以 Milky 当前账号权限及服务端结果为准。
- 成员列表可能较大，只有在确实需要完整列表时调用，不要用它替代单成员查询。

### `get_group_member_info`

查询指定群成员的信息。

- 必填：`group_id`、`user_id`。
- 可选：`no_cache`。
- 这是只读查询，不授予禁言、撤回或其他管理权限。

### `set_group_member_mute`

设置或取消指定群成员的禁言。

- 必填：`group_id`、`user_id`。
- 可选：`duration`，整数 `0..9007199254740991` 秒，默认 `0`；`0` 表示取消禁言。
- Bot 必须是目标群群主或管理员，且仍需遵守 Milky 对目标成员和管理员层级的限制。
- 这是高影响写操作；调用前确认目标成员、时长和“取消禁言”意图。权限错误或未知结果不能通过重复调用放大影响。

### `set_group_whole_mute`

设置或取消目标群的全员禁言。

- 必填：`group_id`。
- 可选：`is_mute`，布尔值，默认 `true`；`true` 开启，`false` 取消。
- Bot 必须是目标群群主或管理员。
- 这是影响整个群的高影响写操作；调用前必须确认目标群和开关方向。服务端拒绝或未知结果应原样作为失败处理。

## 结果与降级

工具返回的是绑定 Milky Action 的结果。`invalid_input` 表示本地参数或目标校验失败，
`rejected` 表示服务端拒绝，`transport_unknown` 表示请求执行状态未知，`malformed` 表示
响应结构不符合预期，`unsupported` 表示当前能力未实现。对撤回和禁言等非幂等或高影响
操作，`transport_unknown` 不应自动重试。
