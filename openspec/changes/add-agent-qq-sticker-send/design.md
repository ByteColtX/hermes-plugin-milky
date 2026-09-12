## Context

`add-manual-qq-sticker-maintenance` 已交付独立的 `stickers.db`、`sticker_items`、
`sticker_files` 和 content-addressed library。条目保存检测基线、当前生效的 `emotion`、`tags`、
`description`、字段来源以及全局 `use_count`/`last_used_at`；维护命令不改变使用统计。现有
`outbound/tools.py` 注册固定的 Milky Action Tool，`outbound/sender.py` 已能把受控 native image
转换为 Milky image segment，并按 `dm:<id>`/`group:<id>` 路由消息。

本 change 增加一个独立语义 Tool `sticker_send`，不是新的 Milky operationId，也不是任意
Action catalog。它需要把 Agent 查询、当前 task-local session context、贴纸库检索和既有出站
边界连接起来，但不能复制 Hermes 的 session 队列、媒体下载/SSRF 边界或普通消息流程。

## Goals / Non-Goals

**Goals:**

- 为 Agent 提供不接受目标和贴纸 ID 入参的单一贴纸发送入口；成功回执只返回发送状态和远端消息 ID，不暴露内部贴纸 ID。
- 以当前生效元数据为唯一匹配输入，让文本相关性优先于曝光轮换。
- 在相关性接近时使用当前 chat 的历史进行软轮换，同时允许最近使用的贴纸在它明显更匹配时再次发送。
- 复用现有严格的 Milky 目标路由、image materialization、Action 错误分类和日志脱敏边界。
- 使全局发送统计和当前 chat 选择历史在一次发送边界上原子记录，并能在重载后继续使用。

**Non-Goals:**

- 不提供 `sticker_search`，不把候选列表、匹配解释或搜索结果单独暴露给 Agent。
- 不接受 Agent 指定 `sticker_id`、`chat_id`、`session_id`、文件路径、URL 或任意图片。
- 不进行图像相似度、视觉模型、远程 embedding、远程搜索或入站图片自动入库。
- 不改变 `/milky sticker` 维护命令、普通消息、Gate、Will、wait buffer、reply cost 或 Hermes core。
- 不限制 Agent 在 turn 内或跨 turn 的显式 `sticker_send` 调用次数；只限制每次调用最多一个有副作用的 Milky 消息 Action。

## Decisions

### 1. Tool 注册和可信目标

在现有 `outbound/tools.py` 的显式注册入口增加独立 `sticker_send` ToolSpec 和 handler。它不
绑定一个 Milky operationId，而是调用插件自己的贴纸发送 service；注册调用只登记 schema、
handler 和可用性检查，不创建或打开贴纸 store、不读取 library、不建立网络连接。`jieba` 由
`plugin.yaml` 的 `python_dependencies` 和项目运行时依赖声明提供，按普通模块在插件导入时加载，
不使用按需导入或可选依赖缺失分支。

Hermes 构建 Agent 可见 Tool definitions 时通过该 ToolSpec 的 `check_fn` 执行只读可用性探测：

- 先确认既有 store 中至少有一个当前可见、关联有效 `sticker_files` 且 library 文件可用的条目；
  store 缺失、为空或没有可用条目时直接返回不可用，不创建目录或数据库。
- `jieba` 是正常插件运行时依赖，模块加载失败属于宿主依赖配置错误，不在 Tool discovery 中按需
  导入、隐藏或转化为 `unsupported`。
- 条目可用时把 `sticker_send` 放入 Agent 可见 definitions。内部可以保留 ToolSpec 登记，但不可用
  时不得出现在 Agent 可调用列表中；handler 对过期 definition 仍需 fail closed。

该探测只在 Tool discovery 的可用性检查边界执行，不在插件 import、`register()`、connect、SSE
或普通 Agent 输出阶段打开 store。维护命令新增第一个可用条目后，下一次 definitions discovery
即可重新暴露工具；删除最后一个可用条目或使 library 索引失效后，下一次探测隐藏工具。

handler 调用 `gateway.session_context.get_session_env()` 读取：

- `HERMES_SESSION_PLATFORM`，必须为 `milky`；
- `HERMES_SESSION_CHAT_ID`，必须由现有 chat-key 校验接受为 `dm:<id>` 或 `group:<id>`。

不读取 `HERMES_SESSION_ID` 作为目标，不读取 home channel，不接受 Tool 参数中的目标。这样
Agent 不能把贴纸发到另一个会话，也不会因当前 context 缺失而误投默认频道。Tool handler 只在
有活动且生命周期绑定的 Milky sender 时继续。

