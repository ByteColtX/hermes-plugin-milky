# Spec Delta

## MODIFIED Requirements

### Requirement: `/milky` 必须格式化返回 get_impl_info 的实现信息

插件 MUST 注册首个 `/milky` 命令。无参数调用时，系统 MUST 使用已连接且由 Milky adapter
生命周期拥有的 client 调用 `get_impl_info`，请求 MUST 为对应 `/api/get_impl_info` 的
HTTP POST、Bearer 认证和 JSON `{}` body。成功时，命令回复正文 MUST 以“Milky · 实现信息”为标题，标题与详情之间空一行，使用固定的可读中文标签展示
`data.impl_name`、`data.impl_version`、`data.milky_version`、`data.qq_protocol_type` 和
`data.qq_protocol_version`；不得展示完整 JSON envelope 或未知扩展字段。协议失败、malformed
或传输未知时不适用成功摘要交付。`/milky sticker` 后的固定子命令 SHALL 在同一 Hermes
插件命令通道中处理：`add [--dry-run]`、`list [--limit <n>]`、`edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]`、`reanalyze <sticker_id>`、`del <sticker_id>`、
`cleanup [--dry-run]` 和 `reindex` SHALL 遵守贴纸维护规范；只有显式 `add` 或 `reanalyze` 路径可以调用
Hermes core 的辅助视觉能力，该路径不得调用 `get_impl_info` 或任意 Milky Action。

同一命令 SHALL 接受 /milky allowlist 与 /milky allowlist help 静态帮助，以及 /milky allowlist list、/milky allowlist add [目标] 和 /milky allowlist del [目标]，并接受 remove 作为 del 的等价别名，按 hot-chat-allowlist 契约处理。合法 allowlist SHALL 不被归类为未知参数；它 SHALL 不调用 get_impl_info 或贴纸维护，只能按该契约返回静态帮助或执行名单读写与回执，不查询来源或目标群状态。所有路径的 slash 权限 SHALL 由 Hermes core 决定。

静态帮助、参数错误和贴纸回执 SHALL 遵守本规范的统一展示要求；既有固定分类在 slash 文本中表示结果语义，不要求展示英文分类原值。新增帮助 SHALL 不触发本条要求中的协议信息或维护操作。

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
- **THEN** 用户 SHALL 收到与安全错误分类对应的固定中文失败标题和必要说明，不直接显示英文状态码前缀、内部操作名称或 JSON；拒绝、响应无效与结果未知 SHALL 能区分
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

## ADDED Requirements

### Requirement: 插件命令必须提供一致的静态帮助与发现路径

系统 MUST 支持 `/milky help` 顶层帮助、`/milky sticker` 与 `/milky sticker help` 等价的贴纸帮助，并保留 `/milky allowlist` 与 `/milky allowlist help` 的等价帮助语义。无参数 `/milky` SHALL 保持实现信息查询。帮助 SHALL 分别使用“Milky · 命令帮助”“Milky · 贴纸维护”“Milky · 会话白名单”标题，以空行分隔 Usage、Commands；必要参数说明及少量 Examples 按需提供，不强制完整 man-page 章节或重复示例；命令行 SHALL 独立换行并缩进两个空格，说明使用简洁中文。顶层帮助 SHALL 展示无参数查询、status 及全部本版本交付命令分支，不列入其他尚未交付 change 的功能。顶层 Usage SHALL 使用 /milky [command] [args...] 表达可选分支和分支参数，用一句话说明无参数查询行为；Commands SHALL 只列真实子命令。帮助 SHALL 使用方括号表示可选部分、尖括号表示值占位符、省略号表示后续参数的 CLI 记法，不将“（无参数）”列为子命令。该概括语法 SHALL 不放宽各分支的实际参数校验。

help SHALL 不接受额外参数；命令关键词 SHALL 延续大小写不敏感行为，不改写 ID、目标或 option 值。帮助 SHALL 在 Hermes core 分发后静态返回，不依赖活动 client、管理实例、profile 或贴纸存储，不产生网络、配置读取、扫描、视觉调用、存储初始化或普通 Agent turn。帮助的可达性 SHALL 继续服从既有 Gate 和 core 授权；白名单外路由例外 SHALL 仍仅适用于 hot-chat-allowlist 已声明的直接语法，不因帮助统一而扩大。

