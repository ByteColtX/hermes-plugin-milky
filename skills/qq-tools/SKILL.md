---
name: qq-tools
description: Reference for Milky QQ Agent's explicit ToolSpec calls — fixed operationIds, strict parameter schemas, admin-only restrictions, and side-effect boundaries. Use when calling or explaining a specific QQ tool (friend requests, forwarded messages, private file transfer, group member/admin actions, mute, poke, message recall, card likes) and you need the exact operationId, required parameters, or permission constraints.
metadata:
  short-description: Milky QQ 工具入参与权限
  keywords: "Milky, QQ, Hermes, ToolSpec, operationId, 好友, 好友请求, 合并转发, 私聊文件, 群聊, 群成员, 名片点赞, 戳一戳, 撤回消息, 群管理, 禁言, 全员禁言, group_id, user_id, initiator_uid, forward_id, file_hash, message_seq"
---

# Milky QQ tools

本 skill 只解释当前已注册的 17 个 Hermes ToolSpec。工具名与 Milky `operationId` 相同；
文字说明不注册工具，文字说明不执行也不扩大工具能力，未列出的 Action 不可调用。每个工具只
调用同名的 `POST /api/{operationId}`。

本 skill 的 17 个 ToolSpec 不含媒体发送。需发送本地图片、音频、视频或文档时，在回复中包含
`MEDIA:<local_path>`（如 `MEDIA:~/path/to/clip.mp4`）；显式使用 `send_message` 工具时，同一
指令放入其 `message` 参数。Hermes 按扩展名路由至 Milky 的原生媒体/文件上传入口。除非发送失败，
不得声称 Milky 不支持媒体或文件发送，也不要把本地路径当普通文本发送。`MEDIA:` 不扩大本 skill
的 ToolSpec 范围。

## 调用规则

- 入参必须是 JSON 对象，只传下表字段；禁止额外字段、别名和字符串伪装的数字。
- `group_id`、`user_id` 是整数 `10001..4294967295`；`message_seq`、`count`、`duration`、
  `limit` 是整数 `0..9007199254740991`；均不接受 `bool`。
- `forward_id`、`file_id`、`file_hash`、`initiator_uid` 必须是非空字符串；`reason` 是字符串或
  `null`。其余可选字段按 schema 的布尔值或 `null` 传递。
- `?` 表示可省略。省略字段与显式传 `null` 不同：插件不会自行补默认字段，显式 `null` 会按原样
 进入 Action body。需要成功率时，优先只传必填字段；需要开关/时长时传明确的 `true`/`false` 或整数。
- ID 必须来自当前消息/上下文或用户明确提供：不要从昵称、正文或模糊描述猜测。`message_seq` 是
  Milky 远端消息序号，不是时间戳或随机数；`initiator_uid` 是好友请求返回的 UID，不是 QQ 号。
- 私聊文件查询必须同时提供 `file_id` 和 `file_hash`；只有文件名不能调用。
- `no_cache=true` 表示要求绕过缓存；不需要时省略。`temp` 会话没有对应的工具目标。

## 工具与入参

### 好友、群和消息

- `send_profile_like`: `{user_id, count?}`；名片点赞，`count` 为次数。
- `send_friend_nudge`: `{user_id, is_self?}`；好友私聊戳一戳，不要传 `group_id`。
- `send_group_nudge`: `{group_id, user_id}`；`user_id` 必须是目标群成员。
- `recall_group_message`: `{group_id, message_seq}`；仅群消息，不能撤回私聊消息。
- `get_group_info`: `{group_id, no_cache?}`；只读查询。
- `get_group_member_list`: `{group_id, no_cache?}`；需要完整成员列表时使用。
- `get_group_member_info`: `{group_id, user_id, no_cache?}`；只查单个成员。

### 群管理

以下工具仅限 Bot 为目标群群主或管理员时使用，最终权限由 Milky 服务端判断：

- `set_group_member_mute`: `{group_id, user_id, duration?}`；时长单位为秒，`duration=0` 取消禁言。
- `set_group_whole_mute`: `{group_id, is_mute?}`；`true` 开启、`false` 取消全员禁言。
- `kick_group_member`: `{group_id, user_id, reject_add_request?}`；可选项控制是否拒绝其再次加群。

`recall_group_message` 不是管理员专用：普通账号通常只能在 2 分钟内撤回 Bot 自己的群消息；
管理员可按服务端规则撤回群内其他消息。查询群信息或成员信息也不代表 Bot 具备管理权限。

### 转发、私聊文件和好友请求

- `get_forwarded_messages`: `{forward_id}`；只按明确的合并转发 ID 查询，不自动展开到 Hermes turn。
- `get_private_file_download_url`: `{user_id, file_id, file_hash, is_self_send?}`；只返回下载链接，
  插件不会下载、缓存或解码。
- `quit_group`: `{group_id}`；显式退出指定群，无默认或备用目标。
- `delete_friend`: `{user_id}`；显式删除好友关系。
- `get_friend_requests`: `{limit?, is_filtered?}`；可传 `{}`，只查询，不自动处理请求。
- `accept_friend_request`: `{initiator_uid, is_filtered?}`；只接受明确的请求 UID。
- `reject_friend_request`: `{initiator_uid, is_filtered?, reason?}`；`reason` 仅作为 Action 入参。

好友请求事件、群通知、普通正文、关键词和 Will 不会自动触发踢人、退群、删好友或接受/拒绝请求。
所有写操作都要先确认目标和动作；请求结果为 `transport_unknown` 时不得重试、换目标或伪造成功。

## 结果

查询工具成功时保留完整 Milky envelope、`data` 和未知扩展字段；管理工具只返回远端结果，不更新
本地好友/群缓存。常见分类：`invalid_input`（本地参数错误）、`rejected`（服务端拒绝）、
`http_error`、`malformed`、`transport_unknown`、`unsupported`。HTTP 200 不等于业务成功。
