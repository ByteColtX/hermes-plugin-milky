## MODIFIED Requirements

### Requirement: `/milky` 必须格式化返回 get_impl_info 的实现信息

插件 MUST 注册首个 `/milky` 命令。无参数调用时，系统 MUST 使用已连接且由 Milky adapter
生命周期拥有的 client 调用 `get_impl_info`，请求 MUST 为对应 `/api/get_impl_info` 的
HTTP POST、Bearer 认证和 JSON `{}` body。成功时，命令回复正文 MUST 使用固定的可读文本格式展示
`data.impl_name`、`data.impl_version`、`data.milky_version`、`data.qq_protocol_type` 和
`data.qq_protocol_version`；不得展示完整 JSON envelope 或未知扩展字段。协议失败、malformed
或传输未知时不适用成功摘要交付。`/milky sticker` 后的固定子命令 SHALL 在同一 Hermes
插件命令通道中处理：`add [--dry-run]`、`list [--limit <n>]`、`edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]`、`del <sticker_id>`、
`cleanup [--dry-run]` 和 `reindex` SHALL 遵守贴纸维护规范；只有显式 `add` 路径可以调用
Hermes core 的辅助视觉能力，该路径不得调用 `get_impl_info` 或任意 Milky Action。

#### Scenario: 成功获取协议端信息

- **WHEN** 已连接 adapter 收到无参数 `/milky`
- **THEN** 系统 SHALL POST `/api/get_impl_info` 并发送 `{}`
- **AND** 成功回复 SHALL 返回包含上述 5 个已知字段的格式化中文摘要

#### Scenario: get_impl_info 数据形状

- **WHEN** Action 返回成功 envelope 且 `data` 包含实现名、实现版本、Milky 版本、QQ 协议类型和 QQ 协议版本
- **THEN** 命令 SHALL 将已知字段重新组织成格式化中文摘要
- **AND** SHALL 不把未知顶层或 `data` 扩展字段带入回复

#### Scenario: sticker add 触发人工导入和视觉打标

- **WHEN** 插件 command handler 收到 `sticker add` 参数
- **THEN** 系统 SHALL 扫描固定持久目录的 inbox，先完成文件校验和 hash 去重，再按稳定顺序最多将 50 张唯一候选放入命令级视觉队列，同时最多执行 10 个视觉调用
- **AND** SHALL 解析每次视觉调用的外层 envelope，并仅将 `success=true` 且内层 `analysis` 通过 JSON/schema 校验的图片立即写入库；回执 SHALL 返回创建、重复、拒绝、`visual_unavailable` 和其他固定失败摘要
- **AND** 超出 50 张批次上限的候选 SHALL 返回 `batch_deferred` 并保留在 inbox
- **AND** 视觉分析失败的候选 SHALL 保留在 inbox，供下一次 add 增量重试
- **AND** SHALL 不进入 Will、wait buffer、普通 Agent turn、主 Agent transcript 或 Milky Action

#### Scenario: sticker add dry-run 只预览视觉结果

- **WHEN** 插件 command handler 收到 `sticker add --dry-run` 参数
- **THEN** 系统 SHALL 执行与正式 add 相同的文件校验、hash 去重、50 张批次上限和最多 10 个并发的命令级视觉辅助
- **AND** SHALL 返回候选的主情绪、中文检索标签和描述摘要；视觉元数据不决定人工筛选，但外层 envelope 失败、内层 `analysis` 非法或字段非法的候选不进入库
- **AND** 超出 50 张批次上限的候选 SHALL 返回 `batch_deferred`
- **AND** SHALL 不写入贴纸文件、数据库记录或可见条目

#### Scenario: sticker edit 手动修正视觉元数据

