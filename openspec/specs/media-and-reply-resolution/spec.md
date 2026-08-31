# media-and-reply-resolution Specification

## Purpose

在消息真正触发 Hermes turn 时补全 Milky 的图片、文件、语音、视频和回复引用，
同时把下载安全、缓存、权限与路径控制留给 Hermes 的公共媒体边界。

## Requirements

### Requirement: wait 阶段禁止资源网络操作

Will wait 阶段 MUST 只保存分类后的 Milky 引用：`media_resource_references`、
`file_attachment_references`、forward ID 和 reply 目标；不下载文件、不调用资源接口、不
调用 `get_message`，也不创建本地媒体缓存或下载目录。`file_attachment_references` 不得
被改写成 `media_resource_references`。

#### Scenario: wait 消息含图片和回复

- **WHEN** 图片和 reply 消息被 Gate 放行但 Will 返回 wait
- **THEN** buffer SHALL 保存 `media_resource_references`、原始 segment 和 reply ID
- **AND** Milky resource Action、文件下载 Action 与 `get_message` 调用次数 SHALL 为零

#### Scenario: wait 保存 Milky 文件引用

- **WHEN** wait 消息含有 file segment
- **THEN** buffer SHALL 保存 `file_attachment_references` 中的 `file_id`、`file_name`、`file_size` 和原始 segment
- **AND** SHALL 不要求或伪造文件 URL，不调用 `get_resource_temp_url` 或未确认的文件下载 Action

### Requirement: trigger 阶段才允许查询分类引用

trigger 阶段 MAY 查询 `media_resource_references` 的临时 URL、forward 完整内容和缺失的
reply 原消息；已有完整 reply segments 时不得无条件重复查询。`file_attachment_references`
不得使用 `get_resource_temp_url`：group file SHALL 使用
`get_group_file_download_url(group_id, file_id)`，private file SHALL 使用
`get_private_file_download_url(user_id, file_id, file_hash, ...)`，其中私聊缺少必需
`file_hash` 时必须安全降级。两个 file Action 返回的 `download_url` 仍须经过安全的
URL-to-bytes seam，才能交给 Hermes attachment materializer；没有该 seam 时必须返回
`unsupported` 和占位。插件 MUST NOT 自行拼接 Hermes 本地路径或接管缓存和 SSRF 规则。

#### Scenario: trigger 补全回复

- **WHEN** detached batch 或当前消息包含 reply segment 且 trigger 已发生
- **THEN** 系统 SHALL 尽力查询原消息的正文、作者和分类后的附件引用
- **AND** 远端引用 SHALL 进入 Hermes 公共附件 materialization 边界

#### Scenario: 资源查询失败

- **WHEN** Milky 资源或 reply 查询失败
- **THEN** 正文 SHALL 保留
- **AND** 结果 SHALL 保留引用 ID 或生成 `[图片不可用]`、`[文件不可用]`、`[语音转写失败]` 等可解释占位
- **AND** metadata SHALL 记录不含凭证的错误类别

#### Scenario: trigger 补全 forward

- **WHEN** detached batch 或当前消息包含 forward segment 且 trigger 已发生
- **THEN** 系统 MAY 使用 `forward_id` 调用 `get_forwarded_messages`
- **AND** 解析失败 SHALL 保留 forward ID 和可解释占位，不得把预览文本冒充完整转发内容

#### Scenario: trigger 获取群文件下载链接

- **WHEN** trigger 处理带有 `file_id` 的 group `file_attachment_references`
- **THEN** 系统 SHALL 调用 `get_group_file_download_url` 并传入当前 `group_id` 与 `file_id`
- **AND** SHALL 将成功返回的 `download_url` 交给经过确认的 bytes seam，不得把该 URL 直接写入 MessageEvent.media_urls

#### Scenario: private file 缺少哈希

- **WHEN** trigger 处理 private `file_attachment_references` 且缺少 `file_hash`
- **THEN** 系统 SHALL 不调用 `get_private_file_download_url`
- **AND** SHALL 记录 `unsupported` 或 `malformed` 的安全诊断并生成 `[文件不可用]` 占位

#### Scenario: file 没有确认的 URL-to-bytes seam

