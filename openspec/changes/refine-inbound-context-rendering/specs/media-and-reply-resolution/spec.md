## MODIFIED Requirements

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
- **THEN** 正文 SHALL 保留 `[forward:<forward_id>]`
- **AND** 资源 resolver SHALL NOT 自动调用 `get_forwarded_messages`
- **AND** forward SHALL 不因 trigger 自动展开为嵌套正文

#### Scenario: trigger 补全 forward

- **WHEN** detached batch 或当前消息包含 forward segment 且 trigger 已发生
- **THEN** 系统 SHALL 保留 forward_id 和 `[forward:<forward_id>]` placeholder
- **AND** 资源 resolver SHALL NOT 自动调用 `get_forwarded_messages`
- **AND** 后续详情查询 SHALL 留给独立 QQ Tool

#### Scenario: 文件下载链接仍使用场景专用 Action

- **WHEN** trigger 处理带有 `file_id` 的 group 或 friend 文件引用
- **THEN** group SHALL 调用 `get_group_file_download_url`，friend 在 hash 可用时 SHALL 调用
  `get_private_file_download_url`
- **AND** 没有已确认的 Hermes 文件入口时 SHALL 保留 `[file:<file_id>]` 或不可用占位

#### Scenario: trigger 获取群文件下载链接

- **WHEN** trigger 处理带有 file_id 的 group 文件引用
- **THEN** 系统 SHALL 调用 `get_group_file_download_url` 并传入当前 group_id 与 file_id
- **AND** SHALL 只在存在已确认 Hermes 文件入口时继续处理 download_url
- **AND** 不存在该入口时 SHALL 保留文件 placeholder，不得把 URL 写入 MessageEvent.media_urls

#### Scenario: private file 缺少哈希

- **WHEN** trigger 处理 private 文件引用且缺少 `file_hash`
- **THEN** 系统 SHALL 不调用 `get_private_file_download_url`
- **AND** SHALL 记录 `unsupported` 或 `malformed` 诊断并生成文件不可用占位

#### Scenario: file 没有确认的 Hermes 入口

- **WHEN** Milky file Action 返回 download_url 但当前 Hermes 没有确认文件入口
- **THEN** 系统 SHALL 保留 file_id、文件名和文件不可用 placeholder
- **AND** SHALL 记录 `unsupported`
- **AND** SHALL NOT 把 URL 当成本地路径或执行插件侧下载

#### Scenario: 引用查询失败

- **WHEN** 媒体或 reply 查询失败
- **THEN** 正文 SHALL 保留已生成的稳定 placeholder 和可用文本
- **AND** 诊断 SHALL 保留安全错误分类
- **AND** SHALL 不把原始 URL、异常文本或完整响应写入 MessageEvent
