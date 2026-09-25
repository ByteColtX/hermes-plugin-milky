# Spec Delta

## MODIFIED Requirements

### Requirement: 斜杠命令必须在 Will 之前进入独立通道

对于已经通过协议解析、canonical、TTL dedup、per-chat admission 和 Gate 的 friend 或
group message_receive，当消息是可识别的斜杠命令时，系统 MUST 在 wait buffer 和 Will
之前将其交给 Hermes gateway control 通道。白名单管理路由例外 SHALL 按 hot-chat-allowlist 契约进入 core，其管理读写不查询来源或目标群状态。命令 SHALL NOT 增长 wait buffer、进行 Will 评分、触发资源补全或创建普通 Agent turn。白名单管理提交导致撤销时 SHALL 按 hot-chat-allowlist 契约清理失效会话的旧等待与 Will 状态，这不属于命令正文参与普通消息策略。

所有 slash 指令的权限 MUST 完全由 Hermes core 管理。插件 MUST NOT 自行解析管理员名单、判断角色、复制命令许可或新增子命令权限门禁；core 放行后 SHALL 仅执行参数、操作对象与运行状态检查。core 拒绝 SHALL 不触发插件管理读写或状态准备；插件 MUST NOT 绕过 core 直接执行指令。

#### Scenario: 合法群内置命令

- **WHEN** 合法 group 消息的纯文本正文为 /status
- **THEN** 消息 SHALL 经过既有身份、去重和会话 Gate 后进入 Hermes 命令通道，由 core 判断权限
- **AND** SHALL 不进入 Will、wait buffer 或普通 Agent 正文

#### Scenario: Gate 拒绝命令

- **WHEN** 斜杠命令来自 self，或不属于白名单管理路由例外且未通过来源会话白名单/禁言 Gate
- **THEN** 命令 SHALL 在 Gate 阶段被拒绝
- **AND** SHALL 不调用 Hermes 命令 handler、Milky Action、Will 或 buffer

#### Scenario: 普通正文保持原有 Will 路径

- **WHEN** 消息正文不是可识别的斜杠命令
- **THEN** 消息 SHALL 继续按照既有 wait/trigger Will 流水线处理
- **AND** SHALL 不因正文包含普通斜杠字符而进入命令通道

纯文本直接 /milky allowlist 固定子命令 SHALL 依照 hot-chat-allowlist 契约，在来源白名单未放行时仍进入 core 分发。路由例外 SHALL 不预先检查发送者管理员身份；core 允许并完成参数校验后，管理 handler SHALL 直接执行名单读写，不查询来源或目标群状态。该例外 MUST NOT 扩展到其他 /milky 子命令、其他命令的别名展开或普通正文；已通过普通会话 Gate 的 core 别名 SHALL 不被插件额外拒绝。无法确定可信来源/profile/实例时 SHALL 返回 unsupported，不借用环境中的旧会话。

#### Scenario: 白名单外群管理员启用当前群

- **WHEN** 来源群未放行，发送者发送 /milky allowlist add 且 core 允许
- **THEN** 系统 SHALL 在 core 分发后校验参数与可信操作上下文，执行当前群的管理操作
- **AND** SHALL 不另查管理员名单、不查询群状态，且不触发普通 Agent turn

#### Scenario: 普通用户获准使用 milky 命令

- **WHEN** 普通用户获 core 允许执行 /milky，但未命中管理员列表
- **THEN** 插件 SHALL 按相同参数和运行条件处理 allowlist 子命令
- **AND** SHALL 不额外要求白名单管理员身份

#### Scenario: core 拒绝白名单外指令

- **WHEN** 规范白名单管理指令从未放行会话到达 core，但 core 拒绝
- **THEN** 插件 SHALL 不执行名单读写、群状态准备或规则发布
- **AND** 拒绝反馈 SHALL 沿宿主既有路径处理，发送仍须遵守群禁言边界

#### Scenario: core 允许后来源群状态不可用

- **WHEN** core 已分发管理指令，来源或目标群状态未知或已禁言
- **THEN** 插件 SHALL 正常执行规则读写，不查询群状态或附加禁言提示
- **AND** 回执 SHALL 沿既有发送流程处理，发送失败不得重放修改

### Requirement: `/milky` 必须格式化返回 get_impl_info 的实现信息

插件 MUST 注册首个 `/milky` 命令。无参数调用时，系统 MUST 使用已连接且由 Milky adapter
生命周期拥有的 client 调用 `get_impl_info`，请求 MUST 为对应 `/api/get_impl_info` 的
HTTP POST、Bearer 认证和 JSON `{}` body。成功时，命令回复正文 MUST 使用固定的可读文本格式展示
`data.impl_name`、`data.impl_version`、`data.milky_version`、`data.qq_protocol_type` 和
`data.qq_protocol_version`；不得展示完整 JSON envelope 或未知扩展字段。协议失败、malformed
或传输未知时不适用成功摘要交付。`/milky sticker` 后的固定子命令 SHALL 在同一 Hermes
插件命令通道中处理：`add [--dry-run]`、`list [--limit <n>]`、`edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]`、`reanalyze <sticker_id>`、`del <sticker_id>`、
`cleanup [--dry-run]` 和 `reindex` SHALL 遵守贴纸维护规范；只有显式 `add` 或 `reanalyze` 路径可以调用
Hermes core 的辅助视觉能力，该路径不得调用 `get_impl_info` 或任意 Milky Action。

