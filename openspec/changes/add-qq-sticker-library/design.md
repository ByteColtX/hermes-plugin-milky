## Context

参见 `proposal.md` 的动机。本 change 的起点不是空的 sticker library，而是已经交付的手动维护库：
固定的 `stickers/inbox/`、`stickers/library/`、`stickers/junk/`，独立 `stickers.db`，
`sticker_items`/`sticker_files`/`sticker_send_usage`，以及显式 `/milky sticker` 命令。
手动 `add` 的视觉结果使用固定的 emotion、中文 tags、短 description 和 `is_sticker` 契约；
`edit`、`reanalyze`、`del`、`cleanup`、`reindex` 已定义字段来源、文件归宿、索引和失败恢复边界。

当前发送服务以人工条目为基础，工具搜索/ID 发送另有正在实施的契约。现有发送统计在有效条目已
解析、文件已验证并发起发送调用后 claim 一次，远端成功、失败或未知均不回滚。当前手动命令的
handler 只得到 raw args，本插件不能据此证明命令一定来自某个 Milky chat 或 operator。

新能力要把“当前入站图片自动沉淀”接入同一持久化和出站边界，同时避免把旧手动数据强制迁移成
按会话数据、让自动任务扫描人工目录，或把未确认的来源/授权写成契约。

## Goals / Non-Goals

**Goals:**

- 在旧手动库之上增加自动收集、质量判定、自动条目作用域和 Agent 查询/纠错能力。
- 用增量 schema、兼容视图/仓储边界和引用保护保留旧手动条目、文件、ID、人工字段和统计。
- 让手动共享条目和自动会话条目可以共同参与当前会话的查询与发送，但彼此隔离分类、标签和使用历史。
- 让自动收集成为 pipeline 的 best-effort 旁路，不复制 Hermes 下载器、SSRF、媒体缓存、Agent queue 或 Will。
- 保持注册无副作用、命令短生命周期 store、断开时自动任务可取消，以及统一的安全错误和日志边界。

**Non-Goals:**

- 不把旧手动条目追溯迁移成按会话条目，不改变既有手动命令的目录、字段、ID 或授权声明。
- 不让自动收集读取或改写 `inbox/`、`junk/`，也不把普通消息图片隐式变成手动 `add` 命令。
- 不在本 change 中重新定义 `sticker_search`/`sticker_send` 的 intent、ID、排序或统计协议；这些接口沿用现有及 `add-sticker-search-and-id-send` 契约。
- 不提供 Agent 强制收藏、任意 scope/target、任意路径或 URL 导入，不改变 Hermes core。
- 不实现跨设备同步、embedding 相似搜索、按热度自动删除或要求可信 operator 身份的新配置。

## Decisions

### 1. 以手动库为兼容基座，不做破坏性表替换

`sticker_items` 继续代表已交付的手动可见条目，保留其 `sticker_id`、检测基线、当前生效字段、
字段级 source、时间戳和使用统计；`sticker_files` 继续代表 plugin-data 下受控的 content-addressed
物理文件索引，`sticker_send_usage` 继续保存现有按 chat 的发送历史。手动命令仍按归档的手动维护
规范工作，旧条目默认保持插件级共享可见性。

自动能力只增加内容资产元数据和自动作用域 entry 的增量记录。逻辑上分为：

```text
physical file/index
  sticker_files.sha256 == content_id

asset metadata
  content_id, quality_class, quality_score,
  classifier_version, created_at

automatic entry
  entry_id, content_id, scope_key, category, tags,
  source_chat_key, source_message_id, usage_count,
  last_used_at, created_at, updated_at

legacy manual entry
  sticker_items.sticker_id -> sticker_files.sha256
```

新记录只引用已经受控的物理内容，不复制人工条目为另一份自动条目。统一的 library repository
在查询时把“手动共享条目 + 当前 scope 的自动条目”组成可见集合；在维护、发送和清理时保留
旧 ID 的稳定性，并区分 manual entry 与 automatic entry 的删除权限。若实现采用显式 asset 表，
必须以旧 `sticker_files` 为物理索引的兼容来源，不能把旧库文件迁移到第二个未验证根目录。

选择增量层而不是直接把 `sticker_items` 改成 `(scope_key, content_id)` 唯一约束，是为了保留
当前手动命令、正在实施的搜索/ID 发送和已有外部 ID；直接重建旧表会改变共享库可见性、删除语义和
使用统计，也无法安全回滚。统一 repository 是新的内部抽象，但不对 Agent 暴露任意资源 URI。

### 2. 迁移先验证旧库，再提交新增结构

