# qq-sticker-search Specification

## Purpose

为当前 Milky 会话提供只读、数量有界的贴纸候选发现能力，让 Agent 能明确选择严格搜索、放宽意图条件或浏览；结果必须标明所用模式，不能把兜底候选伪装成查询命中。

## Requirements

### Requirement: 搜索工具发现和请求边界

插件 MUST 注册独立的 `sticker_search` 语义 Tool；它不对应远端 Milky operationId，也不得开放任意 Action catalog。Agent 可见 definitions 只有在当前贴纸库存在至少一个可见、文件索引有效且文件可用的条目时才包含该工具。工具 SHALL 复用 sticker_send 的现有库可用性边界。注册和可用性检查 MUST 不创建目录、数据库、后台任务或网络连接，也不得迁移存储。

`sticker_search` MUST 只接受 `mode`、`intent`、`emotion`、`tags` 和 `limit`。`mode` 可为 `strict`、`fallback` 或 `browse`；省略时，有查询字段默认为 `strict`，没有查询字段默认为 `browse`。`strict` MUST 至少有一个查询字段；`fallback` MUST 同时提供 `intent` 和至少一个 `emotion` 或 `tags`，用于明确放宽意图条件；`browse` MUST 不带查询字段。显式查询字段沿用 qq-sticker-send 查询模式的类型、枚举、长度、归一化、非空和重复校验。`limit` 省略时为 5，显式值 MUST 是 1 至 10 的非布尔整数。工具 MUST 拒绝 `sticker_id`、目标、路径、URL、`category`、`keyword`、`index`、分页字段和其他未声明字段，并在读取库或网络访问前返回 `invalid_input`。

#### Scenario: 未指定模式时的默认模式

- **WHEN** Agent 提供一个或多个查询字段但省略 `mode`
- **THEN** 工具 SHALL 使用 `strict` 模式
- **WHEN** Agent 只提供 `limit` 或传入空对象
- **THEN** 工具 SHALL 使用 `browse` 模式并返回当前可用的有界候选

#### Scenario: 不完整或矛盾的模式参数在访问前失败

- **WHEN** Agent 传入未知字段、显式 null、非法情绪、空标签、重复标签、越界 limit、目标、路径或 URL，或为 `strict`、`fallback`、`browse` 提供不符合各自条件的查询字段
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** SHALL 不读取贴纸文件、不修改存储且不调用 Milky

#### Scenario: 不可用库隐藏搜索工具

- **WHEN** 贴纸库缺失、为空，或没有当前可见且文件可用的条目
- **THEN** Agent definitions SHALL 不包含 `sticker_search`
- **AND** 可用性检查 SHALL 不创建或修复贴纸存储

#### Scenario: 单条件和默认数量

- **WHEN** Agent 提供一个合法查询条件且省略 limit
- **THEN** 搜索 SHALL 返回最多 5 条候选，不要求补齐其他查询字段

### Requirement: 搜索模式必须明确且不得隐式兜底

所有模式 MUST 只使用当前可见、文件索引有效且文件可用的条目。`strict` MUST 沿用既有情绪、标签和意图匹配证据，按既有相关性排序，并列时按不透明 `sticker_id` 字典序稳定排序。命中时 MUST 返回 `status=ok`、`match_mode=strict` 和不超过 `limit` 个候选；无命中时 MUST 返回 `status=no_match`、`match_mode=strict` 和空 `items`，不得自动切换为 fallback 或 browse。

`fallback` MUST 忽略 `intent` 的匹配条件，但 MUST 保留显式 `emotion` 精确筛选和 `tags` 至少命中一个的条件；候选 MUST 按命中的请求 tag 数量降序、再按不透明 `sticker_id` 字典序稳定排序。命中时 MUST 返回 `status=ok`、`match_mode=fallback` 和不超过 `limit` 个候选；无命中时 MUST 返回 `status=no_match`、`match_mode=fallback` 和空 `items`。不得把 fallback 候选描述为满足原 intent。

`browse` MUST 返回当前可用条目中不超过 `limit` 个候选，并按不透明 `sticker_id` 字典序稳定排序，结果标记为 `match_mode=browse`，不得暗示候选与聊天内容相关。仅当当前不存在任何可用条目时，browse 才 MUST 返回空 `items` 和 `status=no_match`。

严格搜索 SHALL 对全部符合条件的候选按相关性层级及命中证据排序后取前 limit 条，不得仅保留最高层级候选。所有搜索模式 MUST 不使用随机轮换或发送历史改变排序。

#### Scenario: 严格搜索命中

- **WHEN** 当前库有满足查询条件且分属不同相关性层级的多个候选
- **THEN** 工具 SHALL 返回 `status=ok`、`match_mode=strict` 和按相关性排序的前 `limit` 条
- **AND** 结果 SHALL 不重复且保持并列排序稳定

#### Scenario: 严格搜索无命中不自动兜底

- **WHEN** 合法查询没有匹配候选，但库中存在其他当前可用条目
- **THEN** 工具 SHALL 返回 `status=no_match`、`match_mode=strict` 和 `items=[]`
- **AND** SHALL 不自动返回其他条目或改变搜索模式

#### Scenario: 显式放宽意图条件

- **WHEN** Agent 使用 `mode=fallback`，并提供 `intent` 以及 `emotion` 或 `tags`
- **THEN** 工具 SHALL 忽略 intent 匹配但保留 emotion 和 tags 条件
- **AND** SHALL 返回 `match_mode=fallback`，不把结果说成严格命中

#### Scenario: 显式浏览