同一命令 SHALL 接受 /milky allowlist 与 /milky allowlist help 静态帮助，以及 /milky allowlist list、/milky allowlist add [目标] 和 /milky allowlist del [目标]，并接受 remove 作为 del 的等价别名，按 hot-chat-allowlist 契约处理。合法 allowlist SHALL 不被归类为未知参数；它 SHALL 不调用 get_impl_info 或贴纸维护，只能按该契约返回静态帮助或执行名单读写与回执，不查询来源或目标群状态。所有路径的 slash 权限 SHALL 由 Hermes core 决定。

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
- **AND** SHALL 解析每次视觉调用的外层 envelope，并仅将 `success=true` 且内层 `analysis` 通过 JSON/schema 校验且 `is_sticker=true` 的图片从 inbox 移动到 library；合法 `is_sticker=false` 的图片 SHALL 移动到 `junk/` 且不得入库；回执 SHALL 返回创建、重复、`junk`、拒绝、`visual_unavailable` 和其他固定失败摘要
- **AND** 超出 50 张批次上限的候选 SHALL 返回 `batch_deferred` 并保留在 inbox
- **AND** 视觉分析失败、envelope 非法或内层 schema 非法的候选 SHALL 保留在 inbox，供下一次 add 增量重试
- **AND** 成功处理的 `is_sticker=true` 或 `is_sticker=false` 原文件 SHALL 不再留在 inbox
- **AND** SHALL 不进入 Will、wait buffer、普通 Agent turn、主 Agent transcript 或 Milky Action

#### Scenario: sticker add dry-run 只预览视觉结果

- **WHEN** 插件 command handler 收到 `sticker add --dry-run` 参数
- **THEN** 系统 SHALL 执行与正式 add 相同的文件校验、hash 去重、50 张批次上限和最多 10 个并发的命令级视觉辅助
- **AND** SHALL 返回候选的主情绪、中文检索标签、描述摘要和 `is_sticker` 判定；`true` 候选 SHALL 标记为 `would_add`，`false` 候选 SHALL 标记为 `would_move_to_junk`
- **AND** 视觉元数据不决定 `true` 候选的情绪修正，但外层 envelope 失败、内层 `analysis` 非法或字段非法的候选不移动
- **AND** 超出 50 张批次上限的候选 SHALL 返回 `batch_deferred`
- **AND** SHALL 不移动、删除或写入贴纸文件、数据库记录或可见条目

#### Scenario: sticker edit 手动修正视觉元数据

- **WHEN** 插件 command handler 收到 `sticker edit <sticker_id>` 及一个或多个合法的 set/clear option
- **THEN** 系统 SHALL 只更新指定字段；未指定字段 SHALL 保持不变
- **AND** 设置字段 SHALL 将对应字段来源标记为 `manual`，`--clear=<field>` SHALL 恢复对应视觉基线并将该字段来源改回 `vision`
- **AND** 行级 `source` SHALL 派生为任一字段为 `manual` 时的 `manual`，并可通过 `field_sources` 查看具体字段来源
- **AND** SHALL 不修改图片文件、content hash、技术索引或 sticker ID

#### Scenario: sticker reanalyze 重新生成视觉基线

- **WHEN** 插件 command handler 收到 `sticker reanalyze <sticker_id>` 参数
- **THEN** 系统 SHALL 使用同一固定视觉 prompt 分析对应 library 文件
- **AND** 合法 `is_sticker=true` 时 SHALL 更新视觉基线，并只让来源为 `vision` 的当前字段跟随新结果
- **AND** 来源为 `manual` 的字段、图片文件、content hash、技术索引和 sticker ID SHALL 保持不变
- **AND** 合法 `is_sticker=false` 时 SHALL 返回 `not_sticker` 并保留原条目，不移动到 `junk/`
- **AND** 视觉失败或结构非法时 SHALL 返回 `visual_unavailable` 并保留原条目

#### Scenario: `/milky sticker list` 只读列举

- **WHEN** 插件 command handler 收到 `sticker list` 或带合法 `--limit` 的 list 参数
- **THEN** 系统 SHALL 返回稳定、有界的贴纸摘要
- **AND** SHALL 不修改贴纸文件、元数据或远端 QQ 状态

#### Scenario: `/milky` 带参数

- **WHEN** 用户发送 `/milky extra` 或未声明的 sticker/allowlist 子命令及非法参数
- **THEN** 命令 SHALL 返回安全的参数错误或 usage 提示
- **AND** SHALL 不调用 `get_impl_info`、贴纸维护、白名单读写操作或其他 Milky Action

#### Scenario: Action 被拒绝或结果未知

- **WHEN** `get_impl_info` 返回 rejected、malformed、HTTP 错误、连接/超时或 transport_unknown
- **THEN** 用户 SHALL 收到只包含安全错误分类的失败提示
- **AND** 提示 SHALL 不包含 Authorization、token、完整响应正文或底层异常文本

#### Scenario: allowlist 合法子命令分发

- **WHEN** core 允许的调用收到合法 allowlist list、add、del 或其别名 remove 参数且运行条件满足
- **THEN** 命令 SHALL 进入白名单管理流程，省略增减目标时使用可信当前会话
- **AND** SHALL 不返回未知参数错误、不调用 get_impl_info 或贴纸维护

#### Scenario: allowlist 非法参数不回退

- **WHEN** 调用参数为 allowlist 未知子命令、非法目标、额外参数（包括任何分页参数）
- **THEN** 命令 SHALL 返回 invalid_input 或安全 usage 提示
- **AND** SHALL 不读写名单、不查询群状态、不回退协议摘要或贴纸维护

#### Scenario: allowlist 静态帮助分发

- **WHEN** core 允许调用者执行 allowlist 或 allowlist help
- **THEN** 命令 SHALL 返回相同静态帮助，不依赖唯一活动管理实例
- **AND** SHALL 不调用 get_impl_info、贴纸维护、配置读写或群状态查询；core 拒绝时 SHALL 不执行帮助 handler
