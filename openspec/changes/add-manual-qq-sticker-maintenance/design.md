## Context

当前插件的根入口在注册阶段登记 `/milky` 命令，入站 pipeline 在 canonical、dedup、Gate 之后把纯文本斜杠命令分流到 Hermes command event；命令不进入 Will、wait buffer、资源补全或普通 Agent turn。命令 service 目前只处理无参数 `/milky`，adapter connect 时绑定同一个 Milky client，disconnect 时解除绑定。

Hermes core 已提供 `plugin_data_dir("hermes-plugin-milky")` 和 `plugin_db("hermes-plugin-milky", filename=...)`。core 的 gateway 命令执行期间还绑定 task-local 的平台、chat 和 user identity，并提供 `vision_analyze_tool` 辅助视觉调用。新 change 只使用这些已确认边界，不修改 Hermes core，不把贴纸维护改造成 Agent Tool、后台视觉任务、入站媒体缓存或 Agent 队列。

## Goals / Non-Goals

**Goals:**

- 为 `/milky sticker` 提供固定、可审计、可重复执行的人工维护命令。
- 让操作者把图片放入固定持久目录后，以确定性的格式、大小、可读性和内容 hash 规则入库。
- 在确定性筛选和去重之后，用 Hermes core 的辅助视觉能力批量生成一个固定枚举的单选主情绪、2–5 个中文情绪/场景标签和 20 字以内的内容描述；视觉字段的具体内容只作为元数据建议，不决定图片是否入库，但视觉调用成功且结果结构合法是本次新条目可见的前置条件。
- 提供操作者对已入库视觉元数据的显式修正能力，修正不改变图片 bytes、content hash 或 sticker ID。
- 让文件写入和元数据提交可恢复，重复导入不产生重复条目，删除和清理只回收数据库确认无引用的库文件。
- 使用 Hermes core 的插件持久化接口；授权来源边界暂不由本 change 提供，所有维护失败都与普通 Hermes 消息流程隔离。

**Non-Goals:**

- 不从普通消息、入站图片、reply、forward、wait buffer 或 Agent 输出自动收集图片。
- 不在普通消息或连接初始化中调用视觉模型；视觉调用只由到达插件 command handler 的显式 `sticker add` 或 `add --dry-run` 参数驱动，且不能替代人工投放审核或根据语义结果阻止图片入库。视觉调用失败时本次不入库，候选继续留在 inbox 等待下次命令。本 change 不承诺 handler 调用一定来自 Milky friend/group，也不承诺宿主超时后 core 内部任务一定已回收。
- 不提供 Agent 收藏/删除 Tool、跨 chat 作用域、远程 URL 导入、任意路径导入、图片发送或相似度搜索。
- 不把 inbox 原文件移动、覆盖或删除作为导入成功的隐含副作用。

## Decisions

### 1. 固定目录和两层持久化对象

使用以下目录约定：

```text
<hermes plugin-data>/hermes-plugin-milky/
├── stickers/
│   ├── inbox/                 # 操作者投放的原文件，只读扫描
│   └── library/               # 插件生成的 content-addressed 文件
└── stickers.db                # 贴纸元数据和索引
```

实际路径由 Hermes `plugin_data_dir()` 决定，设计文档不硬编码 Hermes home。库文件名只由 SHA-256 派生，例如按 digest 前缀分片后保存完整 digest 和规范化扩展名；不使用原始文件名、命令参数或远端 URL 作为库路径。数据库使用两类记录：`sticker_entries` 保存可见贴纸，至少包含随机不透明 `sticker_id`、唯一 `content_hash`、`created_at`、视觉基线字段 `vision_emotion`/`vision_tags`/`vision_description`、当前生效字段 `emotion`/`tags`/`description`，以及字段级 `emotion_source`/`tags_source`/`description_source`；`sticker_files` 保存由库目录重建的技术索引，至少包含唯一 `content_hash`、唯一 `library_relpath`、MIME、字节数和 `verified_at`。`sticker_entries.content_hash` 的唯一约束保证同一 bytes 最多对应一个可见 `sticker_id`；本 change 不建立多个可见条目共享同一库文件的关系。

视觉基线在首次成功 add 时写入，当前生效字段初始复制基线，三个字段来源均为 `vision`。`edit` 只更新指定字段的当前生效值和对应字段来源；清除人工覆盖时从对应视觉基线恢复，并将该字段来源改回 `vision`。列表中的行级 `source` 不单独持久化，而是派生为“任一字段来源为 `manual` 则为 `manual`，否则为 `vision`”；同时返回 `field_sources` 让维护者知道具体哪些字段被人工改过。Agent 只使用当前生效字段，不需要理解视觉基线和来源字段。

