# Spec Delta

## Purpose

为当前 Milky 会话提供只读、数量有界的贴纸候选搜索，使 Agent 可以根据简短元数据选择已有贴纸，再通过稳定的不透明 ID 精确发送，同时保留不经搜索即可发送的现有路径。

## ADDED Requirements

### Requirement: 搜索工具只在现有贴纸库可用时暴露

插件 MUST 显式注册独立语义 Tool sticker_search；它不对应远端 Milky operationId。工具 SHALL 复用 sticker_send 的现有库可用性边界，空库或没有文件可用的条目时隐藏；注册和只读可用性检查 MUST NOT 创建存储、迁移数据库、联网或创建后台任务。handler MUST 在读取库前验证当前 Milky 会话；上下文缺失返回 missing_session_context，非 Milky、非法或 temp 目标返回 unsupported。活动贴纸服务不可用时 MUST 返回 unsupported，且不得创建旁路服务。

#### Scenario: 库不可用

- **WHEN** 注册或发现工具时贴纸库缺失、为空或没有可用条目
- **THEN** Agent definitions SHALL 不包含 sticker_search
- **AND** SHALL 不创建目录或数据库，其他工具正常可用

#### Scenario: 上下文非法或服务已解绑

- **WHEN** 过期 definition 被调用且当前上下文非法、缺失或活动服务已解绑
- **THEN** 工具 SHALL 返回对应固定分类，不读取贴纸库或发起网络请求

### Requirement: 搜索参数有界且与查询发送一致

sticker_search MUST 只接受 intent、emotion、tags 和 limit；前三个字段沿用 qq-sticker-send 查询模式的类型、值域、长度、归一化和非空校验，且至少提供其中一个有效条件。limit SHALL 默认等于 5，显式值必须是不含 bool 的 1 至 10 整数；null、空查询、非法类型、重复标签、超限字段及未声明字段 MUST 返回 invalid_input，且不得读取库或联网。工具 MUST NOT 接受 sticker_id、目标、路径、URL、category、keyword、index 或分页参数。

#### Scenario: 单条件和默认数量

- **WHEN** Agent 提供一个合法查询条件且省略 limit
- **THEN** 搜索 SHALL 返回最多 5 条候选，不要求补齐其他查询字段

#### Scenario: 非法参数

- **WHEN** Agent 只提供 limit，或传入 limit=0、11、true、null，或提供未声明字段
- **THEN** 工具 SHALL 在读取库前返回 invalid_input

### Requirement: 搜索复用匹配证据且只返回有界元数据

搜索 MUST 使用与查询发送相同的当前生效元数据、候选可见性和词法匹配规则，并按现有相关性层级及命中证据从高到低排序。完全并列候选 SHALL 按 opaque sticker_id 的字典序稳定排序；搜索 MUST NOT 使用随机轮换或发送历史改变排序。搜索 SHALL 对全部符合条件的候选排序后取前 limit 条，而不是只返回最高层级候选。

非空结果 MUST 为 status=ok 和 items；没有匹配条目 MUST 为 status=no_match 和空 items。每项 MUST 只含 sticker_id、emotion、tags、description；ID 沿用已有条目身份，emotion 沿用既有枚举，tags 最多 5 个且每个不超过 16 字符，description 不超过 20 字符。缺失或超出这些边界的条目 SHALL 不作为搜索结果，不通过截断改变其意义；人工清空的标签或描述 SHALL 可分别表示为空数组或空字符串。结果 MUST NOT 包含原始图片、缩略图、路径、URL、内容 hash、统计或匹配解释。元数据 MUST 作为数据返回，不拼接成指令或自动注入普通聊天上下文；日志 MUST NOT 记录查询、描述、标签、完整结果或敏感值。

搜索 SHALL 排除当前已知不可见、文件索引无效或文件缺失的条目；搜索结果仅表示当时可查询的候选，不构成发送成功或文件最终校验承诺。合法无匹配、旧 definition 访问已清空但仍存在的库 SHALL 返回 no_match；存储缺失或不兼容返回 unsupported，存储访问失败返回 storage_error。其他失败结果 MUST 只含固定 status，不伪造 items。

#### Scenario: 搜索得到候选

- **WHEN** 现有库中有多个不同相关性层级的合法匹配条目
- **THEN** 搜索 SHALL 返回按相关性排序的前 limit 条及限定字段
- **AND** 相同库状态和查询的并列排序 SHALL 保持一致，结果无重复 ID

#### Scenario: 无匹配或候选文件缺失

- **WHEN** 没有匹配候选或匹配条目均已知文件缺失
- **THEN** 搜索 SHALL 返回 status=no_match 和 items=[]，不放宽查询条件

#### Scenario: 元数据只作为数据

- **WHEN** 条目的描述包含类似指令的文本
- **THEN** 工具 SHALL 仅将其作为限定字段内的字符串交付，不执行内容或改变工具权限
- **AND** 日志 SHALL 不记录该描述或完整搜索结果

### Requirement: 搜索不改变库、使用历史或当前范围

一次搜索 MUST 不发送消息、不调用远端 Action 或视觉服务、不更新使用次数与时间、不保留搜索结果缓存，也不得创建、迁移或修复存储。本 change SHALL 沿用当前人工共享库的可见范围；当前 chat 只用于可信会话验证，不得把已有使用历史误当作按群隔离的条目权限。搜索与精确发送 MUST 使用一致的条目可见性，ID 不得成为绕过可见性或改变发送目标的凭证。

#### Scenario: 连续搜索后发送

- **WHEN** Agent 连续搜索两次再按返回 ID 显式发送一次
- **THEN** 两次搜索 SHALL 不改变任何使用统计或轮换状态
- **AND** 发送 SHALL 只按既有发送边界计数一次

#### Scenario: 只读库搜索

- **WHEN** 现有兼容库可读但不可写且有可用条目
- **THEN** 搜索 SHALL 正常读取候选，不尝试迁移、修复或写入

### Requirement: 工具说明保持简短且不承载聊天策略

sticker_search 和 sticker_send 的工具描述 MUST 各使用一句能力说明，参数描述只说明含义和必要约束。工具定义 MUST NOT 加入使用时机、聊天场景清单、频率、人格、先搜后发流程或发送后的文字策略；本 change MUST NOT 为此修改平台提示、SOUL 或记忆。bundled skill SHALL 只同步必要的接口和错误分类，不加入上述行为策略。

#### Scenario: 读取工具定义

- **WHEN** Hermes 发现两个贴纸工具
- **THEN** 描述 SHALL 仅说明搜索候选或按查询/ID 发送的能力，必要约束由 schema 和短参数说明表达
- **AND** 原查询发送 SHALL 不依赖先前搜索或额外上下文注入
