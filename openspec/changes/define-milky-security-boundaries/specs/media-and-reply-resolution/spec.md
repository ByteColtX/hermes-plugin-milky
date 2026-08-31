## MODIFIED Requirements

### Requirement: trigger 阶段才允许查询分类引用

trigger 阶段 MAY 查询 `media_resource_references` 的临时 URL、forward 完整内容和缺失的 reply 原消息；已有完整 reply segments 时不得无条件重复查询。`file_attachment_references` 不得使用 `get_resource_temp_url`：group file SHALL 使用 `get_group_file_download_url(group_id, file_id)`，private file SHALL 使用 `get_private_file_download_url(user_id, file_id, file_hash, ...)`，其中私聊缺少必需 `file_hash` 时必须安全降级。Milky 返回的远端引用 SHALL 直接交给 Hermes core 的已确认资源入口；插件 MUST NOT 自行执行 URL-to-bytes、下载、缓存、权限检查或本地路径生成。没有确认的 Hermes 资源入口时必须返回 `unsupported` 和占位。

#### Scenario: trigger 补全回复

- **WHEN** detached batch 或当前消息包含 reply segment 且 trigger 已发生
- **THEN** 系统 SHALL 尽力查询原消息的正文、作者和分类后的附件引用
- **AND** 远端引用 SHALL 进入 Hermes 公共附件边界

#### Scenario: 资源查询失败

- **WHEN** Milky 资源或 reply 查询失败
- **THEN** 正文 SHALL 保留
- **AND** 结果 SHALL 保留引用 ID 或生成可解释占位
- **AND** metadata SHALL 记录固定错误类别

#### Scenario: trigger 补全 forward

- **WHEN** detached batch 或当前消息包含 forward segment 且 trigger 已发生
- **THEN** 系统 MAY 使用 `forward_id` 调用 `get_forwarded_messages`
- **AND** 解析失败 SHALL 保留 forward ID 和可解释占位，不得把预览文本冒充完整转发内容

#### Scenario: trigger 获取群文件下载链接

- **WHEN** trigger 处理带有 `file_id` 的 group `file_attachment_references`
- **THEN** 系统 SHALL 调用 `get_group_file_download_url` 并传入当前 `group_id` 与 `file_id`
- **AND** SHALL 将成功返回的远端引用交给 Hermes core，不得直接下载或写入 `MessageEvent.media_urls`

#### Scenario: private file 缺少哈希

- **WHEN** trigger 处理 private `file_attachment_references` 且缺少 `file_hash`
- **THEN** 系统 SHALL 不调用 `get_private_file_download_url`
- **AND** SHALL 记录 `unsupported` 或 `malformed` 诊断并生成 `[文件不可用]` 占位

#### Scenario: file 没有确认的 URL-to-bytes seam

- **WHEN** trigger 已通过对应 Milky file Action 获得远端引用，但当前 Hermes 组合没有确认的资源入口
- **THEN** 系统 SHALL 保留 `file_id`、文件名和 `[文件不可用]` 占位，并记录 `unsupported`
- **AND** SHALL 不把 URL 当成本地路径、不执行插件侧直接下载

### Requirement: 资源安全限制由 Hermes 所有

媒体资源和文件附件 materialization MUST 由 Hermes core 负责下载、SSRF 校验、大小和 MIME 限制、路径、权限、缓存及生命周期；插件 SHALL 只提供经过协议层校验的分类远端引用，不得自行提供 bytes、路径或第二套资源安全规则。

#### Scenario: 远端媒体引用

- **WHEN** Milky 返回图片、语音、视频或文件的远端引用
- **THEN** 插件 SHALL 将分类引用交给 Hermes core
- **AND** SHALL 不把远端 URL 当成本地路径、不在插件中下载或写入第二套缓存

#### Scenario: 恶意或不受支持引用

- **WHEN** 引用未通过 Hermes 安全限制或没有对应 Hermes 入口
- **THEN** 资源 SHALL 被安全拒绝并保留可解释占位
- **AND** SHALL 不绕过限制继续下载或读取 bytes

#### Scenario: 远端媒体资源引用

- **WHEN** Milky 返回媒体资源的远端引用
- **THEN** 插件 SHALL 将 `media_resource_references` 交给对应 Hermes core 入口
- **AND** SHALL 不把远端 URL 当成本地路径或写入第二套缓存