首次启用时先读取已知的手动 schema/version，确认旧表、技术索引和目录仍在 plugin-data 根内，再
以一个可回滚的增量迁移创建自动资产/entry 所需结构。已有手动行只建立必要的内容映射和质量状态
`unknown`，不重新调用视觉能力、不改变 `sticker_id`、人工字段或 `use_count`。

迁移不得扫描历史消息或人工 inbox，不得把库文件重新命名为新的路径，也不得把同一 hash 的手动行
复制为自动 entry。自动 collection 后续遇到已存在的手动 hash 时返回 `duplicate`，不覆盖手动元数据。
未知 schema、列不完整、事务失败或路径越界时停止迁移，保留原数据并返回 `unsupported` 或
`storage_error`。

自动 entry 的使用统计与旧 `sticker_send_usage` 分开持久化或通过兼容适配层映射；两者都必须在
有效条目已经进入发送调用后 claim 一次，不因远端结果未知而重发。手动和自动引用共同参与物理
文件清理判断，只有确认没有任何可见 entry 引用时才允许回收。

### 3. 旧手动共享可见性与新自动会话作用域并存

旧手动条目继续作为共享池。自动收集使用当前已确认的 session context：friend 为 `dm:<peer_id>`，
group 为 `group:<group_id>`；缺少、非法或 temp context 时不创建自动 entry。`global` 只在启动配置
明确启用时用于自动条目，不改变手动条目的历史可见性。

Agent Tool 不接受 `scope_key`、chat ID、路径或 target。搜索和 categories 只读当前手动共享条目
以及当前自动 scope 的条目；forget 只删除自动 entry。显式手动 `sticker del` 继续管理手动条目，
维护命令不因为缺少可信来源上下文而新增 operator 断言。

同一 content ID 可以由不同自动 scope 的 entry 引用同一个已验证文件；entry 的分类、标签、质量
展示和统计必须独立。共享物理内容不等于扩大可见范围，所有查询、发送和删除仍先按 entry 可见性
检查。

### 4. 手动命令与自动收集使用两条明确的输入路径

手动路径保持：

```text
/milky sticker <subcommand>
  -> 固定 raw-args 解析
  -> 固定 inbox/library/junk 边界
  -> 既有手动视觉元数据与原子维护
```

自动路径保持：

```text
message_receive
  -> canonical/dedup/admission/Gate/Will
  -> current top-level image materialization
  -> bounded internal staging
  -> deterministic gate + visual quality gate
  -> automatic scoped entry or safe defer
```

自动路径只接收当前消息已经由 Hermes helper materialize 的顶层图片，不重新下载、不扫描 inbox、
不把结果写进正文或 history，也不调用手动 command handler。手动命令中的人工投放图片不进入当前
消息自动 staging；两条路径可以共享格式校验、hash、原子写入和引用清理能力，但不共享隐式触发。

### 5. 手动视觉标注和自动质量分类保持兼容但不混用

手动 `add`/`reanalyze` 继续使用已交付的 metadata annotator 结果：合法 `is_sticker=true` 才能
从 inbox 进入 library，false 进入 junk，视觉失败留在 inbox；edit 的人工字段优先级和 clear
恢复视觉基线不变。

自动收集使用固定结构的质量分类，要求 sticker 类别、good 质量、可复用和低隐私风险，并拒绝截图、
新闻、聊天记录、文档、二维码、海报、普通照片和 unknown。自动分类结果只写入自动资产元数据和
自动 entry；不得把自由文本理由写入库、日志或手动 description，也不得用自动 reanalysis 覆盖
手动字段。人工 edit 后，后续自动重复图片仍返回 duplicate，不覆盖 `manual` 字段。

硬门禁、单图大小、总 staging、TTL、并发和取消均在视觉调用前执行。视觉能力不可用、超时或
malformed 时删除 staging，返回 `defer`/`classifier_unavailable`，继续普通 handoff。

### 6. 工具只消费统一可见集合，不重新发明发送协议

`sticker_categories` 是无参数、只读的受限聚合工具；`sticker_search` 和 `sticker_send` 直接沿用
现有及 `add-sticker-search-and-id-send` 的 `intent`/`emotion`/`tags`、`limit`、opaque ID、
当前目标和互斥查询/ID 语义。本 change 不加入 `category/keyword/index`，也不让 Tool 传任意 scope。

`sticker_forget` 只接受当前搜索结果中可见的自动 entry ID；手动共享条目仍通过显式维护命令删除。
所有 Tool 在读取文件或网络 Action 前校验字段、当前 session 和可见性。发送复用现有 sender、一次
读取、大小限制和单次 Action 边界；选定条目并发起发送调用后 claim 一次，拒绝、未知和统计失败
均不得触发第二次发送。

