## Purpose

在消息真正触发 Hermes turn 时补全 Milky 的图片、文件、语音、视频和回复引用，
同时把下载安全、缓存、权限与路径控制留给 Hermes 的公共媒体边界。

## ADDED Requirements

### Requirement: wait 阶段禁止资源网络操作

Will wait 阶段 MUST 只保存 Milky 媒体引用（如 `resource_id`、`temp_url`、`file_id`、`file_name`、`file_size`）、forward ID 和 reply 目标，不下载文件、不调用资源接口、不调用 `get_message`，也不创建本地媒体缓存或下载目录。

#### Scenario: wait 消息含图片和回复

- **WHEN** 图片和 reply 消息被 Gate 放行但 Will 返回 wait
- **THEN** buffer SHALL 保存 URL/file_id/file 提示、原始 segment 和 reply ID
- **AND** Milky resource Action 与 `get_message` 调用次数 SHALL 为零

#### Scenario: wait 保存 Milky 文件引用

- **WHEN** wait 消息含有 file segment
- **THEN** buffer SHALL 保存 `file_id`、`file_name`、`file_size` 和原始 segment
- **AND** SHALL 不要求或伪造文件 URL，不调用文件下载 Action

### Requirement: trigger 阶段才允许补全引用

trigger 阶段 MAY 查询资源临时 URL、文件下载引用、forward 完整内容和缺失的 reply 原消息，并 SHALL 将结果交给 Hermes 公共 media helper；已有完整 reply segments 时不得无条件重复查询。插件 MUST NOT 自行拼接 Hermes 本地路径或接管缓存和 SSRF 规则。

#### Scenario: trigger 补全回复

- **WHEN** detached batch 或当前消息包含 reply segment 且 trigger 已发生
- **THEN** 系统 SHALL 尽力查询原消息的正文、作者和媒体引用
- **AND** 远端引用 SHALL 进入 Hermes 公共安全媒体处理边界

#### Scenario: trigger 补全 forward

- **WHEN** detached batch 或当前消息包含 forward segment 且 trigger 已发生
- **THEN** 系统 MAY 使用 `forward_id` 调用 `get_forwarded_messages`
- **AND** 解析失败 SHALL 保留 forward ID 和可解释占位，不得把预览文本冒充完整转发内容

#### Scenario: 资源查询失败

- **WHEN** Milky 资源或 reply 查询失败
- **THEN** 正文 SHALL 保留
- **AND** 结果 SHALL 保留引用 ID 或生成 `[图片不可用]`、`[文件不可用]`、`[语音转写失败]` 等可解释占位
- **AND** metadata SHALL 记录不含凭证的错误类别

### Requirement: 资源安全限制由 Hermes 所有

媒体处理 MUST 由 Hermes helper 负责 SSRF 校验、大小和 MIME 限制、下载路径、权限、缓存及生命周期；插件 SHALL 只提供经过协议层校验的远端引用。

#### Scenario: 远端媒体引用

- **WHEN** Milky 返回图片或文件的远端 URL
- **THEN** 插件 SHALL 将引用交给 Hermes helper
- **AND** SHALL 不把远端 URL 当成本地可访问路径或写入第二套缓存

#### Scenario: 恶意或不受支持引用

- **WHEN** 引用未通过 Hermes 安全限制
- **THEN** 资源 SHALL 被安全拒绝并保留可解释占位
- **AND** SHALL 不绕过限制继续下载
