# Spec Delta

## MODIFIED Requirements

### Requirement: 固定 Action ToolSpec 目录

插件 MUST 注册下列 26 个 Milky Action ToolSpec，名称与 operationId 一致；不得开放任意 Action catalog。
参数和分组行为由本规范及 [qq-group-action-tools](../qq-group-action-tools/spec.md) 定义；响应交付与日志边界由
[security-boundaries](../security-boundaries/spec.md) 定义。sticker_search 与 sticker_send 是独立语义工具，
不计入此 Action 目录，结果遵守各自规范。

| 工具组 | operationId |
|---|---|
| 消息及群状态 | send_profile_like、send_friend_nudge、send_group_nudge、recall_group_message、get_group_info、get_group_member_list、get_group_member_info、set_group_member_mute、set_group_whole_mute |
| 消息资源 | get_resource_temp_url |
| 转发、私聊文件与好友管理 | get_forwarded_messages、get_private_file_download_url、kick_group_member、quit_group、delete_friend、get_friend_requests、accept_friend_request、reject_friend_request |
| 群文件与请求 | get_group_file_download_url、accept_group_request、reject_group_request、accept_group_invitation、reject_group_invitation、get_group_files |
| 好友资料与专属头衔 | get_friend_info、set_group_member_special_title |

#### Scenario: Manifest 与工具注册保持同一目录

- **WHEN** Hermes 发现插件的 Milky Action 工具
- **THEN** manifest 与实际注册 SHALL 提供上述 26 个同名 operationId
- **AND** SHALL 不把贴纸语义工具计入 Action 数量，也不发现任意未登记 Action

## ADDED Requirements

### Requirement: `get_resource_temp_url` 必须使用固定 operationId 和精确参数

插件 MUST 注册名为 `get_resource_temp_url` 的异步 ToolSpec，使用 `milky` 工具集，并且只调用
`POST /api/get_resource_temp_url`。工具 MUST 只接受必填的 `resource_id: string`，该值 MUST 为非空字符串；
不得接受未声明字段。工具 MUST 在网络访问前拒绝缺失字段、错误类型、空字符串或额外字段，并且只在
Agent 显式调用时执行，不得由消息正文、视频 segment、Will 或资源 resolver 隐式触发。

#### Scenario: Hermes 发现资源临时链接工具

- **WHEN** Hermes 加载插件并读取显式 ToolSpec
- **THEN** 工具列表 SHALL 包含 `get_resource_temp_url`
- **AND** 该工具 SHALL 绑定 Milky `get_resource_temp_url` operationId
- **AND** 注册阶段 SHALL 不发起 Milky HTTP 请求、SSE 连接或长期任务

#### Scenario: 资源临时链接请求使用精确 body

- **WHEN** Agent 以合法 `resource_id` 显式调用工具
- **THEN** 系统 SHALL 向 `<base>/api/get_resource_temp_url` 发送一次 POST JSON 请求
- **AND** 请求 body SHALL 只包含 `{ "resource_id": "<resource-id>" }`

#### Scenario: 非法资源 ID 不触网

- **WHEN** Agent 缺少 `resource_id`、传入非字符串、空字符串或未声明字段
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** SHALL 不调用 Milky client、不发送 HTTP 请求且不记录远端结果

### Requirement: `get_resource_temp_url` 必须原样交付远端响应体

只要 `get_resource_temp_url` 已取得远端响应体，Tool 调用方 SHALL 收到 UTF-8 解码后的原始响应内容，
不得对 envelope、`data.url`、HTTP 状态或未知字段进行解析、过滤、摘要或重建。工具 SHALL 不下载、缓存、
materialize 或自动把 URL 写入普通入站上下文或 `MessageEvent.media_urls`；日志不得记录请求参数、完整 URL
或响应体。参数非法、client 未绑定或传输未取得响应体时，工具 SHALL 沿用固定的 `invalid_input`、
`unsupported` 或 `transport_unknown` 分类。

#### Scenario: 取得包含临时 URL 的响应体

- **WHEN** Milky 返回任意 HTTP 状态和包含 `data.url` 或未知扩展字段的响应体
- **THEN** Tool 调用方 SHALL 收到远端响应体的原始内容
- **AND** SHALL 不附加插件分类或状态码，也不得在日志中记录 URL
- **AND** 插件 SHALL 不下载或 materialize 该资源

#### Scenario: 未取得远端响应体

- **WHEN** 网络调用进入传输边界但未取得响应体
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** SHALL 不自动重试或伪造成功 URL
