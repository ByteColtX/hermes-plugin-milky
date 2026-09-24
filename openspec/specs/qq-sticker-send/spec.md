# qq-sticker-send Specification

## Purpose

为 Hermes Agent 提供一个只能面向当前 Milky 会话、依据本地贴纸元数据选择并发送单张 QQ 贴纸的受限能力。

## Requirements

### Requirement: Tool 发现和参数边界

插件 MUST 注册独立的 `sticker_send` ToolSpec；它不是 Milky `operationId`，也不是任意 Action catalog。
插件 MUST 通过 manifest 的 `python_dependencies` 和项目运行时依赖声明提供 `Pillow>=12.3.0` 与
`jieba>=0.42.1`，且不得把 `jieba` 作为 optional extra 或按需导入。Agent 可见 definitions 只有在现有
`stickers.db` 中存在当前可见、`sticker_files` 关联有效且 library 文件可用的条目时才包含该工具。
空库检查不得创建目录或数据库。
Tool SHALL 接受互斥的两种输入：至少一个有效 `intent`、`emotion`、`tags` 查询条件，或单独一个有效 `sticker_id`。额外字段、目标、路径、URL、混合模式和空输入 MUST 在文件或网络访问前返回 `invalid_input`。搜索返回的 opaque ID 可以用于精确发送，发送不要求先调用搜索。

#### Scenario: 空库隐藏工具

- **WHEN** 贴纸库没有可用条目
- **THEN** Agent definitions SHALL 不包含 `sticker_send` 且不得创建贴纸存储

### Requirement: 目标和查询必须受信

Tool MUST 从 task-local `HERMES_SESSION_PLATFORM` 与 `HERMES_SESSION_CHAT_ID` 获取目标；平台必须为 `milky`，目标必须是合法
`dm:<十进制 QQ 号>` 或 `group:<十进制群号>`。Tool MUST NOT 使用 `HERMES_SESSION_ID`、home channel、默认目标或 Agent 参数。
缺失上下文返回 `missing_session_context`，非法或非 Milky 上下文返回 `unsupported`。

#### Scenario: 目标上下文缺失

- **WHEN** task-local context 缺少合法 Milky chat key
- **THEN** Tool SHALL 在网络访问前返回固定失败分类

### Requirement: 匹配使用当前元数据且相关性优先

查询发送模式下，系统 MUST 只读取当前生效的 `emotion`、`tags`、`description` 以及有效 `sticker_files` 关联；`manual` 与 `vision` 来源不得改变
权重。`emotion` 严格筛选，多个请求 `tags` 为 OR，已提供字段之间为 AND。`intent` 使用统一 Unicode 归一化和本地 `jieba`
分词，按完整短语、全部 token、部分 token 的固定层级比较，不计算数值分数或使用阈值。无情绪时必须存在 tag、短语或 token 证据；
仅情绪查询可直接进入候选池。仅最终比较完全并列的候选可以使用当前 chat 的历史做软轮换，最近使用不得硬排除明显更优候选。

ID 模式 MUST 精确解析指定条目，不执行上述词法匹配或候选轮换；其可见性、文件和发送校验仍然适用。

#### Scenario: 相关性优先

- **WHEN** 一个候选的匹配证据明显优于其他候选
- **THEN** 系统 SHALL 优先选择该候选且不得因最近使用强制换图

### Requirement: 文件校验、统计和发送

选定条目 MUST 通过受控 library containment、regular-file、图片格式、双索引 SHA-256 和一次性 materialization 校验；失败不得静默换图。
本地校验成功后，Tool MUST 在短事务中只更新一次全局 `use_count`/`last_used_at` 和 `(chat_key, sticker_id)` 使用记录，再调用一次
`send_private_message` 或 `send_group_message`。消息只含一张 `image` segment，且 `sub_type` 严格为 `sticker`；不得附加 caption、文本、上传、重试或
fallback。统计不等待远端结果，远端失败或未知不回滚统计。

#### Scenario: 发送边界唯一

- **WHEN** 选定贴纸通过本地校验并进入发送边界
- **THEN** 系统 SHALL 只执行一次对应 Milky 消息 Action

### Requirement: 结果分类和生命周期

成功返回 `status=sent` 和 Milky `message_id`，不得返回内部 `sticker_id`；没有候选返回 `no_match`。参数、上下文、文件、存储、协议拒绝、HTTP、malformed 和 transport unknown MUST 使用固定机器可读分类。注册、连接、SSE、普通 Agent 输出和 disconnect MUST 不打开贴纸 store、扫描 library、创建检索后台任务或执行网络 I/O；`jieba` 作为正常运行时依赖随插件模块加载，不得在 Tool discovery 中按需导入。过期 definition 和未连接 sender MUST fail closed。