#### Scenario: 顶层帮助无需协议连接

- **WHEN** core 已分发 `/milky help`，当前没有唯一活动 Milky client
- **THEN** 系统 SHALL 返回包含默认查询说明以及 status、sticker、allowlist 与 help 的静态帮助
- **AND** SHALL 不请求协议信息或访问配置与存储

#### Scenario: 贴纸空参数与帮助等价

- **WHEN** core 分别分发 `/milky sticker`、`/milky sticker help` 或其关键词大小写变体
- **THEN** 系统 SHALL 返回相同的分段帮助，展示全部维护动词、支持的选项、删除别名和可复制示例
- **AND** 即使图库不存在，SHALL 不创建持久目录或打开数据库

#### Scenario: 帮助不能扩大白名单外路由

- **WHEN** 未放行会话发送 /milky status、`/milky help`、`/milky sticker help` 或 `/milky sticker remove demo_id`
- **THEN** 系统 SHALL 继续执行普通会话 Gate，不给予白名单管理路由例外
- **AND** 合法的直接 `/milky allowlist help` SHALL 保持既有 core 分发边界

### Requirement: 参数错误必须提供就近且可执行的用法提示

非法输入 SHALL 返回“指令格式不正确。”，随后以空行分隔 Usage 和 Help，内容使用独立缩进命令行，不回显原始输入、不拼接完整命令树或异常正文。未知顶层分支 SHALL 指向 `/milky help`；未知 sticker 动词 SHALL 指向 `/milky sticker help`；已识别 sticker 动词的参数错误 SHALL 展示该动词完整合法语法，并指向贴纸帮助。allowlist SHALL 按 hot-chat-allowlist delta 提供同样就近的 Usage 与 Help，已知动词只显示自身语法；list/help 不暗示接受目标。参数错误 SHALL 在操作或运行依赖访问前返回，不隐式执行无参数查询或其他分支。

#### Scenario: 已识别操作参数有误

- **WHEN** core 分发 `/milky sticker edit demo_id`，但缺少字段选项
- **THEN** 回复 SHALL 展示 edit 的参数语法与 `/milky sticker help`
- **AND** SHALL 不打开图库、不修改条目或调用视觉

#### Scenario: 未知分支与带多余参数的帮助

- **WHEN** 输入为 `/milky unknown`、`/milky help extra` 或 `/milky sticker help extra`
- **THEN** 回复 SHALL 使用对应层级的 Usage 和 Help
- **AND** SHALL 不把非法输入当作合法帮助、协议查询或维护操作执行

### Requirement: 插件回执必须使用一致且真实的中文结果表达

插件拥有的 slash 回执 SHALL 采用纯文本。帮助和查询 SHALL 使用 `Milky · 功能名` 标题；操作与失败 SHALL 以中文结果标题开头，必要的安全对象标识独立成行，补充说明前空一行。用户正文 SHALL 不使用裸 JSON、英文错误前缀或内部异常代替解释。固定状态 SHALL 映射到受控中文文案，帮助中的命令、参数 token 与来源标识 SHALL 保持可复制的原值。

回执 SHALL 区分已执行、未作更改、预览、部分失败、结果未知以及已保存但未生效，不依据通用成功 envelope 推断整批成功，不把未知结果表述为“未执行”。allowlist 的持久化/运行状态、完整列表及来源表达 SHALL 继续遵守 hot-chat-allowlist；不得套用贴纸条数限制或增加冗余查看名单提示。格式化 SHALL 不触发重试、补查、回滚或第二次业务操作，长消息 SHALL 复用既有发送流程。该约定 SHALL 不改写 Hermes 内置命令、Web JSON、共享业务结果或 Agent Tool 返回。

#### Scenario: 协议信息失败分类可辨

- **WHEN** 协议信息查询遇到无可归属连接、远端拒绝、无效响应或传输结果未知
- **THEN** 系统 SHALL 分别说明暂不可用、请求被拒绝、响应无法解析或无法确认查询结果
- **AND** SHALL 不暴露底层错误、凭证或完整响应，不把全部失败归为同一无信息提示