### 2. 查询规范化和相关性排序

查询和库字段使用同一个本地 `jieba` tokenizer。`jieba` 不是 Python 内置库，也不是 Hermes
core 依赖；它通过插件 manifest 的 `python_dependencies` 和项目运行时依赖声明提供，使用
`jieba>=0.42.1`，不设置上限，也不做按需加载，并在 Python 3.13 环境验证导入和分词结果。选择 `jieba` 是因为它适合当前小规模中文 metadata、
无需模型服务且部署边界简单；不引入需要额外模型资源或远程服务的分词方案。归一化只做 Unicode NFKC、大小写折叠、
空白/标点边界处理和分词，不调用模型或远程服务。`intent` 的 Tool 文档约束为简短意图短语，
不把 Agent 长篇正文当作查询。

候选处理分三层：

1. **硬筛选**：`emotion`（若提供）要求当前值严格相等；`tags`（若提供）至少有一个请求 tag
   与当前 tag 规范化后精确相等，多个请求 tag 是 OR 关系；多个已提供字段之间仍取 AND。`intent`
   不要求所有分词都命中，只参与后续词法证据分层。候选读取前确认 `sticker_files` 有效索引和
   `sticker_items` 的可见关联。
2. **无分数的相关性分层**：对通过硬筛选的候选，使用同一 `jieba` tokenizer 处理 intent、
   当前 tags 和 description，并按以下顺序比较：完整归一化 intent 短语命中；全部有效 intent
   token 命中；部分有效 intent token 命中。处于同一层时，命中不同有效 token 更多者优先；
   tags-only 请求则按命中的请求 tag 数量比较。这里不计算 BM25 或其他总分，也不设置“60 分”
   一类的最低数值阈值。`emotion` 不参与排序，只作为硬筛选。
3. **最低证据**：没有提供 emotion 时，至少需要一个精确 tag 命中或一个 intent 短语/token
   命中；intent 和 tags 都没有任何证据时返回 `no_match`。只有 emotion 的调用在严格 emotion
   筛选后把所有候选视为同一相关性层，交给曝光选择。唯一候选只要满足这些硬筛选和最低证据就发送。

该分层规则不把内部比较结果暴露给 Agent，也不把分层或命中数量写入数据库。选择规则的关键
不变量是：明显更多词法证据的候选不能被使用历史压过；曝光逻辑只作用于最终比较结果完全并列
的候选。

### 3. 相关性优先、近似候选软轮换

分层比较结束后，只将最终比较结果完全并列的候选放入轮换池，不使用动态分数或相对 margin。
明显缺少词法证据的候选不会因为 `use_count` 较低而入池。

轮换池内使用当前 `chat_key` 的最近使用时间作为软偏好：未使用或较久未使用者优先，但最近使用
者仍有非零机会；同等使用历史下随机选择。测试只依赖以下可观察不变量：池外较差候选不可被选，
池内候选不会被硬 cooldown 排除，同等条件下选择可产生不同贴纸。候选只有一张且满足最低证据
时直接选择，不因数量少而放宽匹配要求。

现有全局 `sticker_items.use_count`/`last_used_at` 保留为统计和诊断字段，不作为跨会话的主选择
顺序。新增受控的 per-chat 使用表（例如 `sticker_send_usage`）保存 `(chat_key, sticker_id)`
的最近使用时间和次数；只存安全 chat key、匿名 sticker ID 和时间/计数，不保存正文、查询或
消息内容。这样不同群/好友的曝光不会互相污染，同时维护命令仍不改变发送统计。

### 4. Store 迁移、选择 claim 和统计边界

贴纸数据库从当前 schema version 通过一次受限迁移增加 per-chat 使用记录表和必要索引。未知
schema 继续返回 `unsupported`，不得静默创建空库或覆盖旧文件。发送 service 每次操作短时
打开自己的 store；检索可以在只读连接上完成，选择后使用短事务 `BEGIN IMMEDIATE` 重新确认
条目/file index，写入全局统计和 per-chat 最近使用时间后提交，再进入 Milky Action。数据库
事务不跨网络等待。

如果统计 claim 失败，Tool 在 Action 前返回 `storage_error` 且不调用 Milky；如果 claim 已提交而后续 Milky
返回失败或未知，统计不回滚，且 Tool 不重发。这样一次 Tool 调用最多一次计数和一次消息
Action；并发调用的统计更新由 SQLite 原子事务保护，曝光轮换仍是软公平，不宣称严格的全局
随机无重复保证。

### 5. 受控文件校验和专用发送路径

