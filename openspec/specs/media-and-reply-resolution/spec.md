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

trigger 阶段 MAY 查询 `media_resource_references` 的临时 URL 和缺失的 reply 原消息；已有
完整 reply segments 时不得无条件重复查询。`forward` 的 `forward_id` MUST 只作为规范化引用
和正文 placeholder 保留，资源 resolver MUST NOT 自动调用 `get_forwarded_messages`；未来的
显式 QQ Tool 可以在独立授权和参数校验后按 Agent 选择查询。`file_attachment_references`
不得使用 `get_resource_temp_url`：group file SHALL 使用
`get_group_file_download_url(group_id, file_id)`，private file SHALL 使用
`get_private_file_download_url(user_id, file_id, file_hash, ...)`，其中私聊缺少必需
`file_hash` 时必须安全降级。两个 file Action 返回的 `download_url` 只能在存在已确认的
Hermes 文件资源入口时继续处理；没有该入口时必须返回 `unsupported` 和占位。插件 MUST
NOT 自行拼接 Hermes 本地路径或接管缓存和 SSRF 规则。

#### Scenario: trigger 补全回复

- **WHEN** detached batch 或当前消息包含 reply segment 且 trigger 已发生
- **THEN** 系统 SHALL 尽力查询缺失的原消息正文、作者和分类后的附件引用
- **AND** 完整 inline reply SHALL 不触发重复的 `get_message`

#### Scenario: 资源查询失败

- **WHEN** Milky 媒体或 reply 查询失败
- **THEN** 正文 SHALL 保留已有文本和稳定 placeholder
- **AND** 结果 SHALL 保留安全错误分类
- **AND** SHALL 不把原始 URL、异常文本或完整响应写入 MessageEvent

#### Scenario: forward 只保留引用 ID

- **WHEN** detached batch 或当前消息包含 `forward` segment
- **THEN** 正文 SHALL 保留 `[forward:forward_id=<forward_id>]`
- **AND** 资源 resolver SHALL NOT 自动调用 `get_forwarded_messages`
- **AND** forward SHALL 不因 trigger 自动展开为嵌套正文

#### Scenario: trigger 补全 forward

- **WHEN** detached batch 或当前消息包含 forward segment 且 trigger 已发生
- **THEN** 系统 SHALL 保留 forward_id 和 `[forward:forward_id=<forward_id>]` placeholder
- **AND** 资源 resolver SHALL NOT 自动调用 `get_forwarded_messages`
- **AND** 后续详情查询 SHALL 留给独立 QQ Tool

#### Scenario: 文件下载链接仍使用场景专用 Action

- **WHEN** trigger 处理带有 `file_id` 的 group 或 friend 文件引用
- **THEN** group SHALL 调用 `get_group_file_download_url`，friend 在 hash 可用时 SHALL 调用
  `get_private_file_download_url`
- **AND** 没有已确认的 Hermes 文件入口时 SHALL 保留 `[file:file_id=<file_id>,file_name=<file_name>]`

#### Scenario: trigger 获取群文件下载链接

- **WHEN** trigger 处理带有 file_id 的 group 文件引用
- **THEN** 系统 SHALL 调用 `get_group_file_download_url` 并传入当前 group_id 与 file_id
- **AND** SHALL 只在存在已确认 Hermes 文件入口时继续处理 download_url
- **AND** 不存在该入口时 SHALL 保留文件 placeholder，不得把 URL 写入 MessageEvent.media_urls

#### Scenario: private file 缺少哈希

- **WHEN** trigger 处理 private 文件引用且缺少 `file_hash`
- **THEN** 系统 SHALL 不调用 `get_private_file_download_url`
- **AND** SHALL 记录 `unsupported` 或 `malformed` 诊断并保留
  `[file:file_id=<file_id>,file_name=<file_name>]`

#### Scenario: file 没有确认的 Hermes 入口

- **WHEN** Milky file Action 返回 download_url 但当前 Hermes 没有确认文件入口
- **THEN** 系统 SHALL 保留 file_id、文件名和
  `[file:file_id=<file_id>,file_name=<file_name>]`
- **AND** SHALL 记录 `unsupported`
- **AND** SHALL NOT 把 URL 当成本地路径或执行插件侧下载

#### Scenario: 引用查询失败