选择独立 `stickers.db` 而不是 Hermes session DB、JSON 或全局 state：SQLite 事务能把条目可见性和去重约束放在同一持久边界；独立文件避免污染 session schema；content-addressed 文件避免复制同一 bytes。JSON 和单独状态对象无法可靠处理重复命令、删除引用和重载恢复。

### 2. 每次命令短生命周期打开 store

根 `register(ctx)` 只注册 command handler、静态配置和必要的生命周期绑定，不调用 `plugin_data_dir()`，不打开数据库，不扫描文件。有效的贴纸子命令到达后才创建目录并打开数据库；一次命令结束在 `finally` 中提交或回滚并关闭连接。

这样可以同时满足懒加载、插件重载和多 adapter 场景：不会留下持有旧 profile 路径的长期连接，也不需要未经 core 确认的 `on_unload` API。插件创建的视觉调用在当前显式命令的 task group 内最多并发 10 个，不主动创建脱离 handler 的持久化后台队列；core 对已发出调用的超时和回收语义不由本 change 承诺。数据库写入使用短临界区和单条事务；视觉等待期间不持有数据库事务，提交前重新检查 content hash 和唯一约束。事件流、普通消息和 Milky client 不会把视觉结果交给主 Agent turn。

### 3. add 采用“先校验去重、再视觉打标、再原子文件、后元数据可见”的顺序

`add` 只接受固定 inbox 的 regular file，并通过 `lstat`/root containment 检查拒绝符号链接和越界路径。每个候选文件以流式方式读取，限制在 `10 MiB` 内，检查非空、图片 magic/header、结构完整性和 PNG/JPEG/GIF/WebP 格式；不以扩展名单独信任类型。读取过程中计算 SHA-256，避免重复读取同一输入。

同一批次内和库中已经存在的 content hash 先去重，duplicate 不调用视觉模型。按照稳定扫描顺序，剩余唯一候选最多取前 50 张进入当前命令的视觉队列；第 51 张及以后不调用视觉并报告 `batch_deferred`，继续留在 inbox。队列由最多 10 个并发 worker 调用 Hermes core 的 `vision_analyze_tool`，传入 inbox 内受控本地路径和固定 JSON 输出提示词；一个调用完成并释放槽位后，立即补入下一候选。正常完成时命令等待本批次候选进入成功提交、重复、固定失败或 `batch_deferred` 状态；每个成功候选独立提交，不要求整批事务。宿主超时或取消时，插件只保证已完成提交的条目保持可见、未提交候选留在 inbox；core 是否能回收已发出的底层调用不由本 change 承诺。每次视觉调用返回后，维护 service SHALL 先按 core 的外层 JSON envelope 解析，再读取其中的 `analysis` 字符串；只有外层 `success=true` 且内层 `analysis` 解析为单个对象后，才进入字段 schema 校验。要求内层对象严格包含一个固定枚举的 `emotion`、有界 `tags` 数组和短 `description`；这些字段是贴纸元数据建议，不是人工筛选裁决。

`--dry-run` 执行同样的确定性校验、去重和最多 10 个并发的视觉分析，但插件不写入库文件、数据库或待确认状态，并返回每个候选的主情绪、中文检索标签和 20 字以内描述摘要，供操作者确认标签质量后再执行正式 `add`。正式 `add` 会重新扫描并重新分析候选，以避免使用过期的预览结果；core 视觉 helper 的临时处理仍由 Hermes core 自己管理。视觉 provider 不可用、超时、返回错误或结构无法解析时，本次不创建库文件或可见条目，候选继续留在 inbox，并在下一次 `add` 中按 hash 增量重试。正式 add 中每个成功候选独立完成原子文件和元数据提交，不等待其他候选。情绪、标签和描述只作为已接收条目的元数据，不改变文件 bytes 或 sticker ID 的去重语义。

对通过确定性文件校验、尚未重复且视觉分析成功的新内容，先写入同一 library 文件系统下的随机临时文件，完成写入和必要的 flush 后使用原子 replace；随后在同一数据库事务中写入 `sticker_files` 技术记录和 `sticker_entries` 可见记录，并将视觉基线、生效字段和字段来源一起写入。视觉分析失败时不得复制到 library，也不得创建可见 entry；inbox 永远作为下一次命令的重试输入。数据库事务失败时保留的库文件只能成为 cleanup/reindex 可识别的 orphan，不得成为可见 entry；临时文件使用受控前缀，cleanup 可以安全删除。

