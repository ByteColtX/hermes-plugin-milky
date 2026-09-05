---
name: milky-qq-action-tools
description: Reference for Milky QQ Agent's 25 fixed Action ToolSpecs and parameter rules.
metadata:
  short-description: Milky QQ 工具入参与权限
  keywords: "Milky, QQ, Hermes, ToolSpec, operationId, 好友, 好友资料, 好友请求, 合并转发, 私聊文件, 群聊, 群成员, 群文件, 专属头衔, 入群请求, 群邀请, group_id, user_id, special_title, initiator_uid, forward_id, file_hash, message_seq, notification_seq, invitation_seq, download_url"
---

# Milky QQ action tools

这份 skill 只说明当前注册的 25 个 Hermes Action ToolSpec。工具名对应 Milky 的 `operationId`，
请求为 `POST /api/{operationId}`；未列出的 Action、别名和任意 Action catalog 均不可调用。
文字说明不注册工具，不执行也不扩大工具能力。

最终能力和参数校验以实际 ToolSpec、handler 和 Milky 契约为准。

## 参数规则

- 只传 ToolSpec 声明的字段，参数必须是 JSON object；整数不接受 `bool`、浮点数或字符串数字。
- 普通目标的 `group_id`、`user_id` 使用当前消息、`channel_context` 或用户明确提供的真实 ID；不要从昵称、
  正文、通知或关键词猜 ID。
- `message_seq`、`notification_seq`、`notification_type`、`invitation_seq`、`forward_id`、`file_id`、
  `file_hash`、`initiator_uid` 等关联字段只能使用当前消息/事件或 `channel_context` 中的真实值；没有可靠值
  就不要调用，也不能用时间戳、文件名或显示文本替代。
- `forward_id`、`file_id`、`file_hash`、`initiator_uid` 必须是非空字符串；`parent_folder_id` 和群请求的
  `reason` 若传字符串也不能全空。好友请求的 `reason` 可为空；私聊 `file_hash` 是 TriSHA1。
- `?` 表示可省略；schema 标为 nullable 的字段才可显式传 `null`，两者不会互相替换。`temp` 会话没有工具目标。

省略可选字段时由 Milky 使用 schema 默认值；插件不主动把默认值写入请求 body。

## 25 个工具

### 查询

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `get_group_info` | `{group_id: integer, no_cache?: boolean|null}` | 查群信息 |
| `get_group_member_list` | `{group_id: integer, no_cache?: boolean|null}` | 查群成员列表 |
| `get_group_member_info` | `{group_id: integer, user_id: integer, no_cache?: boolean|null}` | 查一个群成员 |
| `get_friend_requests` | `{limit?: integer|null, is_filtered?: boolean|null}` | 查好友请求，可传 `{}` |
| `get_forwarded_messages` | `{forward_id: string}` | 查合并转发内容；嵌套合并转发不展开 |
| `get_private_file_download_url` | `{user_id: integer, file_id: string, file_hash: string, is_self_send?: boolean|null}` | 查私聊文件下载链接 |
| `get_group_file_download_url` | `{group_id: integer, file_id: string}` | 查群文件下载链接 |
| `get_group_files` | `{group_id: integer, parent_folder_id?: string|null}` | 查群文件和文件夹 |
| `get_friend_info` | `{user_id: integer}` | 查好友资料；字段由目标服务定义，不支持 `no_cache` |

查询只返回完整 Milky envelope，保留未知字段，不自动下载、缓存或解码文件。

### 消息

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `send_profile_like` | `{user_id: integer, count?: integer|null}` | 点赞名片 |
| `send_friend_nudge` | `{user_id: integer, is_self?: boolean|null}` | 给好友发送戳一戳 |
| `send_group_nudge` | `{group_id: integer, user_id: integer}` | 在群里戳一戳；目标须是群成员 |
| `recall_group_message` | `{group_id: integer, message_seq: integer}` | 撤回群消息 |

### 群管理

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `set_group_member_mute` | `{group_id: integer, user_id: integer, duration?: integer|null}` | 禁言成员；秒，`0` 表示取消 |
| `set_group_whole_mute` | `{group_id: integer, is_mute?: boolean|null}` | 开关全员禁言 |
| `kick_group_member` | `{group_id: integer, user_id: integer, reject_add_request?: boolean|null}` | 踢出成员，可拒绝其再次加群 |
| `quit_group` | `{group_id: integer}` | 退出指定群 |

### 好友、入群请求和邀请

| ToolSpec | 参数 | 用途 |
| --- | --- | --- |
| `accept_friend_request` | `{initiator_uid: string, is_filtered?: boolean|null}` | 接受好友请求 |
| `reject_friend_request` | `{initiator_uid: string, is_filtered?: boolean|null, reason?: string|null}` | 拒绝好友请求 |
| `delete_friend` | `{user_id: integer}` | 删除好友关系 |
| `accept_group_request` | `{notification_seq: integer, notification_type: enum, group_id: integer, is_filtered?: boolean|null}` | 接受入群请求 |
| `reject_group_request` | `{notification_seq: integer, notification_type: enum, group_id: integer, is_filtered?: boolean|null, reason?: string|null}` | 拒绝入群请求 |
| `accept_group_invitation` | `{group_id: integer, invitation_seq: integer}` | 接受群邀请 |
| `reject_group_invitation` | `{group_id: integer, invitation_seq: integer}` | 拒绝群邀请 |
| `set_group_member_special_title` | `{group_id: integer, user_id: integer, special_title: string}` | 设置专属头衔（Bot 需为群主） |

`special_title` 最多 6 个中文字符；空字符串用于清除。不要截断、trim 或补默认值，超过限制时不要调用。

`notification_type` 只能是 `join_request` 或 `invited_join_request`。请求/邀请事件仅供观察，接受或拒绝
必须显式调用对应 Action。

## 文件与媒体

入站文件正文使用：

```text
[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]
```

下载流程和安全要求见 [group-file-download.md](references/group-file-download.md)。

25 个 Action 不含媒体发送。发送本地图片、音频、视频或文档时，在回复中包含 `MEDIA:<local_path>`；
显式使用 `send_message` 时放入 `message` 参数。Hermes 负责上传，不要把本地路径当普通文本。

## 返回结果

- 查询成功，返回完整 Milky envelope、`data` 和未知扩展字段。
- `invalid_input`，参数本地就不合法，且不会发网络请求。
- `http_error`，HTTP 状态码不是成功状态；不要将它与业务拒绝混淆。
- `rejected`，服务端返回了 envelope，但 Milky 业务拒绝；HTTP 200 不代表业务成功。
- `malformed`，响应缺少工具要求的最小结构。
- `transport_unknown`，客户端没有拿到可确认的结果，不能重试。
- `unsupported`，工具当前不可用。