- **WHEN** 媒体或 reply 查询失败
- **THEN** 正文 SHALL 保留已生成的稳定 placeholder 和可用文本
- **AND** 诊断 SHALL 保留安全错误分类
- **AND** SHALL 不把原始 URL、异常文本或完整响应写入 MessageEvent

### Requirement: 资源安全限制由 Hermes 所有

媒体资源和已确认的文件附件 materialization MUST 由 Hermes helper/cache 边界负责其适用的 SSRF 校验、大小和 MIME 限制、下载路径、权限、缓存及生命周期；插件 SHALL 只提供经过协议层校验的分类远端引用。

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

resolver MUST 在 mapper 和 `handle_message()` 之前等待 detached batch 中历史消息与当前消息实际使用的异步 Hermes URL helper/materializer 完成。成功结果 SHALL 形成 `hermes_attachment_materializations`，包含 Hermes 可访问的本地路径、MIME 和 kind；历史上下文中实际展示的图片和当前 trigger 消息的图片均属于本次 Hermes 媒体输入候选。只有这些本地路径才可写入 `MessageEvent.media_urls`/`media_types`；未 materialize 的 Milky URL、`file_id` 或远端引用不得直接写入 `media_urls`。

#### Scenario: async URL helper

- **WHEN** image 或 record 的临时 URL 交给 Hermes async URL helper
- **THEN** resolver SHALL await helper 返回的本地路径后再构造 MessageEvent
- **AND** MessageEvent SHALL 只包含该本地路径及对应 MIME，不得包含未解析 URL

#### Scenario: 历史上下文图片与当前图片均完成 materialization

- **WHEN** detached batch 的历史消息和当前 trigger 消息都包含图片，且 Hermes helper 为这些图片返回有效本地路径
- **THEN** resolver SHALL 为历史消息和当前消息分别保留成功的图片 materialization
- **AND** 这些图片 SHALL 都可供同一次 MessageEvent 的 `media_urls` 使用
- **AND** 历史图片 SHALL 按其在 `channel_context` 中的顺序先于当前 trigger 图片

#### Scenario: 重复图片路径只保留一次

- **WHEN** 历史上下文图片和当前 trigger 图片的成功 materialization 使用相同本地路径
- **THEN** 同一次 MessageEvent 的媒体输入 SHALL 只保留该本地路径一次
- **AND** SHALL 保留该路径首次出现时的顺序和对应 MIME

#### Scenario: 文件没有确认的 materialization 入口

- **WHEN** 某种附件没有已确认的 Hermes 远端资源或文件 materialization 入口
- **THEN** 系统 SHALL 返回 `unsupported` 和可解释占位
- **AND** SHALL 不在插件中读取 bytes、创建路径或调用未确认的 bytes helper

#### Scenario: materialization 不支持

- **WHEN** 引用存在但当前 Hermes helper 不支持该 kind 或安全校验失败
- **THEN** mapper SHALL 保留结构化引用诊断并生成可解释占位
- **AND** SHALL 不把远端 URL、file ID 或猜测的本地路径写入 MessageEvent.media_urls

#### Scenario: 历史图片 materialization 失败

- **WHEN** 历史消息中的图片 helper 不可用、下载失败或返回无效本地路径
- **THEN** 该图片 SHALL 不进入 MessageEvent.media_urls
- **AND** 对应历史 `channel_context` SHALL 保留既有图片失败占位和安全诊断

### Requirement: Hermes helper 的职责和能力边界必须显式

本适配器 MUST 按具体 helper 的能力调用 Hermes，不得假定存在统一的
`await_resource()` 或“任意引用转附件”公共入口。Hermes 的 image/audio async URL helper
负责其支持类型的下载并返回本地路径；没有明确对应入口的附件由插件保留占位并返回
`unsupported`；插件不得创建第二套缓存、下载目录、权限规则、SSRF 规则或本地路径协议。

#### Scenario: 图片或音频远端引用

- **WHEN** `media_resource_references` 提供受支持的图片或音频 URL
- **THEN** 插件 SHALL 将 URL 交给对应 Hermes URL helper 并等待其结果
- **AND** SHALL 不在插件中复制下载、缓存或 SSRF 检查

#### Scenario: 恶意或不受支持引用

- **WHEN** 引用未通过 Hermes 安全限制或没有对应 helper seam
- **THEN** 资源 SHALL 被安全拒绝并保留可解释占位
- **AND** SHALL 不绕过限制继续下载