查询发送模式没有足够匹配证据时 MUST 返回 `status=no_match` 和 `alternatives` 数组。当原查询同时包含 `intent` 与至少一个 `emotion` 或 `tags` 时，该数组 MUST 包含至多 5 个当前可见、文件有效的备选；备选 MUST 忽略 `intent` 匹配条件、保留显式 `emotion` 精确筛选和 `tags` 至少命中一个的条件，并按命中的请求 tag 数量降序、再按不透明 `sticker_id` 字典序稳定排序。其他无匹配情形 MUST 返回 `alternatives=[]`。每个备选 MUST 只包含 `sticker_id`、`emotion`、`tags` 和 `description`，不得包含路径、URL、hash、图片内容、统计或匹配解释。备选不是原查询的匹配结果；`sticker_send` MUST 不据此选择或发送贴纸，也不得更新使用统计。工具结果序列化 MUST 保留 `no_match` 的备选字段。

#### Scenario: 未连接 sender

- **WHEN** 过期 definition 或未连接 sender 调用 `sticker_send`
- **THEN** Tool SHALL fail closed 且不得创建旁路连接

#### Scenario: 严格发送无匹配时返回有限备选

- **WHEN** 查询模式的 `sticker_send` 没有足够匹配证据，且原查询同时包含 `intent` 与 `emotion` 或 `tags`
- **THEN** Tool SHALL 返回 `status=no_match` 和最多 5 个明确标为备选的当前可用条目
- **AND** SHALL 不发送消息、不更新使用统计，且不得声称备选满足原 intent
- **AND** 只有 Agent 显式选中某个 `sticker_id` 并再次调用工具时，才可进入精确发送路径

#### Scenario: 只有 intent 无匹配时不伪造相关备选

- **WHEN** 查询模式只提供 `intent` 且没有足够匹配证据
- **THEN** Tool SHALL 返回 `status=no_match` 和 `alternatives=[]`
- **AND** 插件 SHALL 不自动浏览或发送其他条目

#### Scenario: 发送 Action 结果不确定时插件不自动重试

- **WHEN** `sticker_send` 返回 `http_error`、`malformed` 或 `transport_unknown`
- **THEN** 插件 SHALL 返回对应固定分类，且本次调用不自动再次发送或改发另一张贴纸
- **AND** 工具定义和 bundled skill SHALL 仅说明通用接口和结果语义，不规定调用方的后续对话或搜索策略

### Requirement: `sticker_send` 只在贴纸库可用时暴露

插件 MUST 通过 manifest 的 `python_dependencies` 和项目运行时依赖声明提供 `Pillow>=12.3.0` 与
`jieba>=0.42.1`，且不得把 `jieba` 作为 optional extra 或按需导入。Agent 可见的 Tool definitions
MUST 只有在既有贴纸 store 中至少存在一个当前可见、具备有效 `sticker_files` 关联且 library 文件
可用的条目时，才包含 `sticker_send`。可用性探测 MUST 不得创建目录或数据库。
内部已登记但当前不可用的 ToolSpec 不得出现在 Agent 可调用列表中；过期 definition 触发 handler
时也 MUST fail closed。

#### Scenario: 贴纸库为空时隐藏工具

- **WHEN** 贴纸 store 缺失、为空，或没有当前可见且文件索引有效的条目
- **THEN** 系统 SHALL 不创建目录或数据库
- **AND** Agent 可见 Tool definitions SHALL 不包含 `sticker_send`
- **AND** 其他 Tool 与贴纸维护命令 SHALL 继续可用

#### Scenario: 贴纸库有可用条目

- **WHEN** 贴纸库存在至少一个可用条目
- **THEN** Agent 可见 Tool definitions SHALL 包含 `sticker_send`
- **AND** 工具 SHALL 使用同一 tokenizer 执行查询和元数据匹配

### Requirement: Agent 只能通过受限的 `sticker_send` Tool 请求发送