- **WHEN** trigger 已通过对应 Milky file Action 获得 `download_url`，但当前 Hermes 组合没有确认的 URL-to-bytes seam
- **THEN** 系统 SHALL 保留 `file_id`、文件名和 `[文件不可用]` 占位，并记录 `unsupported`
- **AND** SHALL 不调用 `get_resource_temp_url`、不把 URL 当成本地路径、不执行未受控的插件侧直接下载

### Requirement: 资源安全限制由 Hermes 所有

媒体资源和已确认的文件附件 materialization MUST 由 Hermes helper/cache 边界负责其适用的 SSRF 校验、大小和 MIME 限制、下载路径、权限、缓存及生命周期；插件 SHALL 只提供经过协议层校验的分类远端引用或经确认 seam 得到的 bytes。

#### Scenario: 远端媒体引用

- **WHEN** Milky 返回图片或文件的远端 URL
- **THEN** 插件 SHALL 将引用交给 Hermes helper
- **AND** SHALL 不把远端 URL 当成本地可访问路径或写入第二套缓存

#### Scenario: 恶意或不受支持引用

- **WHEN** 引用未通过 Hermes 安全限制
- **THEN** 资源 SHALL 被安全拒绝并保留可解释占位
- **AND** SHALL 不绕过限制继续下载

#### Scenario: 远端媒体资源引用

- **WHEN** Milky 返回媒体资源的远端 URL
- **THEN** 插件 SHALL 将 `media_resource_references` 交给对应 Hermes helper
- **AND** SHALL 不把远端 URL 当成本地可访问路径或写入第二套缓存

### Requirement: Hermes materialization 必须在 MessageEvent 映射前完成

resolver MUST 在 mapper 和 `handle_message()` 之前等待所有实际使用的异步 Hermes URL
helper/materializer 完成。成功结果 SHALL 形成 `hermes_attachment_materializations`，
包含 Hermes 可访问的本地路径、MIME 和 kind；只有这些本地路径才可写入
`MessageEvent.media_urls`/`media_types`。未 materialize 的 Milky URL、`file_id` 或
远端引用不得直接写入 `media_urls`。

#### Scenario: async URL helper

- **WHEN** image 或 record 的临时 URL 交给 Hermes async URL helper
- **THEN** resolver SHALL await helper 返回的本地路径后再构造 MessageEvent
- **AND** MessageEvent SHALL 只包含该本地路径及对应 MIME，不得包含未解析 URL

#### Scenario: bytes-only cache helper

- **WHEN** 某种附件只能由 Hermes bytes cache helper materialize
- **THEN** 系统 SHALL 仅在已有经过确认的下载 seam 提供 bytes 后调用 `cache_media_bytes()` 或对应 bytes helper
- **AND** 对 ZIP 等普通文件 SHALL 生成 `kind="document"` 的本地 materialization，且不得把同步 bytes cache helper 描述为会下载或 await 远端资源

#### Scenario: materialization 不支持

- **WHEN** 引用存在但当前 Hermes helper 不支持该 kind 或安全校验失败
- **THEN** mapper SHALL 保留结构化引用诊断并生成可解释占位
- **AND** SHALL 不把远端 URL、file ID 或猜测的本地路径写入 MessageEvent.media_urls

### Requirement: Hermes helper 的职责和能力边界必须显式

本适配器 MUST 按具体 helper 的能力调用 Hermes，不得假定存在统一的
`await_resource()` 或“任意引用转附件”公共入口。Hermes 的 image/audio async URL helper
负责其支持类型的下载并返回本地路径；`cache_media_bytes()` 和其他 bytes cache helper
只缓存已提供的 bytes，其中普通文件会被归类为 document；插件不得创建第二套缓存、下载
目录、权限规则、SSRF 规则或本地路径协议。

#### Scenario: 图片或音频远端引用

- **WHEN** `media_resource_references` 提供受支持的图片或音频 URL
- **THEN** 插件 SHALL 将 URL 交给对应 Hermes URL helper 并等待其结果
- **AND** SHALL 不在插件中复制下载、缓存或 SSRF 检查

#### Scenario: 恶意或不受支持引用

- **WHEN** 引用未通过 Hermes 安全限制或没有对应 helper seam
- **THEN** 资源 SHALL 被安全拒绝并保留可解释占位
- **AND** SHALL 不绕过限制继续下载
