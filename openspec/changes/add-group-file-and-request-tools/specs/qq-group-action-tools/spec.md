## Purpose

为 Hermes Agent 提供与 Milky v1.3.0 对齐的群文件、入群请求和群邀请固定工具，并在显式调用、参数校验、结果保留和远端副作用之间建立可测试的安全边界。

## ADDED Requirements

### Requirement: 群文件和群请求工具必须使用固定 operationId

插件 MUST 注册以下 6 个固定 ToolSpec，工具名、toolset 和 Milky operationId MUST 一一对应：
`get_group_file_download_url`、`accept_group_request`、`reject_group_request`、
`accept_group_invitation`、`reject_group_invitation` 和 `get_group_files`。每个工具 MUST
只调用名称对应的 `POST /api/{operationId}` Action；插件 MUST NOT 因本能力开放任意 Action
catalog、别名 Action 或未列出的操作。

#### Scenario: Hermes 发现 6 个群工具

- **WHEN** Hermes 加载插件并读取显式工具注册
- **THEN** 工具列表 SHALL 包含上述 6 个工具
- **AND** 每个工具 SHALL 使用 `milky` toolset 并绑定同名 Milky operationId
- **AND** 注册阶段 SHALL 不发起 Milky 网络请求或建立长期事件任务

#### Scenario: 工具不得改写为其他 Action

- **WHEN** Agent 调用任一新增工具
- **THEN** 请求 SHALL 只访问该工具对应的 `/api/{operationId}` 路径
- **AND** SHALL 不根据入参、事件正文或远端结果改调用其他 Action

### Requirement: 群工具参数必须匹配 Milky v1.3.0 schema

工具 MUST 只接受下列字段，并在网络访问前完成校验：

| ToolSpec | 必填字段 | 可选字段 |
|---|---|---|
| `get_group_file_download_url` | `group_id: integer`、`file_id: string` | 无 |
| `accept_group_request` | `notification_seq: integer`、`notification_type: "join_request" \| "invited_join_request"`、`group_id: integer` | `is_filtered: boolean \| null` |
| `reject_group_request` | `notification_seq: integer`、`notification_type: "join_request" \| "invited_join_request"`、`group_id: integer` | `is_filtered: boolean \| null`、`reason: string \| null` |
| `accept_group_invitation` | `group_id: integer`、`invitation_seq: integer` | 无 |
| `reject_group_invitation` | `group_id: integer`、`invitation_seq: integer` | 无 |
| `get_group_files` | `group_id: integer` | `parent_folder_id: string \| null` |

`group_id` MUST 是不含布尔值且范围为 `10001` 至 `4294967295` 的整数；
`notification_seq` 和 `invitation_seq` MUST 是不含布尔值且范围为 `0` 至
`9007199254740991` 的整数；`file_id` MUST 是非空字符串；`parent_folder_id` 和
`reason` 如提供 MUST 符合其声明类型。所有工具 MUST 拒绝额外字段、错误类型、越界值、空
字符串和非法 `notification_type`，并返回 `invalid_input` 而不触网。省略可选字段时，插件
MUST NOT 自行补入 OpenAPI 默认值；显式 `null` 仅在 schema 允许时按原值传递。

#### Scenario: 群文件下载参数通过校验

- **WHEN** Agent 提供合法 `group_id` 和非空 `file_id` 调用 `get_group_file_download_url`
- **THEN** Action body SHALL 只包含这两个字段并使用相同的值
- **AND** 请求 SHALL 使用 `POST /api/get_group_file_download_url`

#### Scenario: 群请求类型和序号必须明确

- **WHEN** Agent 调用 `accept_group_request` 或 `reject_group_request`
- **THEN** 工具 SHALL 要求合法的 `notification_seq`、`notification_type` 和 `group_id`
- **AND** SHALL 不把群号、昵称、正文或通知显示文本推断为缺失的序号或类型

#### Scenario: 群邀请使用独立的邀请序号

- **WHEN** Agent 调用 `accept_group_invitation` 或 `reject_group_invitation`
- **THEN** 请求 SHALL 使用 `group_id` 和 `invitation_seq`
- **AND** SHALL 不把 `notification_seq`、消息序号或群号当作 `invitation_seq`

#### Scenario: 群文件列表的父目录字段按原值传递

- **WHEN** Agent 调用 `get_group_files` 并显式提供 `parent_folder_id`
- **THEN** Action body SHALL 保留该字符串或允许的 `null`
- **AND** 当 Agent 省略该字段时，body SHALL 不凭插件自身添加 `/`

#### Scenario: 非法群工具参数不触网

- **WHEN** 任一新增工具收到缺失必填字段、错误类型、越界序号、空文件 ID、非法枚举或额外字段
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** Milky client SHALL 不发送 HTTP 请求