插件 MUST 注册一个名为 `sticker_send` 的异步 Agent Tool。Tool MUST 接受互斥的查询模式或 ID 模式。查询模式只接受 `intent`、`emotion`、`tags`，且至少一个条件有效；ID 模式只接受 `sticker_id`，该值 MUST 是长度 1 至 128 且只包含 ASCII 字母、数字、下划线或连字符的字符串，不做 trim 或大小写转换。空输入、显式 null、ID 与任何查询字段并存 MUST 返回 `invalid_input`。`emotion` 若提供 MUST 是 `joy|sadness|anger|surprise|fear|disgust|love|approval|confusion|neutral|mixed|unknown`
中的一个值；`intent` MUST 是不超过 64 个字符的非空短字符串；`tags` MUST 是包含 1 至 5 个非空
字符串的数组，每个 tag 归一化后不得超过 16 个字符，重复的归一化 tag MUST 返回 `invalid_input`。
Tool MUST 拒绝 `emoji_id`、`face_id`、`chat_id`、`session_id`、文件路径、远端媒体
URL 以及其他未声明字段，并在任何 Milky Action 或文件读取前返回 `invalid_input`。成功回执不得
返回 `sticker_id`；Agent 可以使用搜索结果中的 opaque ID，但该 ID 不代表目标授权。

#### Scenario: Agent 只提供一个查询参数

- **WHEN** Agent 只提供非空 `emotion`、非空 `intent` 或至少一个非空 `tags`
- **THEN** `sticker_send` SHALL 接受该调用并开始本地候选匹配
- **AND** SHALL 不要求 Agent 补充其他查询参数

#### Scenario: Agent 提供多个查询参数

- **WHEN** Agent 同时提供 `emotion`、`tags` 和 `intent` 中的两个或三个参数
- **THEN** 系统 SHALL 将每个已提供参数作为同一次匹配请求的约束
- **AND** SHALL 不把未提供的参数补成默认值

#### Scenario: ID 模式与查询模式互斥

- **WHEN** Agent 单独提供合法 sticker_id，或同时提供 ID 与任一查询字段
- **THEN** 单独 ID SHALL 进入精确发送；混合输入 SHALL 在读取库或联网前返回 invalid_input
- **AND** SHALL 不静默忽略任一字段

#### Scenario: Tool 参数包含目标或路径

- **WHEN** Tool 参数包含 `emoji_id`、`face_id`、`chat_id`、`session_id`、任意路径、URL 或未知字段
- **THEN** Tool SHALL 返回 `invalid_input`
- **AND** SHALL 不读取文件、不打开贴纸 store 且不调用 Milky

### Requirement: 发送目标必须来自可信的当前 Milky 会话上下文

Tool MUST 从 task-local session context 读取 `HERMES_SESSION_PLATFORM` 和
`HERMES_SESSION_CHAT_ID`。只有 `HERMES_SESSION_PLATFORM=milky` 且 chat key 为合法的
`dm:<十进制 QQ 号>` 或 `group:<十进制群号>` 时，Tool 才能继续发送。Tool MUST NOT 使用
`HERMES_SESSION_ID`、最近会话、home channel、默认频道或 Agent 参数推断目标。
缺少、冲突、非法或不支持的上下文 MUST 在网络访问前返回 `missing_session_context` 或
`unsupported`，不得建立旁路 client。

#### Scenario: 当前 Milky 私聊上下文可用

- **WHEN** task-local context 表示 `HERMES_SESSION_PLATFORM=milky` 且
  `HERMES_SESSION_CHAT_ID=dm:<合法 QQ 号>`
- **THEN** Tool SHALL 将贴纸发送到该私聊目标
- **AND** SHALL 不要求 Agent 传入 QQ 号

#### Scenario: 当前 Milky 群聊上下文可用

- **WHEN** task-local context 表示 `HERMES_SESSION_PLATFORM=milky` 且
  `HERMES_SESSION_CHAT_ID=group:<合法群号>`
- **THEN** Tool SHALL 将贴纸发送到该群聊目标
- **AND** SHALL 不把群聊目标改写为私聊或默认目标

#### Scenario: 上下文缺失或不是 Milky

- **WHEN** 当前 context 缺少平台、缺少 chat key、平台不是 `milky`、chat key 非法或表示 temp
  会话
- **THEN** Tool SHALL 在网络访问前返回固定的 `missing_session_context` 或 `unsupported`
- **AND** SHALL 不回退到任何其他目标

### Requirement: 候选匹配必须只使用当前生效元数据并以文本相关性为优先