### 7. 文件和数据库提交采用“引用优先”的可恢复顺序

自动收集的顺序为：校验受信任 staging -> 流式计算 content ID -> 查找手动/自动引用 -> 复用或
原子写入受控 library 文件 -> 提交 asset metadata 和自动 entry -> 清理 staging。数据库提交失败
时保留完整但暂时孤立的文件，交给受控 cleanup；不先删除可能已被引用的文件。

手动 add 的 true/false 文件归宿、edit/reanalyze、del、cleanup 和 reindex 继续遵守已有规范。
cleanup/reindex 处理物理文件时必须同时检查 `sticker_items` 和自动 entries；缺失引用保留 metadata
并返回 `missing_file`，未知文件返回固定诊断，不猜测创建新可见 entry。dry-run 不写数据库、不移动
或删除文件，也不改变统计。

### 8. 生命周期和跨 change 合并顺序

贴纸 store 按手动命令或 Tool 调用短生命周期打开；自动分类任务加入插件拥有的任务集合。注册阶段
只登记 command、ToolSpec、配置和生命周期绑定，不创建数据库、目录、SSE、Milky client、视觉调用
或常驻扫描器。断开、卸载和 reload 时先取消并等待自动任务，再清理 staging 和关闭本次拥有的资源；
已提交数据保留。

与 `add-sticker-search-and-id-send` 合并时，library 只扩展其候选可见性和 ID 解析来源，不覆盖
查询/ID 参数、排序、not_found、发送回执或既有 claim 语义。与 relationship system 合并时，
保持独立表、repository、observer 和 cleanup 任务；pipeline 先完成既有 admission/Gate/Will，再
分别挂载自动 sticker observer 与关系 observer，任一旁路失败都不能改变 Hermes handoff。

## Risks / Trade-offs

- **[旧手动表和新作用域模型并存增加查询复杂度]** → 保留一个统一的可见性/引用 repository，旧
  `sticker_id` 不变；用手动库回归和跨 scope fixture 验证查询、发送、删除和 cleanup 的 union 语义。
- **[自动图片可能带来隐私或误收风险]** → 默认 chat scope、显式 global、固定拒绝类别、unknown
  fail-closed、无 Agent 强制收藏和 `sticker_forget` 只删自动条目。
- **[文件与数据库不是同一原子事务]** → 先提交可验证文件再提交引用，失败时保留 orphan，cleanup
  只回收确认无引用的文件。
- **[自动任务影响资源和关闭顺序]** → staging TTL/大小/总量/并发上限，任务纳入生命周期集合，
  handoff 不等待视觉完成，断开时取消并等待。
- **[搜索/发送 change 与 library 同时修改工具注册]** → 以搜索/ID change 的契约为依赖边界，
  合并回归验证 ToolSpec 只注册一次、参数不冲突、旧人工库调用保持兼容。
- **[手动命令没有可信 operator 上下文]** → 保持已有“不声明来源授权”的契约，不新增伪安全配置；
  未来如需 operator-only 行为另起 change。

## Migration Plan

1. 先在 fake store 中验证现有手动 schema、目录、条目、ID、字段来源、统计和使用历史的只读识别；
   不启用自动收集也不创建新文件。
2. 以可回滚事务增加自动 asset/entry 结构和兼容查询边界；旧手动记录只建立内容映射，不重命名、
   不重分析、不改变共享可见性。未知 schema 或迁移失败保持旧库不变。
3. 先上线只读 categories/search 的统一可见性、质量 fixture、dry-run 诊断和 cleanup/reindex
   引用保护，再启用当前图片自动收集、forget 和自动条目发送；视觉不可用时保留查询/发送已有条目。
4. 在 fake Hermes/Milky 中验证手动 add/edit/reanalyze/del、自动收集、作用域隔离、共享文件、
   发送 claim、任务取消和 ordinary handoff；真实 Hermes/Milky 视觉与发送边界没有证据时保持
   `unsupported`/`blocked`，不得把 fake 结果写成实机成功。
5. 回滚时关闭自动 collection 和新 Tool 能力，保留 `stickers.db`、旧目录、手动条目和自动文件；
   不执行自动删除。兼容版本继续读取旧手动表，升级版本通过 schema version/reindex 恢复自动结构。

## Open Questions

无。手动兼容层、自动条目作用域、物理文件共享、工具依赖、统计时机和授权边界已在 proposal 与
specs 中固定；实现阶段只需选择不改变这些外部行为的本地 repository 和迁移实现。
