---
name: milky-qq-action-tools
description: Reference for Milky QQ Agent's 25 fixed Action ToolSpecs, strict parameters, permissions, and side-effect boundaries.
metadata:
  short-description: Milky QQ 工具入参与权限
  keywords: "Milky, QQ, Hermes, ToolSpec, operationId, 好友, 好友资料, 好友请求, 合并转发, 私聊文件, 群聊, 群成员, 群文件, 专属头衔, 入群请求, 群邀请, group_id, user_id, special_title, initiator_uid, forward_id, file_hash, message_seq, notification_seq, invitation_seq, download_url"
---

# Milky QQ action tools

这份 skill 只管当前注册的 25 个 Hermes Action ToolSpec。工具名对应 Milky 的 `operationId`，请求发往
同名的 `POST /api/{operationId}`。未列出的 Action、别名和任意 Action catalog 都不能调用。
文字说明不注册工具、不执行也不扩大工具能力，也不会自动触发操作。

## 调用前先看这几条

- 参数必须是 JSON object，只传工具声明的字段。额外字段、别名和字符串数字都会被拒绝。
- `group_id`、`user_id` 是整数，范围 `10001..4294967295`，`bool` 不算整数。
- `message_seq`、`notification_seq`、`invitation_seq`、`count`、`duration`、`limit` 是整数，
  范围 `0..9007199254740991`，也不接受 `bool`。
- `forward_id`、`file_id`、`file_hash`、`initiator_uid` 必须是非空字符串。
- `parent_folder_id` 和群请求拒绝工具的 `reason` 可以是非空字符串或 `null`；好友请求
  拒绝工具的 `reason` 按 schema 可以是字符串或 `null`。`is_filtered`、`is_self`、
  `no_cache`、`reject_add_request` 按 schema 传布尔值或 `null`。
- `?` 表示可以省略。省略和传 `null` 不一样，插件不会替你填默认值。
- ID 要来自当前消息、上下文或用户的明确输入。不要从昵称、正文或显示文本猜 ID。
- `message_seq` 是远端消息序号，不是时间戳；`initiator_uid` 是请求 UID，也不是 QQ 号。
- `temp` 会话没有对应的工具目标。

## 25 个工具

### 查询

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `get_group_info` | `{group_id, no_cache?}` | 查群信息 |
| `get_group_member_list` | `{group_id, no_cache?}` | 查群成员列表 |
| `get_group_member_info` | `{group_id, user_id, no_cache?}` | 查一个群成员 |
| `get_friend_requests` | `{limit?, is_filtered?}` | 查好友请求，可传 `{}` |
| `get_forwarded_messages` | `{forward_id}` | 查合并转发，不自动展开 |
| `get_private_file_download_url` | `{user_id, file_id, file_hash, is_self_send?}` | 查私聊文件下载链接 |
| `get_group_file_download_url` | `{group_id, file_id}` | 查群文件下载链接 |
| `get_group_files` | `{group_id, parent_folder_id?}` | 查群文件和文件夹 |
| `get_friend_info` | `{user_id}` | 查指定好友资料；资料字段由目标服务定义 |

查询工具只返回 Milky envelope，不下载、缓存或解码文件。群文件的手动下载流程见
[group-file-download.md](references/group-file-download.md)。文件样文里已经有 `file_id` 时，
可以直接拿它调用对应的 `get_*_file_download_url`，不必先查文件列表。私聊文件必须同时提供
`file_id` 和 `file_hash`，只有文件名不够。

### 消息

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `send_profile_like` | `{user_id, count?}` | 点赞名片 |
| `send_friend_nudge` | `{user_id, is_self?}` | 给好友发送戳一戳 |
| `send_group_nudge` | `{group_id, user_id}` | 在群里戳一戳，目标须是群成员 |
| `recall_group_message` | `{group_id, message_seq}` | 撤回群消息 |

### 群管理

设置群成员专属头衔必须由 Bot 作为目标群群主调用；管理员权限不足以执行此操作。是否成功仍
以远端 envelope 为准，HTTP 200 也不等于业务成功。

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `set_group_member_mute` | `{group_id, user_id, duration?}` | 禁言成员，单位是秒；`0` 表示取消 |
| `set_group_whole_mute` | `{group_id, is_mute?}` | 开关全员禁言 |
| `kick_group_member` | `{group_id, user_id, reject_add_request?}` | 踢出成员，可拒绝其再次加群 |
| `quit_group` | `{group_id}` | 退出指定群 |

`recall_group_message` 不专属于管理员。能查群信息，也不代表 Bot 有群管理权限。

### 好友、入群请求和邀请

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `accept_friend_request` | `{initiator_uid, is_filtered?}` | 接受好友请求 |
| `reject_friend_request` | `{initiator_uid, is_filtered?, reason?}` | 拒绝好友请求 |
| `delete_friend` | `{user_id}` | 删除好友关系 |
| `accept_group_request` | `{notification_seq, notification_type, group_id, is_filtered?}` | 接受入群请求 |
| `reject_group_request` | `{notification_seq, notification_type, group_id, is_filtered?, reason?}` | 拒绝入群请求 |
| `accept_group_invitation` | `{group_id, invitation_seq}` | 接受群邀请 |
| `reject_group_invitation` | `{group_id, invitation_seq}` | 拒绝群邀请 |
| `set_group_member_special_title` | `{group_id, user_id, special_title}` | 设置群成员专属头衔 |

`special_title` 必须是字符串，长度最多 6 个中文字符；空字符串用于清除专属头衔并原样传递。
不要截断或补默认值，也不要把管理员权限当作足够。

`notification_type` 只接受 `join_request` 和 `invited_join_request`。群请求、群邀请事件只做
observe-only，通知、普通正文、关键词和 Will 都不会替你接受或拒绝。四个群请求 Action 只有
在 Agent 给出完整参数时才会提交，而且一次调用最多提交一次。

## 文件正文和媒体发送

入站文件正文使用：

```text
[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]
```

从这段样文里可以直接拿到 `file_id`。group 会话再用当前 `group_id` 调用
`get_group_file_download_url`；dm 会话还要拿可用的 `file_hash`，调用
`get_private_file_download_url`。如果样文没有 `file_id`，再用 `get_group_files` 查询，别从
文件名猜 ID。

缺失、`null` 或空 hash 会显示为 `NOT SUPPORTED`。不要从正文反解析 hash，也不要把文件名当
成本地路径。文件引用和媒体引用分开，文件不会自动变成出站文件。

本 skill 的 25 个 Action ToolSpec 不含媒体发送。需发送本地图片、音频、视频或文档时，在回复中包含
`MEDIA:<local_path>`，例如 `MEDIA:~/path/to/clip.mp4`；显式使用 `send_message` 工具时，把同一
指令放进其 `message` 参数。Hermes 会按扩展名走 Milky 的原生媒体或文件上传入口。不要把
本地路径当普通文本发送，也不要在发送入口失败前声称 Milky 不支持媒体或文件发送。

## 返回结果

- 查询成功，返回完整 Milky envelope、`data` 和未知扩展字段。
- `invalid_input`，参数本地就不合法，且不会发网络请求。
- `rejected`，服务端拒绝请求；HTTP 200 不代表业务成功。
- `malformed`，响应缺少工具要求的最小结构。
- `transport_unknown`，客户端没有拿到可确认的结果，不能重试。
- `unsupported`，工具未注册、没有生命周期 sender，或当前没有对应的安全入口。

管理工具只返回远端结果，不更新本地好友、群成员、请求或邀请状态。状态变更只能来自明确的
ToolSpec 调用。