查询发送模式下，系统 MUST 只从当前可见且当前文件索引有效的 `sticker_items` 中检索，并只读取当前生效的
`emotion`、`tags` 和 `description`。字段来源为 `manual` 或 `vision` MUST 不改变匹配权重。
提供 `emotion` 时，候选的当前 `emotion` MUST 严格相等；提供 `tags` 时，候选 MUST 至少
精确命中一个请求 tag，多个请求 tag 之间是 OR 关系；提供 `intent` 时，候选 MUST 至少命中
完整归一化 intent 短语或一个有效的本地规范化 token，不要求全部 token 命中。多个已提供参数
之间 MUST 取 AND。候选 MUST 按不产生数值分数的固定相关性层级比较：完整短语命中高于全部
token 命中，全部 token 命中高于部分 token 命中；同一层级内命中不同有效 token 或请求 tag
更多者优先。未提供 `emotion` 时，没有精确 tag、短语或 token 证据的候选 MUST 被排除并返回
`no_match`；仅提供 `emotion` 时，通过情绪硬筛选的候选可以直接进入轮换层，不得因没有文本
证据而返回 `no_match`。系统不得使用任意最低分数阈值。

#### Scenario: 人工修正字段不获得额外优先级

- **WHEN** 两张候选贴纸的当前 `emotion`、`tags` 和 `description` 匹配证据相同，但字段来源
  不同
- **THEN** 系统 SHALL 按相同的相关性规则处理两张贴纸
- **AND** SHALL 不因为 `*_source=manual` 增加或减少匹配优先级

#### Scenario: 明确情绪不匹配

- **WHEN** Agent 提供 `emotion=love`，而某候选当前 `emotion` 为 `joy`
- **THEN** 该候选 SHALL 在相关性排序前被排除
- **AND** SHALL 不因 tags 或 description 相似而发送该候选

#### Scenario: 只有低质量或无证据候选

- **WHEN** 贴纸库中只有候选，但候选不满足已提供的情绪、标签或意图词法条件
- **THEN** Tool SHALL 返回 `no_match`
- **AND** SHALL 不因为候选数量只有一张而降低匹配要求

#### Scenario: intent 只有部分 token 命中

- **WHEN** `intent` 经同一 tokenizer 分为多个有效 token，候选只命中其中一部分，且没有更高层级候选
- **THEN** 该候选 SHALL 保留在部分 token 命中层级中参与选择
- **AND** 系统 SHALL 不因不存在全部 token 命中而直接返回 `no_match`

#### Scenario: 唯一候选存在实际词法证据

- **WHEN** 只有一张候选通过已提供的 `emotion`/`tags` 硬筛选，且至少命中一个 intent 短语/token 或请求 tag
- **THEN** 系统 SHALL 选择该候选发送
- **AND** SHALL 不使用未定义的数值分数阈值拒绝该候选

### Requirement: 语义相关性必须优先于曝光轮换

查询发送模式下，系统 MUST 先按固定的无分数相关性层级确定最终候选池，再使用当前 chat key 的发送历史进行
多样性选择。只有最终层级和命中证据完全并列的候选才能进入轮换池。使用历史只能作为并列候选
之间的软偏好，MUST NOT 硬排除最近使用的贴纸，也 MUST NOT 让明显较差的候选超过明显更匹配
的候选。并列时，未使用或较久未使用者可以获得更高选择概率，同等使用历史下允许随机选择；
候选只有一张且满足最低证据时 SHALL 发送。

ID 模式 MUST 跳过匹配排序和轮换，近期使用不得阻止精确发送指定条目。

#### Scenario: 更匹配的贴纸最近刚发送

- **WHEN** 候选 A 的文本相关性明显高于候选 B，且 A 刚在当前会话中发送过
- **THEN** 系统 SHALL 仍优先选择 A
- **AND** SHALL 不因 A 最近发送而强制选择 B

#### Scenario: 多张候选相关性接近

- **WHEN** 多张候选都满足查询约束且相关性层级和命中证据完全相同
- **THEN** 系统 SHALL 在这些候选中进行随机或等价的软轮换
- **AND** 选择 SHALL 可以偏向当前会话较久未使用的候选，但不得把近期候选设为绝对不可选

#### Scenario: 唯一候选满足要求

- **WHEN** 只有一张候选满足最低匹配要求
- **THEN** 系统 SHALL 选择该候选发送
- **AND** SHALL 不因没有其他候选而返回 `no_match`

### Requirement: 发送只能使用已维护并校验通过的库文件