- **WHEN** 插件 command handler 收到 `sticker edit <sticker_id>` 及一个或多个合法的 set/clear option
- **THEN** 系统 SHALL 只更新指定字段；未指定字段 SHALL 保持不变
- **AND** 设置字段 SHALL 将对应字段来源标记为 `manual`，`--clear=<field>` SHALL 恢复对应视觉基线并将该字段来源改回 `vision`
- **AND** 行级 `source` SHALL 派生为任一字段为 `manual` 时的 `manual`，并可通过 `field_sources` 查看具体字段来源
- **AND** SHALL 不修改图片文件、content hash、技术索引或 sticker ID

#### Scenario: `/milky sticker list` 只读列举

- **WHEN** 插件 command handler 收到 `sticker list` 或带合法 `--limit` 的 list 参数
- **THEN** 系统 SHALL 返回稳定、有界的贴纸摘要
- **AND** SHALL 不修改贴纸文件、元数据或远端 QQ 状态

#### Scenario: `/milky` 带参数

- **WHEN** 用户发送 `/milky extra` 或未声明的 sticker 子命令/参数
- **THEN** 命令 SHALL 返回安全的参数错误或 usage 提示
- **AND** SHALL 不调用 `get_impl_info`、贴纸维护操作或其他 Milky Action

#### Scenario: Action 被拒绝或结果未知

- **WHEN** `get_impl_info` 返回 rejected、malformed、HTTP 错误、连接/超时或 transport_unknown
- **THEN** 用户 SHALL 收到只包含安全错误分类的失败提示
- **AND** 提示 SHALL 不包含 Authorization、token、完整响应正文或底层异常文本

### Requirement: 命令注册和 client 生命周期必须安全降级

斜杠命令注册阶段 MUST 只登记 handler 和静态元数据，不建立 Milky HTTP/SSE 连接。无参数
`/milky` handler MUST 使用 adapter connect 时绑定的同一 client；未连接、已停止或无法确定
唯一活动 client 时，`/milky` 的协议信息路径 MUST 在网络访问前返回 `unsupported`，不得临时
创建旁路 client。`/milky sticker` 路径 MAY 只使用插件持久化和可用的 Hermes task-local 会话上下文，
但不在 handler 内验证命令来源，并不得因本地维护临时创建 client。命令诊断、
fixture 和结果 MUST 遵守既有秘密脱敏边界。

#### Scenario: 注册阶段无网络

- **WHEN** Hermes 加载 Milky plugin 并调用其根 `register(ctx)`
- **THEN** `/milky` SHALL 出现在插件命令 registry
- **AND** 注册过程 SHALL 不发送 HTTP/SSE 请求、不读取协议响应、不启动长期后台任务或扫描贴纸目录

#### Scenario: adapter 未连接

- **WHEN** 用户在 Milky adapter 完成 connect 前或 disconnect 后调用 `/milky`
- **THEN** 协议信息路径 SHALL 返回 `unsupported` 或等价的未连接提示
- **AND** SHALL 不建立新 client、不访问网络且不伪造 JSON 成功

#### Scenario: 贴纸维护不创建旁路 client

- **WHEN** 插件 command handler 收到 `sticker list` 或其他贴纸子命令
- **THEN** 系统 SHALL 只访问插件持久化边界和可用的 task-local 会话上下文
- **AND** SHALL 不创建第二个 Milky client、不发起 Milky Action 或 SSE 请求

#### Scenario: 多活动 client 无法唯一归属

- **WHEN** 宿主同时存在多个活动 Milky client 且插件命令 handler 没有 source/profile 参数可用于选择
- **THEN** 协议信息路径 SHALL 安全返回 `unsupported`
- **AND** 贴纸路径 SHALL 不随机选择 client 或把信息写入错误 profile

#### Scenario: 命令诊断脱敏

- **WHEN** 命令注册、请求、贴纸扫描或响应解析失败
- **THEN** 日志和用户可见结果 SHALL 只保留命令名、错误分类和必要的安全 reason
- **AND** SHALL 不包含 token、Authorization header、真实 QQ/群 ID、媒体路径、完整响应、图片内容或完整异常