#### Scenario: 白名单状态保持原有意义

- **WHEN** allowlist 更改已保存但未发布到当前运行，或重复添加已有字面规则
- **THEN** 前者 SHALL 明示尚未生效和重启 Gateway 的建议，后者 SHALL 明示规则已存在及未作更改
- **AND** SHALL 不统一替换成“操作成功”，不因发送失败再次修改规则

#### Scenario: 共享消费者保持机器契约

- **WHEN** 相同贴纸业务结果分别交付 slash、Web 或其他已有结构化消费者
- **THEN** slash SHALL 显示中文文本，其他消费者 SHALL 继续接收既有字段与固定分类
- **AND** 任一消费者 SHALL 不需要解析中文回执才能执行后续业务

### Requirement: 运行状态查询必须反映当前实例的可确认状态

系统 MUST 在同一插件命令入口提供 /milky status，只接受无附加参数的 status 子命令，关键词延续大小写不敏感。core 允许后，回复 SHALL 以“Milky · 运行状态”为标题，按插件状态、事件流状态、本次运行时长、运行白名单条数和白名单配置一致性的顺序提供只读摘要。status SHALL 服从普通会话 Gate 和 core 授权，不属于白名单外管理路由例外。

插件运行与事件流连接 SHALL 分开表达。当前实例完成初始化进入运行阶段可显示“插件: 运行中”；事件流 SHALL 依据其生命周期观察区分“连接中”“已连接”“重连中”“已停止”和“未知”。只有观察到当前连接成功且未观察到断开时才可显示已连接；首次连接失败后重试或退避 SHALL 显示重连中，不能仅根据插件就绪、任务存在或历史成功显示已连接。没有新事件 SHALL 不单独作为断线依据。摘要 SHALL 不宣称实时验证 QQ 登录状态、Action 可用性或端到端收发健康。

本次运行 SHALL 表示当前实例自初始化完成进入运行阶段后的单调经过时间，SSE 自动重连不中断累计；停止或运行失败后不继续累计，新的运行代次重新开始。少于一分钟 SHALL 显示“不足 1 分钟”，其他时长按天、小时、分钟的非零部分显示并舍去秒，不使用墙钟差值造成倒退。尚未开始且可确认时 SHALL 显示“尚未开始”，未知起点 SHALL 显示“未知”。

状态 SHALL 只属于当前注册作用域下唯一可确认的实例和可信 profile；多个实例无法唯一归属、没有可确认实例、实例与当前 profile 的归属无法确认或读取期间实例已失效时 SHALL 整条返回“运行状态暂不可用”与安全原因，不能借用环境默认、最近会话或已解绑实例。已绑定实例可确认启动/停止/失败阶段时 SHALL 如实表达；缺少某字段的观察能力时该字段 SHALL 显示未知。状态生成 SHALL 不建立网络连接、调用 Milky Action、触发群状态准备、视觉能力或图库访问，不创建后台任务、不改变运行状态；回执仍通过原发送路径交付。此无额外网络约束 SHALL 限定于 status 处理，不改变普通入站 Gate 既有的按需群状态准备与出站回执发送。

#### Scenario: 正常运行摘要

- **WHEN** core 分发 status，唯一可信实例已运行 2 小时 18 分钟，且观察到 SSE 当前已连接
- **THEN** 回复 SHALL 显示“插件: 运行中”“事件流: 已连接”“本次运行: 2 小时 18 分钟”以及白名单摘要
- **AND** SHALL 不为查询状态额外发起 HTTP、SSE 或群状态请求

#### Scenario: SSE 重连期间仍在运行

- **WHEN** 当前实例仍在运行，但事件流正在断线退避或尝试重连
- **THEN** 回复 SHALL 显示“事件流: 重连中”，本次运行时间继续累计
- **AND** 首次 SSE 尚未建立时 SHALL 显示连接中，首次失败进入重试后 SHALL 显示重连中，不能以插件就绪伪造已连接

#### Scenario: 计时随实例运行代次变化