- **WHEN** Agent 使用 `mode=browse` 且未提供查询字段
- **THEN** 工具 SHALL 返回稳定排序、有界且标记为 `match_mode=browse` 的当前可用条目
- **AND** SHALL 不暗示候选符合任何未提供的意图

#### Scenario: 空库或放宽条件仍无命中

- **WHEN** 当前没有可用条目，或 fallback 条件下没有候选
- **THEN** 工具 SHALL 返回 `status=no_match`、对应的 `match_mode` 和 `items=[]`
- **AND** SHALL 不伪造候选

### Requirement: 搜索结果必须有界且只含安全元数据

对于 `status=ok` 和 `status=no_match` 的候选查询结果，工具 MUST 只返回 `status`、`match_mode` 和 `items`；每个 item MUST 只含 `sticker_id`、`emotion`、`tags` 和 `description`。结果 MUST 不包含图片 bytes、缩略图、路径、URL、内容 hash、使用统计、轮换历史、匹配解释或当前会话目标。`limit` MUST 同时约束严格、fallback 和 browse 结果的数量；条目字段超出既有边界或无法验证时不得通过截断改变其含义，也不得进入结果。

搜索结果中的 `sticker_id` 只可作为后续显式 `sticker_send` 的不透明 ID 使用，不代表目标授权、文件永久有效或发送成功。元数据 MUST 作为数据交付，不得被拼接到平台提示或自动注入普通聊天上下文。

每项 MUST 沿用已有条目身份和 emotion 枚举；tags 最多 5 个且每个不超过 16 字符，description 不超过 20 字符。字段缺失的条目 MUST 不进入结果；人工清空的标签或描述 SHALL 可分别表示为空数组或空字符串。

#### Scenario: 结果字段受限

- **WHEN** 搜索返回严格命中、fallback 或 browse 候选
- **THEN** 每个 item SHALL 只包含声明的四个元数据字段
- **AND** SHALL 不泄露本地路径、URL、hash、图片内容或统计信息

#### Scenario: 过期 ID 仍需发送时重新校验

- **WHEN** Agent 使用搜索结果中的 ID 调用 `sticker_send`
- **THEN** 发送工具 SHALL 重新验证当前条目和文件
- **AND** 搜索结果 SHALL 不被视为发送成功或文件有效期承诺

#### Scenario: 元数据只作为数据

- **WHEN** 条目的描述包含类似指令的文本
- **THEN** 工具 SHALL 仅将其作为限定字段内的字符串交付，不执行内容或改变工具权限
- **AND** 日志 SHALL 不记录该描述或完整搜索结果

### Requirement: 搜索必须保持只读和当前会话安全边界

一次搜索 MUST 不发送消息、不调用 Milky Action 或视觉服务、不更新全局或会话使用统计、不改变轮换状态、不创建搜索缓存，也不得创建、迁移或修复存储。handler MUST 先验证当前 task-local Milky 会话；缺少上下文返回 `missing_session_context`，非 Milky、非法或 temp 目标返回 `unsupported`。活动贴纸服务不可用或解绑时 MUST 在读取库前返回 unsupported，不得创建旁路服务。

搜索 SHALL 沿用当前人工共享库的可见范围；当前 chat 只用于可信会话验证，不得把使用历史当作按群隔离的条目权限。搜索与精确发送 MUST 使用一致的条目可见性，ID 不得成为绕过可见性或改变发送目标的凭证。

旧 definition 访问已清空但仍存在的兼容库时 SHALL 返回 status=no_match、对应的 match_mode 和空 items。

存储缺失或不兼容 MUST 返回 `unsupported`，访问故障 MUST 返回 `storage_error`；除固定分类外不得返回原始异常、原始响应或查询正文。其他失败结果 MUST 只含固定 status，不得伪造 items。搜索日志 MUST 不记录查询、完整参数、描述、标签、路径、URL、图片内容或完整结果。

#### Scenario: 连续搜索不产生副作用

- **WHEN** Agent 在同一会话连续调用两次 `sticker_search`
- **THEN** 两次调用 SHALL 不发送消息、不写入统计且不改变后续发送轮换

#### Scenario: 上下文缺失或非法

- **WHEN** 当前 task-local context 缺少合法 Milky chat key、表示 temp 会话或平台不是 Milky
- **THEN** 工具 SHALL 在读取贴纸库前返回 `missing_session_context` 或 `unsupported`
- **AND** SHALL 不回退到其他会话目标

#### Scenario: 连续搜索后发送

- **WHEN** Agent 连续搜索两次再按返回 ID 显式发送一次
- **THEN** 两次搜索 SHALL 不改变任何使用统计或轮换状态
- **AND** 发送 SHALL 只按既有发送边界计数一次

#### Scenario: 只读库搜索

- **WHEN** 现有兼容库可读但不可写且有可用条目
- **THEN** 搜索 SHALL 正常读取候选，不尝试迁移、修复或写入

### Requirement: 工具说明保持简短且不承载聊天策略

sticker_search 和 sticker_send 的工具描述 MUST 各使用一句能力说明，参数描述只说明含义和必要约束。工具定义 MUST NOT 加入使用时机、聊天场景清单、频率、人格、先搜后发流程或发送后的文字策略；插件 MUST NOT 为此修改平台提示、SOUL 或记忆。bundled skill SHALL 只同步必要的接口和错误分类，不加入上述行为策略。

#### Scenario: 读取工具定义

- **WHEN** Hermes 发现两个贴纸工具
- **THEN** 描述 SHALL 仅说明搜索候选或按查询/ID 发送的能力，必要约束由 schema 和短参数说明表达
- **AND** 原查询发送 SHALL 不依赖先前搜索或额外上下文注入