### 4. edit 使用字段级部分更新和人工覆盖重置

`/milky sticker edit <sticker_id>` 使用显式 option 语法：

```text
/milky sticker edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<emotion|tags|description>[,<field>...]]
```

每个 option 都是单个 `--name=value` raw-args token，option 最多出现一次；`--description=<text>` 的值不跨空白 token，命令不依赖 shell quoting；未出现的字段保持不变；至少要有一个 set 或 clear option；同一字段同时 set 和 clear、未知字段、空值、非法枚举、重复标签、标签不在 2–5 个范围内或描述超过 20 个字符时，整条命令返回 `invalid_input` 且不写入任何字段。`--clear` 清除的是人工覆盖：系统从相应 `vision_*` 基线恢复当前值，并把对应字段来源恢复为 `vision`，不写入空标签或空情绪。所有字段校验通过后，在一个数据库事务中更新当前生效值和字段级来源；图片文件、hash、技术索引和 `sticker_id` 不变。

行级 `source` 只作为列表输出的派生摘要，字段级 `*_source` 才是持久化事实。视觉成功入库时三项字段来源都是 `vision`；人工设置某字段后只将该字段标记为 `manual`；清除该字段覆盖后恢复为 `vision`。重复 `add` 按 content hash 返回 `duplicate`，不得重新视觉分析或覆盖已有基线及人工字段。

### 5. 视觉辅助使用 core 的独立分析路径，不进入主 Agent 上下文

维护 service 使用 Hermes core 暴露的 `vision_analyze_tool(image_url, user_prompt, model=None, ...)` 辅助接口，而不是调用 `PluginContext.dispatch_tool("vision_analyze", ...)`。后者可能根据主模型能力选择 native vision 并返回 `_multimodal` tool-result envelope，目标是让主 Agent 在下一轮看图，不适合这里要求的结构化文本判定；直接使用辅助函数则只消费分析结果，不创建 Agent tool call、tool message、transcript 或 handoff。

`vision_analyze_tool` 的返回值是 JSON 编码的外层 envelope，而不是贴纸元数据对象。维护 service 必须按以下顺序处理：

```text
tool result string
  -> 解析外层 JSON 对象
  -> 要求 success == true
  -> 读取 analysis 字符串
  -> 若存在 scale_note，只去除与该字段精确匹配的 core 前缀
  -> 将剩余 analysis 严格解析为单个 JSON 对象
  -> 校验 emotion/tags/description
```

成功 envelope 的 `analysis` 可能带有缩放或裁剪提示前缀，并可能同时有 `scale_note` 字段；不得用任意方括号正则吞掉模型正文，只能去除已确认的 core 前缀。`success=false`、存在 `error`、缺少或为空的 `analysis`、外层 JSON 非对象、内层 JSON 非对象或任何解析/字段校验失败，均归类为 `visual_unavailable`，不得入库。模型只负责返回内层 JSON；提示词中的“只返回一个 JSON 对象”不等于 `vision_analyze_tool` 的最终返回只有这一层。

core 可能在空结果、图片大小或传输错误时自行重试、缩放后重试或切换 fallback provider。维护 service 将 core 返回的最终 envelope 视为本次调用结果，不在同一次命令中重复调用 `vision_analyze_tool`；失败候选留在 inbox，下一次显式 `add` 再重试，避免重试次数叠加。

视觉调用必须使用以下固定 prompt；插件仍需对模型输出执行独立 schema 校验，不能因为 prompt 已限定格式就跳过 envelope、JSON 或字段校验：

```text
You are a sticker metadata annotator.

Analyze the input sticker/meme image and extract metadata that best captures its expressive content.

Return only one valid JSON object. Do not output Markdown, explanations, comments, or any additional content.

Field requirements:

- `emotion`: Select exactly one primary emotion:  
  `joy`, `sadness`, `anger`, `surprise`, `fear`, `disgust`, `love`, `approval`, `confusion`, `neutral`, `mixed`, `unknown`
  - Select the most prominent and clearly expressed emotion in the image.
  - If multiple emotions are equally prominent, select `mixed`.
  - If the emotion cannot be determined reliably, select `unknown`.
- `tags`: Return 2–5 unique Chinese emotion/context tags.
  - Tags should directly describe the emotion, reaction, action, or typical conversational context expressed by the image.
  - Prefer short, natural words or phrases commonly used in chat.
  - Examples: 安慰、阴阳怪气、无语、得意、卖萌、自信、哭泣、嘲讽、难绷、嫌弃、攻击、吐槽、疑惑...
  - Do not add information that cannot be confirmed from the image.
- `description`: Return a brief description in no more than 20 Chinese characters.
  - Summarize the main subject and what the image is expressing.
  - If the image contains text, summarize its meaning rather than copying long text verbatim.

Output format:
{
"emotion": "joy",
"tags": ["开心", "鼓励", "摸头"],
"description": "猫咪举爪安慰对方"
}
```