- **WHEN** SSE 内部断开重连，随后整个实例停止并重新进入运行阶段
- **THEN** 内部重连 SHALL 不重置本次计时，实例停止 SHALL 停止累计，新运行代次 SHALL 从新起点累计
- **AND** 系统时间调整 SHALL 不导致经过时长倒退，缺少起点 SHALL 显示未知而非零

#### Scenario: 实例归属或部分状态不可确认

- **WHEN** 没有可信状态实例、存在多个无法区分的实例、实例与当前 profile 的归属无法确认，或调用期间实例被解绑、运行代次变化
- **THEN** status SHALL 返回运行状态暂不可用，不读取其他 profile 配置或报告伪造运行信息
- **AND** 唯一实例仍可信但缺少事件流观察能力时 SHALL 保留可确认字段，事件流显示未知

#### Scenario: status 拒绝额外参数

- **WHEN** core 分发 /milky status extra、/milky status --refresh 或其他附加参数
- **THEN** 回复 SHALL 使用中文格式错误，Usage 展示 /milky status，Help 指向 /milky help
- **AND** SHALL 不读取运行快照或配置，不执行主动探测

### Requirement: 运行状态的白名单摘要必须区分运行规则与配置一致性

status 中“运行白名单: N 条规则” SHALL 只统计当前实例已经发布的字面规则条数，每个通配符计一条，不把条数当作可访问会话数量。运行规则未知时 SHALL 显示未知，不能用零代替。当前运行集合为空时 SHALL 显示 0 条并说明当前不接收任何会话的普通消息。

配置一致性 SHALL 在同一可信 profile 中只读取得最新持久有效白名单，与本次运行规则比较；只有取得有效结果且确认观察期间实例代次和运行规则版本未变时才可报告一致或不同。相同时 SHALL 显示“白名单配置与当前运行一致。”，不同时 SHALL 显示“白名单配置与当前运行不同。”并提示重启 Gateway。实例及 profile 归属仍可信，仅配置读取失败、配置非法或运行规则版本变化导致比较无法确认时 SHALL 显示“白名单配置一致性未知。”，其他已确认字段仍可显示。若实例归属失效或运行代次变化，SHALL 整条返回“运行状态暂不可用”，不得仅降级配置一致性字段。

status SHALL 不展示具体规则、来源 profile 路径、服务地址、Bot 身份、凭证、配置正文或异常文本，不比较白名单以外的设置。读取 SHALL 不初始化、修改、保存或发布配置，不调用白名单写操作，不自动重试或隐式重载；发送失败 SHALL 不引发状态变更。

#### Scenario: 白名单规则条数与配置一致

- **WHEN** 运行集合共有 6 个字面条目且包含通配符，可信配置读取确认相同规则
- **THEN** 回复 SHALL 显示“运行白名单: 6 条规则”和“白名单配置与当前运行一致。”
- **AND** SHALL 不展开通配符、不输出完整名单或将 6 条规则描述为 6 个会话

#### Scenario: Web 保存后尚未运行应用

- **WHEN** 最新持久有效白名单与当前运行规则不同
- **THEN** status SHALL 显示当前运行规则的条数、白名单差异和重启提示
- **AND** SHALL 不调用规则发布，不用新配置条数替换运行条数

#### Scenario: 配置不可读或观察期间变化

- **WHEN** 实例及 profile 归属仍可信，但白名单配置读取失败、配置无效，或观察期间运行规则版本变化
- **THEN** 回执 SHALL 显示白名单配置一致性未知，保留仍可确认的插件和事件流状态
- **AND** SHALL 不报告一致、不将读取失败解释为空名单、不无限重试

#### Scenario: 空运行白名单

- **WHEN** 唯一实例已发布的运行规则集合为空
- **THEN** 回复 SHALL 显示 0 条及普通消息全部阻止的说明
- **AND** SHALL 不把空名单表述为插件停止或事件流断开

#### Scenario: 相同条数不代表规则一致

- **WHEN** 配置与运行白名单条数相同，但字面规则集合不同
- **THEN** status SHALL 报告白名单配置与当前运行不同
- **AND** SHALL 不以计数相等或历史读取结果代替集合比较