### Requirement: 群文件查询结果必须保留完整成功 envelope

`get_group_file_download_url` 成功时，Tool 调用方 SHALL 收到包含字符串
`data.download_url` 的完整 Milky envelope；`get_group_files` 成功时，Tool 调用方 SHALL
收到包含对象数组 `data.files` 和 `data.folders` 的完整 Milky envelope。工具 MUST 保留未知
envelope、data、文件和文件夹字段，不得把结果改造成摘要、普通消息正文、本地路径或自动下载
动作。工具只返回下载链接或列表数据，不在调用中下载、缓存、解码或自动 materialize 文件。

#### Scenario: 获取群文件下载链接

- **WHEN** Agent 以合法 `group_id` 和 `file_id` 调用 `get_group_file_download_url`，远端返回成功 envelope
- **THEN** Tool SHALL 返回完整 envelope 和 `data.download_url`
- **AND** SHALL 保留远端返回的未知扩展字段
- **AND** SHALL 不直接读取或下载该 URL

#### Scenario: 获取群文件和文件夹列表

- **WHEN** Agent 调用 `get_group_files`，远端返回成功 envelope
- **THEN** Tool SHALL 返回完整 envelope、`data.files` 数组和 `data.folders` 数组
- **AND** 每个数组中的协议字段和未知扩展字段 SHALL 保持可用
- **AND** SHALL 不把列表自动写入入站上下文或本地缓存

#### Scenario: 查询结果缺少最小结构

- **WHEN** 成功 envelope 缺少 `data.download_url`，或 `data.files`/`data.folders` 不是对象数组
- **THEN** 工具 SHALL 返回 `malformed`
- **AND** SHALL 不报告查询成功或伪造缺失字段

### Requirement: 群请求和群邀请处理必须只由显式调用触发

`accept_group_request`、`reject_group_request`、`accept_group_invitation` 和
`reject_group_invitation` MUST 仅在对应 ToolSpec 被 Agent 显式调用时提交同名 Action。插件
MUST NOT 因 `group_join_request`、`group_invitation`、群通知、普通正文、关键词、Will 或
其他事件自动接受或拒绝请求；插件 MUST NOT 因这些 Action 更新本地群成员、请求或邀请状态。

#### Scenario: 群请求事件保持观察边界

- **WHEN** 系统收到入群请求或邀请他人入群的群通知
- **THEN** 系统 SHALL 记录或观察该事件
- **AND** SHALL 不自动调用 `accept_group_request` 或 `reject_group_request`

#### Scenario: 群邀请事件保持观察边界

- **WHEN** 系统收到他人邀请 Bot 入群的事件
- **THEN** 系统 SHALL 不自动调用 `accept_group_invitation` 或 `reject_group_invitation`
- **AND** SHALL 等待明确的 Tool 调用及其完整参数

#### Scenario: 显式拒绝群请求

- **WHEN** Agent 显式调用 `reject_group_request` 并提供合法参数和可选 `reason`
- **THEN** 请求 SHALL 只提交一次同名 Action
- **AND** `reason` SHALL 只作为协议参数传递，不得进入普通入站正文或本地请求状态

### Requirement: 群管理 Action 必须保留确定性错误边界且不得盲目重试

群请求和群邀请的接受/拒绝属于可能改变远端状态的 Action。请求进入 HTTP 边界后，如果响应
状态未知、超时、连接中断、写入失败或读取失败，工具 MUST 返回 `transport_unknown`，不得重试、
换目标或伪造成功；HTTP 200 但协议拒绝 MUST 返回 `rejected`。成功响应的数据不符合确认的
空对象结构时 MUST 返回 `malformed`。错误结果和安全日志 MUST 不包含认证凭证、完整异常正文、
下载 URL 或敏感自由文本。

#### Scenario: 群请求 Action 的结果未知

- **WHEN** 接受或拒绝群请求/邀请的请求已进入 HTTP 边界，但客户端未收到可确认响应
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** 同一次 Tool 调用 SHALL 不再次提交该 Action

#### Scenario: 远端协议拒绝群操作

- **WHEN** 群请求或群邀请 Action 返回 HTTP 200 但协议 envelope 表示失败
- **THEN** 工具 SHALL 返回 `rejected`
- **AND** SHALL 不把 HTTP 200 当作成功

#### Scenario: 成功管理结果保留协议边界

- **WHEN** 接受或拒绝群请求/邀请返回成功 envelope 且 data 是空对象
- **THEN** Tool 调用方 SHALL 收到完整成功 envelope
- **AND** 插件 SHALL 不虚构本地请求状态或远端对象