内层 JSON 超出边界、夹带自由格式正文或不是对象，或外层 envelope 解析失败，都视为本次视觉打标失败；该候选不入库，保留在 inbox 等待下一次命令重试。

视觉调用在确定性候选集合形成后由命令级队列并发执行，最多 10 个调用同时进行；库中已存在或批次内重复的 bytes 在视觉阶段之前跳过，超过 50 张的唯一候选标记为 `batch_deferred`。视觉 provider 不可用、超时、返回错误或结构不可信时，本次不复制图片、不创建可见 entry，只返回固定的 `visual_unavailable` 状态；该候选留在 inbox，其他队列候选继续处理，不把原始异常交给用户或日志。插件不主动创建脱离 handler 的持久化后台队列；宿主超时/取消时只执行当前运行时可观察到的取消和清理，不把可靠回收 core 底层调用写成契约。

### 6. 命令 service 只做语法分发和结果格式化

保留现有无参数 `/milky` 的 `get_impl_info` 路径。新增路径按以下顺序处理：

```text
/milky sticker <subcommand>
  -> 严格解析固定参数
  -> 仅使用 handler 已收到的 raw_args，不推断来源或操作者身份
  -> 进入单次 store operation
  -> 返回固定摘要/分类
```

`list` 使用稳定的 created-at + `sticker_id` 顺序并限制 20/100 条；返回受限的当前生效 `emotion`、`tags`、`description`、派生 `source=vision|manual` 和字段级 `field_sources`，不返回绝对路径、原始文件名、URL 或 bytes。`edit` 只接受 list 产生的 ID 和固定 set/clear option，不触碰图片文件；`--clear` 恢复视觉基线。`del` 只接受 list 产生的 ID，并在删除事务中检查唯一 hash 引用。`cleanup` 的 dry-run 先完成同样的扫描和引用分析但不提交删除；`reindex` 只处理已在 library 目录内且能通过受控格式/hash 校验的内容，不把 inbox 当作隐式输入。

贴纸路径不需要 Milky Action，也不在 handler 内验证命令是否来自 Milky friend/group、其他平台或 CLI。无参数路径仍必须有唯一已绑定 client 才能调用 `get_impl_info`；贴纸路径不会为了本地操作创建旁路 client。

### 7. 授权边界暂缓，不增加插件操作者配置

当前 Hermes core 的插件 handler 只收到 `raw_args`，没有可供插件可信判断的 Milky friend/group 来源上下文。gateway 虽可能在 handler 前检查 canonical `/milky`，但这不等于插件可以把后续贴纸写操作证明为 Milky-only 或 operator-only；其他平台或 CLI 仍可能以相同 handler 形状触发参数。

本 change 因此不增加插件级操作者环境变量、不复制 core 的用户 ID 策略，也不验证 `allow_admin_from`、`group_allow_admin_from`、`user_allowed_commands` 或 `group_user_allowed_commands` 能为贴纸子命令提供授权边界。授权能力待 Hermes core 向 handler 提供可信来源上下文后另行处理。

### 8. cleanup 的修复语义保守

cleanup 将库状态分成三类：有 entry 引用且文件存在（正常）、有 entry 但文件缺失（保留 metadata 并报告 missing_file）、无 entry 引用的完整文件或受控临时文件（可在正常模式删除）。它不删除 inbox，也不通过猜测补建 entry。

reindex 的扫描、索引替换、缺失引用和 orphan 语义详见第 9 节；cleanup 不借助 reindex 猜测或补建可见 entry。

### 9. reindex 只重建库文件技术索引