系统 MUST 通过选定条目的内部关联找到 `stickers/library/` 下的 content-addressed 文件，并在
发送前校验文件仍存在、路径仍位于受控 plugin-data 根目录、文件为允许的图片格式且实际
SHA-256 与 `sticker_items.file_sha256` 和 `sticker_files.sha256` 一致。Tool MUST NOT 接受
或读取任意 Agent 路径、URL 或未登记文件。校验失败 MUST 返回 `missing_file` 或
`storage_error`，且 MUST NOT 静默选择另一张贴纸继续发送。

#### Scenario: 库文件和 hash 校验通过

- **WHEN** 选定条目的 library 文件存在、路径受控且 hash 与索引一致
- **THEN** 系统 SHALL 生成一个 `image` segment，并将其 `sub_type` 设为 `sticker`
- **AND** SHALL 保留贴纸图片内容，不附加未请求的文本或第二张图片

#### Scenario: 选定文件缺失或 hash 不一致

- **WHEN** 选定贴纸的文件缺失、越界、格式无效或 hash 校验失败
- **THEN** Tool SHALL 返回 `missing_file` 或 `storage_error`
- **AND** SHALL 不调用发送 Action，也 SHALL 不改发排序中的下一张贴纸

### Requirement: 单次 Tool 调用只能产生一次明确的贴纸发送 Action

Tool MUST 根据 `dm:<id>` 或 `group:<id>` 分别调用既有的 `send_private_message` 或
`send_group_message`，消息 MUST 只包含一张已校验的 sticker image segment。一次 Tool 调用
在发送请求进入网络边界后 MUST NOT 自动重试、拆分、回退为文本或追加第二个发送 Action。
Tool 可以被 Agent 在不同调用中重复调用，不得设置 Agent turn 级调用次数上限。

#### Scenario: 私聊贴纸发送

- **WHEN** 当前目标是合法 `dm:<id>`，且选定文件已校验通过
- **THEN** 系统 SHALL 只调用一次 `send_private_message`
- **AND** 请求 SHALL 只包含一张 `sub_type=sticker` 的 image segment

#### Scenario: 群聊贴纸发送

- **WHEN** 当前目标是合法 `group:<id>`，且选定文件已校验通过
- **THEN** 系统 SHALL 只调用一次 `send_group_message`
- **AND** 请求 SHALL 使用当前群号，不得改投其他群或私聊

#### Scenario: Milky 结果未知

- **WHEN** 发送 Action 已进入网络边界但结果为超时、连接中断或 transport unknown
- **THEN** Tool SHALL 返回 `transport_unknown`
- **AND** SHALL 不自动重试或伪造 `sent`

### Requirement: 发送统计和会话历史必须与发送边界一致

当有效贴纸已完成本地校验并进入发送 Action 边界时，系统 MUST 对现有 `sticker_items` 的
`use_count` 和 `last_used_at` 执行一次原子更新，并记录当前 chat key 下的贴纸使用时间，供
后续近似候选软轮换使用。统计更新 MUST 不等待 Milky 成功响应；Milky 成功、失败或未知均不
回滚已经接受的统计。统计写入失败时 MUST 不重发已经接受的消息；同一次 Tool 调用 MUST
不得重复计数。不同 Tool 调用之间不受调用次数限制，并分别产生自己的统计记录。

#### Scenario: Action 成功、失败或未知均计数

- **WHEN** 贴纸发送 Action 已进入网络边界，并分别返回成功、协议拒绝、HTTP 错误或未知结果
- **THEN** 对应贴纸 SHALL 只增加一次使用统计
- **AND** 统计结果 SHALL 不被远端失败或未知结果回滚

#### Scenario: 统计 claim 写入失败

- **WHEN** 贴纸已完成本地校验，但发送前的统计 claim 无法持久化
- **THEN** 系统 SHALL 返回 `storage_error`
- **AND** SHALL 不调用 Milky，也 SHALL 不为了补写统计而发送或重发该贴纸

#### Scenario: Agent 连续显式调用

- **WHEN** Agent 在同一 turn 或不同 turn 中显式多次调用 `sticker_send`
- **THEN** 每次调用 SHALL 独立执行候选选择、一次发送和一次统计处理
- **AND** 系统 SHALL 不因 turn 边界拒绝后续显式调用

### Requirement: 工具结果和诊断必须使用固定安全分类