选定条目通过数据库关联解析到 library 的 content-addressed 文件。为避免 Agent 路径穿透和
文件在 hash 校验后被替换，sticker 发送路径把受控路径 containment、常规文件/格式/大小、
流式 SHA-256 校验和 base64 materialization 组合在同一个受控读取边界；不把任意用户路径交给
通用附件入口。实现应复用现有 materialization 的限制和错误分类，但不绕过 hash 校验。

专用 sender 路径构造一张 `image_segment(uri, sub_type="sticker")`；`sub_type` 字段必须存在且
严格等于 `"sticker"`，不得省略，也不得使用 `"normal"`。不附加 caption，不经过普通文本拆分、
forward、文本 fallback 或独立文件上传。按已校验 `dm:`/`group:` 目标调用现有
`send_private_message`/`send_group_message` 一次，并将 Milky 的确认 message sequence 映射为
Tool 的 `message_id`。Action 进入网络边界前完成所有本地校验；结果未知时保留
`transport_unknown`，不重试。

### 6. 生命周期、错误和日志边界

Tool 注册、插件导入、connect、SSE 和普通 Agent 输出不打开贴纸 store、不扫描 library、不
创建检索后台任务。Tool handler 在调用范围内短生命周期打开/关闭 store；disconnect/reload
不删除已提交条目、library 文件或 usage 记录。

Tool 只返回固定机器可读分类：`sent`、`no_match`、`invalid_input`、
`missing_session_context`、`unsupported`、`missing_file`、`storage_error`、`rejected`、
`http_error`、`malformed` 和 `transport_unknown`。日志只记录 Tool 名称、固定分类、已知状态码、
耗时和必要的低敏关联 ID，不记录查询正文、路径、URL、图片 bytes、完整响应、token 或异常正文。

## Risks / Trade-offs

- **[中文分词边界影响召回]** 同一表达可能被 tokenizer 分成不同 token。→ 使用统一 tokenizer、
  current tag 作为受控字段、固定 fixture 覆盖短意图和 tags；不在 v1 自制二字 n-gram 或隐式
  同义词扩展。
- **[词法分层无法理解同义表达]** 词面不同但含义相近的请求可能 `no_match` 或证据层较低。→ v1
  保持本地、确定性和可审计；后续若需要同义语义另立 change，不在发送路径调用模型。
- **[部分命中可能扩大召回]** 只有部分 intent token 命中时可能选到泛化贴纸。→ 只有至少一个
  有效 token/短语命中才进入候选；完整短语、全 token 和部分 token 使用固定层级，且曝光只在
  最终比较完全并列时生效；用合成 fixture 覆盖唯一候选、部分命中和零命中。
- **[per-chat 使用记录增长]** 群和好友数量乘以贴纸数量会增加 SQLite 行数。→ 只保存每个
  `(chat_key, sticker_id)` 的最新计数和时间，建立索引并在 cleanup/受控维护路径中提供过期记录
  清理策略；不保存消息正文。
- **[本地文件与数据库不是单一事务]** 文件在校验或发送前可能被外部修改。→ 发送边界内重新
  校验并 materialize；校验失败不发送、不换图；library 仍由现有 reindex/cleanup 修复。
- **[并发 Tool 调用造成软公平偏差]** 多个调用可能在短时间内竞争同一候选。→ 用 SQLite
  短事务保护统计 claim，不承诺严格 reservation；每次调用最多一次 Action，未知结果不重试。
- **[Hermes task-local context 缺失或非 Milky]** Tool 无法安全确定目标。→ fail closed，返回
  `missing_session_context`/`unsupported`，不读取 `HERMES_SESSION_ID` 或任何默认目标。

## Migration Plan

1. 在实现前声明中文 tokenizer 运行时依赖并补充数据库 schema migration；旧版没有发送 Tool 时继续
   正常执行既有维护命令。
2. 发布后，只有明确注册且 context 合法的 `sticker_send` 调用会读取既有 library；不会自动
   扫描 inbox、导入新图片或发送历史条目。
3. 第一次发送时创建或迁移 per-chat usage 表；已有 `use_count`/`last_used_at` 保持原值，旧条目
   不需要重新视觉分析或重新生成 sticker ID。
4. 回滚时保留 `stickers.db`、library 和 usage 表；旧版本可以继续维护已知表，但不应删除未知
   usage 表或误把发送 Tool 标记为成功。重新启用新版本后继续使用已提交统计。

## Open Questions

无。Tool 参数、目标来源、当前字段、相关性优先、近似候选软轮换、文件/hash 失败、发送次数、
统计边界和排除 `sticker_search` 已在 proposal/spec/design 中固定；实现阶段只需用合成 fixture
验证分层匹配、部分命中和并列轮换，不改变外部行为。