`reindex` 只扫描 `stickers/library/` 下的 regular file，不扫描 inbox、不调用视觉、不创建 `sticker_id`，也不从图片 bytes 推断情绪、标签或描述。每个文件必须通过受控相对路径、content-addressed 文件名、PNG/JPEG/GIF/WebP 结构、非空和 `10 MiB` 上限校验，并由流式 SHA-256 确认文件名 digest 与实际 bytes 一致；不满足条件的文件报告 `reindex_skipped`，不进入技术索引。

实现时先在内存或临时 staging 表中形成全部有效 `sticker_files` 记录，再开启一个数据库事务原子替换 `sticker_files` 索引；事务失败时回滚并保留旧索引。`sticker_entries` 不因 reindex 被创建、删除或改写：可见条目对应文件缺失时保留其元数据并报告 `missing_file`；合法但没有可见条目引用的库文件可以登记为技术索引中的 orphan，后续由 `cleanup` 按“无可见引用”规则回收。reindex 本身不删除任何库文件，`--dry-run` 也不需要额外语义。

### 10. 失败分类和普通消息隔离

命令层只向用户返回固定的 `invalid_input`、`batch_deferred`、`rejected`、`duplicate`、`missing_file`、`storage_error`、`visual_unavailable`、`unsupported` 等分类及低基数计数。logger 不写原始参数、路径、URL、图片 bytes、异常正文或凭证。视觉失败只影响当前候选，不阻塞普通 SSE、Hermes turn 或其他维护命令；store 或 metadata 提交失败只结束本次命令，不修改 SSE、Gate、Will、buffer、Hermes handoff、reply cost 或 outbound sender 状态。

## Risks / Trade-offs

- **[视觉模型判断不稳定]** 视觉模型可能误判主情绪或检索标签。→ 视觉结果不作为语义入库条件，`--dry-run` 只供操作者检查标签，`edit` 允许修正已入库元数据，人工投放仍是内容筛选边界。
- **[视觉 provider 不可用或占用资源]** 辅助模型可能超时、未配置或与主模型共享额度，且 core 可能已经进行内部重试或 fallback。→ 只在显式维护命令中调用，候选先确定性筛选和去重，命令级最多 10 个并发调用且不创建脱离命令生命周期的后台任务；插件只解析 core 的最终 envelope，不额外叠加同次调用重试；失败产生 `visual_unavailable`，候选留在 inbox，下一次命令增量重试。
- **[源文件长期占用磁盘]** add 不删除 inbox，重复扫描会保留源文件。→ 回执提供 duplicate 计数，文档说明由操作者自行清理 inbox；cleanup 永不触碰 inbox，降低误删风险。
- **[数据库事务与文件系统不是同一原子域]** 数据库成功和文件 replace 不能由单一事务覆盖。→ 采用先完成 content-addressed 文件、再提交 entry；未关联文件由受控 orphan cleanup 回收，entry 永不指向临时文件。
- **[超大或超多图片导致命令耗时]** 手动包可能包含大量文件，且单次视觉调用可能长时间等待。→ 单文件 10 MiB 上限、单次最多 50 张唯一候选、最多 10 个命令级并发调用、队列背压和逐条提交；`batch_deferred` 候选留在 inbox。当前 change 不承诺跨宿主超时的总时长预算或可靠回收 core 底层任务。
- **[handler 缺少可信来源上下文]** 插件无法证明写命令来自 Milky friend/group 或特定操作者。→ 明确搁置授权边界，不增加伪安全的 operator 配置；后续待 core 提供来源上下文后另行设计。

## Migration Plan

1. 发布实现与文档后，在 Hermes plugin-data 根目录创建 `stickers/inbox/`；已有安装不会自动扫描或导入任何文件。
2. 操作者将人工筛选后的图片包复制到 inbox，执行 `/milky sticker add --dry-run`；命令先做文件校验和 hash 去重，再显示每张候选的主情绪、中文检索标签和短描述。确认标签质量后执行正式 `add`；只有视觉分析成功且字段合法的条目入库，视觉失败的条目留在 inbox，等待下次命令增量重试。
3. 首次正式 add 创建 `stickers.db` 和库目录；后续升级通过 schema version 检查，未知或不兼容版本返回 `unsupported/storage_error`，不覆盖原数据。
4. 回滚实现时保留 `stickers/` 与 `stickers.db`；旧版本不识别该库时不得删除它。重新启用本 change 后可继续 list、cleanup 或 reindex。

## Open Questions

无。目录、命令、授权边界暂缓、视觉触发时机、结构化输出、单命令 50 张候选上限、文件上限、去重和失败语义已在规格中固定；实现阶段只需选择不改变这些外部行为的本地解析与事务写法。