Tool 成功时 MUST 返回 `status=sent` 和 Milky 返回的 `message_id`，且不得返回内部
`sticker_id`；查询模式无候选时返回 `status=no_match`，ID 模式不存在或不可见时返回 `status=not_found`。该回执限制只适用于发送，搜索结果可以包含 opaque ID。缺少可信上下文、参数非法、文件缺失、存储
失败、Milky 协议拒绝、HTTP 错误、malformed 和 transport unknown MUST 使用固定机器可读
分类，不得把 HTTP 200、Action 调用完成或统计更新成功单独描述为用户已看到消息。日志和
异常 MUST 不包含 token、Authorization、完整参数、媒体 URL、本地路径、图片 bytes、完整远端
响应或自由文本正文。

#### Scenario: 成功结果

- **WHEN** Milky 返回可确认的成功消息序列
- **THEN** Tool SHALL 返回 `status=sent` 和 `message_id`
- **AND** SHALL 不返回内部 `sticker_id`
- **AND** SHALL 不把原始响应 body 写入日志

#### Scenario: 本地或远端失败

- **WHEN** 参数、上下文、匹配、文件、存储或 Milky Action 任一边界失败
- **THEN** Tool SHALL 返回对应固定分类
- **AND** SHALL 不泄露路径、URL、凭证、完整参数、图片内容或底层异常正文

### Requirement: 显式 ID 必须精确发送并重新校验

Agent 显式提供 sticker_id 时，工具 MUST 只查找该条目，不参与查询匹配或轮换。ID 不存在 MUST 返回 not_found，文件缺失 MUST 返回 missing_file，索引或元数据损坏 MUST 返回 storage_error，不得自动换图。发送前 MUST 重新执行既有文件完整性、当前会话、统计和单次 Action 校验；搜索候选不是发送成功或持续可用的承诺。

#### Scenario: 显式 ID 发送

- **WHEN** Agent 只提供合法 sticker_id 且对应条目通过当前校验
- **THEN** 工具 SHALL 只向可信当前会话发送该贴纸，并按既有边界更新一次统计
- **AND** 成功结果 SHALL 只返回 status=sent 和 message_id

#### Scenario: ID 失效或文件不可用

- **WHEN** ID 不存在、文件缺失或索引损坏
- **THEN** 工具 SHALL 返回对应固定分类，不调用发送 Action、不更新统计且不改发其他条目

### Requirement: 按 ID 发送必须精确解析并重新验证条目

ID 模式 MUST 使用既有持久化 opaque 条目 ID，保持编辑、重新分析和重启前后身份稳定，不把 ID 解释为路径、URL、候选序号或内容 hash。发送 MUST 重新读取当前可见条目并应用与查询发送相同的文件、大小、完整性及发送边界；不得因 ID 来自搜索而跳过检查，也不要求存在短期搜索缓存或最近一次搜索记录。

合法但不存在、已删除或当前不可见的 ID MUST 返回 not_found；可见条目已知文件缺失 MUST 返回 missing_file，文件索引损坏、完整性失败或存储访问失败 MUST 返回 storage_error。存储整体不可用沿用 unsupported。前述失败 MUST 不发送、不增加使用统计、不改发其他条目。搜索后、发送前删除或替换条目 SHALL 重新验证并安全失败，不使用过期搜索内容替代当前校验。通过校验进入发送边界后 SHALL 沿用现有 claim 统计和一次发送语义；远端失败或未知不回滚统计。

#### Scenario: 搜索后按 ID 发送

- **WHEN** Agent 使用搜索返回的有效 ID 显式发送，其他条目相关性更高或该条目刚使用过
- **THEN** 系统 SHALL 精确发送指定条目到当前可信会话，不重新匹配或轮换
- **AND** SHALL 只执行一次发送并按既有规则记录一次使用

#### Scenario: 搜索后条目删除

- **WHEN** ID 曾出现在搜索结果中但发送前条目已删除
- **THEN** 系统 SHALL 返回 not_found，不发送、不计数、不换图

#### Scenario: 搜索后文件失效

- **WHEN** 条目仍可见但文件缺失或完整性校验失败
- **THEN** 系统 SHALL 分别返回 missing_file 或 storage_error，不发送、不计数、不换图

#### Scenario: 不依赖搜索缓存

- **WHEN** 当前上下文已有有效工具返回 ID，且插件重启后该条目仍然可见可用
- **THEN** Agent SHALL 可直接按 ID 发送，不需要重新搜索

#### Scenario: ID 不能改变目标

- **WHEN** ID 有效但当前会话上下文缺失、非法或非 Milky
- **THEN** 系统 SHALL 在读取库及联网前返回既有上下文错误，不以 ID 推断或回退发送目标
