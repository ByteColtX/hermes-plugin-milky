# qq-sticker-maintenance Specification

## Purpose

为操作者提供只由显式 `/milky sticker` 命令驱动、可恢复且可审计的 QQ 贴纸本地维护闭环。

## Requirements

### Requirement: 贴纸维护必须限制在 plugin-data 和固定目录

系统 MUST 使用 Hermes `plugin_data_dir("hermes-plugin-milky")` 与独立
`plugin_db("hermes-plugin-milky", filename="stickers.db")`。输入只来自
`stickers/inbox/`，正式库和隔离目录分别为 `stickers/library/` 与 `stickers/junk/`；命令不得
接受或读取任意路径、URL、URI、符号链接或特殊文件。

#### Scenario: 维护输入边界

- **WHEN** 维护命令收到固定目录之外的输入
- **THEN** 系统 SHALL 拒绝该输入且不读取目标路径

### Requirement: add 必须先确定性校验去重再调用视觉

`add` SHALL 递归校验非空 PNG、JPEG、GIF、WebP regular file，单文件不超过 `10 MiB`，并以流式
SHA-256 去重。每次命令最多为 50 张唯一候选调用 Hermes `vision_analyze_tool`，同时最多 10 路；
超出部分返回 `batch_deferred` 并留在 inbox。视觉调用必须解析外层 JSON envelope 和内层 analysis
对象，严格校验单选 `emotion`、2–5 个中文 `tags`、20 字以内中文 `description` 和布尔
`is_sticker`。true 原子移动到 library 并写入 `sticker_items`/`sticker_files`，false 原子移动
到 junk；视觉失败、非法结构或移动失败不得伪造成功，源文件留在 inbox。

#### Scenario: add 校验失败

- **WHEN** inbox 中存在损坏、超限或重复文件
- **THEN** 系统 SHALL 在视觉分析前分类处理且不得伪造导入成功

### Requirement: 贴纸条目必须支持字段级维护和可恢复修复

`sticker_items.file_sha256` MUST 唯一，并保存随机不透明 `sticker_id`、`detected_*` 视觉基线、
当前生效字段、字段级 `vision|manual` 来源和 `created_at`/`updated_at`/`detected_at`。`edit`
必须在单事务中支持 set/clear 部分更新；`--clear` 恢复对应视觉基线。`reanalyze` 只更新合法
`is_sticker=true` 的视觉基线，人工字段保持；false 或失败保留原条目。`del` 只接受当前可见 ID，
`cleanup` 只回收无可见引用的 orphan/临时文件且不删除 junk，`reindex` 只扫描 library 并原子
重建 `sticker_files`，不创建条目或 ID。

#### Scenario: 字段级维护

- **WHEN** 操作者只修改或清除一个贴纸字段
- **THEN** 系统 SHALL 保留未指定字段、图片和不透明 ID

### Requirement: 维护命令必须有界、懒加载并隔离普通消息

系统 MUST 支持 `add`、`list`、`edit`、`reanalyze`、`del`、`cleanup`、`reindex` 及对应 `--dry-run`/`--limit`
语法。dry-run 不移动、删除或写入贴纸文件、数据库记录或索引。贴纸 store 只在有效维护命令中
懒加载，注册、普通连接、普通消息、关键词、Will 和 Agent 输出不得触发维护。handler 只按
`raw_args` 处理，不声明或实现 operator 身份授权。

#### Scenario: 普通消息不触发维护

- **WHEN** 插件处理普通消息、关键词、Will 或 Agent 输出
- **THEN** 系统 SHALL 不扫描贴纸目录、不打开贴纸 store 且不调用视觉能力

### Requirement: 使用统计必须不影响维护幂等性

新条目 MUST 初始化 `use_count=0`、`last_used_at=NULL`；list 和所有维护操作不得修改统计。预留
的发送接口只有在有效条目已发起发送调用后才原子递增一次，Milky 成功、失败或未知状态均不回滚，
统计写入失败不得重发已接受的消息。

#### Scenario: 维护操作不改变统计

- **WHEN** 操作者执行 list、edit、reanalyze、cleanup 或 reindex
- **THEN** 系统 SHALL 保持贴纸发送统计不变

### Requirement: 结果和日志必须脱敏

用户回执和日志 MUST 只能包含固定安全分类、低基数计数、受限元数据和不透明 ID，不得包含 token、
Authorization、绝对路径、URL、图片 bytes、完整参数、视觉原文或异常正文。贴纸维护失败不得改变
SSE、Gate、Will、buffer、Hermes handoff、reply cost 或出站 sender 状态。

#### Scenario: 维护失败保持脱敏

- **WHEN** 贴纸维护或存储操作失败
- **THEN** 回执和日志 SHALL 使用固定安全分类且不得包含凭证、路径或完整异常

### Requirement: 贴纸维护必须使用插件持久目录和固定输入边界

贴纸维护 SHALL 使用 Hermes 提供的插件持久目录作为唯一持久化根目录。输入目录 SHALL 固定为该根目录下的 `stickers/inbox/`，库文件和元数据 SHALL 位于同一插件持久化根目录的受控子目录或数据库中。系统 MUST NOT 写入插件安装目录、Hermes session DB、任意命令参数指定的路径或用户全局 skills 目录。

#### Scenario: 首次执行 add 创建维护目录

- **WHEN** 操作者首次执行 `/milky sticker add` 且插件持久目录尚不存在
- **THEN** 系统 SHALL 创建固定的 `stickers/inbox/` 和贴纸库所需目录
- **AND** SHALL 只在插件持久目录中创建文件或数据库对象

#### Scenario: 命令参数试图改变输入目录

- **WHEN** 命令参数包含绝对路径、相对路径、`..`、URL、`file://` 或其他输入目录
- **THEN** 系统 SHALL 返回 `invalid_input`
- **AND** SHALL 不读取、下载或写入该值指向的位置

### Requirement: add 必须只导入可验证的图片文件并保留原始输入

`/milky sticker add` SHALL 递归扫描固定 inbox 下的 regular file，且 SHALL 只接受已确认属于 PNG、JPEG、GIF 或 WebP 的非空图片。文件大小 SHALL 不超过 `10 MiB`；符号链接、目录、特殊文件、扩展名与内容不一致、损坏、不可读或超限文件 SHALL 被分类为 `rejected` 或对应的固定失败分类。确定性文件校验和 file_sha256 去重完成后，add SHALL 对尚未重复的候选调用 Hermes core 的辅助视觉能力生成元数据建议和 `is_sticker` 判定；只有完整结果结构合法且 `is_sticker=true` 的候选可以移动到 library 并创建可见条目，完整结果结构合法且 `is_sticker=false` 的候选 SHALL 移动到 `junk/` 且不得入库。视觉调用失败或结果结构非法的候选 SHALL 保留在 inbox，供后续命令增量重试。候选内容的来源和基础筛选由操作者负责，普通消息不得触发该流程。

#### Scenario: 导入受支持的静态图片和 GIF

- **WHEN** inbox 中包含可读取且格式与内容一致的 PNG、JPEG、GIF 或 WebP 文件
- **THEN** add SHALL 将其作为候选图片处理
- **AND** SHALL 保留 GIF 的原始 bytes 和动画格式

#### Scenario: 排除非图片和不安全文件

- **WHEN** inbox 中包含文本、压缩包、目录、符号链接、特殊文件、空文件、损坏图片或超过 `10 MiB` 的文件
- **THEN** add SHALL 报告对应的拒绝或失败计数
- **AND** SHALL 不为该文件创建可见贴纸条目或库文件

#### Scenario: 确定性筛选和去重先于视觉分析

- **WHEN** inbox 中包含多张图片，其中有格式无效文件、库中已存在的 bytes 或本批次内重复的 bytes
- **THEN** 系统 SHALL 先排除无效文件并按 file_sha256 去重
- **AND** SHALL 只对剩余的唯一候选执行视觉分析
- **AND** 每张候选图片 SHALL 最多触发一次视觉分析调用

#### Scenario: 视觉分析结果判定为贴纸

- **WHEN** 唯一候选的视觉结果可解析，且 `emotion`、`tags`、`description` 与 `is_sticker` 符合固定 schema，`is_sticker` 为 `true`
- **THEN** 正式 add SHALL 将该候选的原文件从 inbox 原子移动到 library，并将图片和视觉元数据一起提交
- **AND** 可见条目 SHALL 保存受限的 `emotion`、`tags` 和 `description` 元数据

#### Scenario: 视觉分析结果判定为非贴纸

- **WHEN** 唯一候选的视觉结果可解析，且 `emotion`、`tags`、`description` 与 `is_sticker` 符合固定 schema，`is_sticker` 为 `false`
- **THEN** 正式 add SHALL 将该候选的原文件从 inbox 原子移动到 `junk/`
- **AND** 系统 SHALL 返回或统计 `junk`
- **AND** 系统 SHALL 不创建 library 文件、`sticker_items` 或可见 `sticker_id`
- **AND** 后续 add SHALL 不自动扫描 `junk/`，操作者可直接删除文件，或手动移回 inbox 后重新执行 add

#### Scenario: 贴纸视觉元数据与人工判断不一致

- **WHEN** `is_sticker=true` 且视觉结果中的 `emotion`、`tags` 或 `description` 与操作者对图片的判断不一致
- **THEN** 系统 SHALL 将该结果作为视觉元数据建议保存或报告
- **AND** 正式 add SHALL 仍将其原文件移动到 library 并创建可见条目
- **AND** 操作者 SHALL 能通过 `edit` 修正入库后的元数据

#### Scenario: 视觉分析不可用或结果不可信

- **WHEN** Hermes core 视觉能力不可用、超时、返回错误、返回非 JSON 对象或字段不符合固定枚举/长度边界
- **THEN** 系统 SHALL 报告 `visual_unavailable` 或等价的固定状态
- **AND** SHALL 不移动该图片、不创建库文件或可见条目
- **AND** SHALL 保留 inbox 原文件，下一次 add SHALL 能重新尝试该图片
- **AND** SHALL 不向用户或日志输出原始异常、完整模型回复、路径或图片内容

#### Scenario: add 按视觉结果移动人工投放文件

- **WHEN** add 对 inbox 文件得到合法的 `is_sticker=true` 或 `is_sticker=false` 结果
- **THEN** `is_sticker=true` 的原文件 SHALL 移动到 library，`is_sticker=false` 的原文件 SHALL 移动到 `junk/`
- **AND** 成功处理的原文件 SHALL 不再留在 inbox

#### Scenario: 移动失败保留源文件

- **WHEN** 合法视觉结果已经得到，但移动到 library 或 `junk/` 失败
- **THEN** 系统 SHALL 报告 `storage_error`
- **AND** SHALL 不创建可见条目
- **AND** 源文件 SHALL 保留在 inbox，供下一次命令处理

### Requirement: 视觉辅助结果必须结构化、有界且与主 Agent 隔离

贴纸维护的视觉辅助 SHALL 只在到达插件 command handler 的显式 `sticker add`、`add --dry-run` 或 `reanalyze` 参数中运行；`add` SHALL 在确定性校验和去重之后按稳定顺序最多纳入 `50` 张唯一候选，第 `51` 张及以后 SHALL 报告 `batch_deferred`、保留在 inbox 且不得调用视觉。当前批次同时进行中的视觉调用 SHALL 不超过 `10` 个，任一调用完成后 SHALL 立即从当前批次队列补入下一候选。正式 add 中每个视觉结果成功的候选 SHALL 独立完成原子移动和元数据提交，不得等待整批候选完成；`is_sticker=true` 的候选 SHALL 移动到 library 并创建可见条目，`is_sticker=false` 的候选 SHALL 移动到 `junk/` 且不得入库；正常完成时命令 SHALL 等待当前批次候选进入成功提交、`junk`、重复、固定失败或 `batch_deferred` 状态后返回。宿主超时或取消时，系统 SHALL 保证已提交条目保持可见、尚未完成移动或提交的候选保持在 inbox；本 change 不承诺可靠回收已由 Hermes core 发出的底层视觉调用。`vision_analyze_tool` 返回的字符串 SHALL 先解析为外层 JSON envelope；只有外层 `success=true`、读取 `analysis`、去除精确匹配的允许 scale note 前缀，并将剩余 `analysis` 严格解析为单个 JSON 对象后，才可校验其中的 `emotion`、`tags`、`description` 和 `is_sticker`。视觉结果 SHALL 是单个内层 JSON 对象，包含固定枚举的单选 `emotion`、2–5 个中文 `tags`、20 个字符以内的中文 `description` 和严格布尔 `is_sticker`；固定枚举、数量、语言、长度或布尔类型约束不满足时 SHALL 报告 `visual_unavailable`，add 候选不得移动文件、创建库文件或可见条目，且 SHALL 保留在 inbox 供下一次命令重试。情绪、标签和描述只作为已接收条目的元数据建议，`is_sticker` 是新增候选的唯一语义入库门槛。视觉辅助 MUST NOT 创建 Agent tool call、写入主 Agent transcript、启动 handoff 或触发普通消息流程；插件不主动创建脱离 handler 的持久化后台队列。操作者 SHALL 能通过显式 `edit` 命令修正已入库的视觉元数据，并通过 `reanalyze` 重新生成视觉基线。

#### Scenario: dry-run 先给出视觉预览

- **WHEN** 操作者执行 `/milky sticker add --dry-run`
- **THEN** 系统 SHALL 完成与正式 add 相同的文件校验、去重和视觉分析
- **AND** SHALL 返回每个已分析候选的主情绪、中文检索标签、描述摘要和 `is_sticker` 判定
- **AND** `is_sticker=true` 的候选 SHALL 标记为 `would_add`，`is_sticker=false` 的候选 SHALL 标记为 `would_move_to_junk`
- **AND** SHALL 不移动、删除或写入任何贴纸文件、数据库记录或可见条目

#### Scenario: 解析视觉外层 envelope 和内层 analysis

- **WHEN** `vision_analyze_tool` 返回 JSON 字符串，外层对象为 `{"success": true, "analysis": "...", "scale_note": "..."}`，且 `analysis` 包含带 `is_sticker` 布尔字段的合法贴纸元数据 JSON
- **THEN** 系统 SHALL 先解析外层对象并检查 `success=true`
- **AND** SHALL 只去除与 `scale_note` 精确匹配的 core 前缀，再解析 `analysis` 内层 JSON
- **AND** SHALL 仅在内层 JSON 为单个对象且字段符合 schema 时按 `is_sticker` 决定移动到 library 或 `junk/`

#### Scenario: 失败 envelope 或空/非法 analysis 不入库

- **WHEN** core 返回 `success=false`、带 `error` 的失败 envelope、外层 JSON 非对象、缺少/为空的 `analysis`，或内层 `analysis` 不是合法 JSON 对象
- **THEN** 系统 SHALL 报告 `visual_unavailable`
- **AND** SHALL 不把错误说明或 fallback 文本当作贴纸元数据
- **AND** SHALL 保留 inbox 原文件并允许下一次 add 重试

#### Scenario: 不重复 core 已执行的内部重试

- **WHEN** core 已因空结果、图片缩放或传输错误完成内部重试/替代 provider，并返回最终 envelope
- **THEN** 系统 SHALL 只解析该次调用的最终 envelope
- **AND** SHALL 不在同一次命令中再次调用 `vision_analyze_tool`
- **AND** 失败时 SHALL 将候选留在 inbox，等待下一次显式 add

#### Scenario: 视觉并发上限和队列补位

- **WHEN** 去重后的唯一候选为 `11` 至 `50` 张
- **THEN** 系统 SHALL 将全部唯一候选纳入当前命令的视觉队列
- **AND** SHALL 同时最多发起 `10` 个视觉 provider 请求
- **AND** 任一请求完成后 SHALL 立即为下一候选释放并补入一个并发槽位
- **AND** SHALL 不创建脱离当前命令 handler 的持久化视觉队列

#### Scenario: 单次批次上限

- **WHEN** 确定性校验和去重后有超过 `50` 张唯一候选
- **THEN** 系统 SHALL 只将稳定顺序的前 `50` 张纳入当前视觉批次
- **AND** 第 `51` 张及以后 SHALL 报告 `batch_deferred`
- **AND** 被延后的候选 SHALL 保留在 inbox 且 SHALL 不调用视觉

#### Scenario: 单个候选完成后立即入库

- **WHEN** 正式 add 中某个候选的视觉结果成功，且其他候选仍在视觉处理中或排队
- **THEN** 若 `is_sticker=true`，系统 SHALL 立即为该候选完成独立的原子移动和元数据提交
- **AND** 若 `is_sticker=false`，系统 SHALL 立即将该候选移动到 `junk/` 且不创建可见条目
- **AND** `is_sticker=true` 的候选 SHALL 在其他候选完成前成为可见条目
- **AND** 已释放的视觉并发槽位 SHALL 继续处理队列中的下一候选

#### Scenario: 命令取消或宿主超时时保留未提交候选

- **WHEN** 操作者取消 add 或宿主在视觉调用完成前超时，且仍有候选正在视觉处理或排队
- **THEN** 系统 SHALL 不为未完成移动或提交的候选创建库文件或可见条目
- **AND** 已完成原子提交的条目 SHALL 保持可见
- **AND** 正在处理或排队但尚未移动或提交的候选 SHALL 保留在 inbox
- **AND** 本 change SHALL 不把 Hermes core 对已发出底层调用的回收能力声明为可靠保证

#### Scenario: 单个候选失败不阻塞队列

- **WHEN** 某个候选的视觉调用失败、超时或返回非法结构
- **THEN** 系统 SHALL 将该候选保留在 inbox 并报告 `visual_unavailable`
- **AND** 其他正在处理或排队的候选 SHALL 继续执行
- **AND** 失败候选 SHALL 不创建库文件或可见条目

#### Scenario: 视觉结果字段有界

- **WHEN** 视觉服务返回结果
- **THEN** `emotion` SHALL 为 `joy|sadness|anger|surprise|fear|disgust|love|approval|confusion|neutral|mixed|unknown`
- **AND** `emotion` SHALL 只允许一个值，不得返回数组或多个主情绪
- **AND** `tags` SHALL 包含 2 至 5 个不重复的中文标签，每个不超过 16 个字符，且可以与 `emotion` 的中文含义重叠
- **AND** `description` SHALL 为不超过 20 个字符的中文内容简述，图片含文字时 SHALL 概括文字含义而非抄录长文本
- **AND** `is_sticker` SHALL 为 JSON 原生布尔值 `true` 或 `false`，不得接受字符串、数字或缺失字段

#### Scenario: 主 Agent 上下文保持不变

- **WHEN** 视觉辅助在贴纸维护命令中成功或失败
- **THEN** 系统 SHALL 不创建主 Agent turn、tool message、transcript 条目或 handoff
- **AND** 普通消息的 Gate、Will、buffer、reply cost 和出站状态 SHALL 保持不变

### Requirement: edit 必须支持字段级部分更新和人工覆盖清除

`sticker_items` SHALL 将 `detected_emotion`、`detected_tags_json`、`detected_description` 作为最近一次合法视觉结果的基线，将 `emotion`、`tags_json`、`description` 作为当前生效值，并以 `emotion_source`、`tags_source`、`description_source` 记录每个字段的 `vision|manual` 来源；`created_at`、`updated_at` 和 `detected_at` SHALL 分别表示条目创建、最近一次任意元数据更新和最近一次视觉基线更新。命令和 Agent 对外仍使用逻辑字段 `emotion`、`tags`、`description`，`tags_json` 仅为数据库内部表示。

`sticker_items` SHALL 额外保存 `use_count` 和可空的 `last_used_at`；新条目 SHALL 初始化为 `use_count=0`、`last_used_at=NULL`。本 change 的 `add`、`edit`、`reanalyze`、`del`、`cleanup`、`reindex` 和 `sticker_search` SHALL 不修改这两个字段。后续 `sticker_send` 在有效贴纸已解析并发起发送调用时，才 SHALL 原子地执行 `use_count = use_count + 1` 并写入当前 UTC 的 `last_used_at`；Milky Action 随后的成功、失败或未知状态均不得回滚该计数，计数写入失败 SHALL 不重发已接受的消息，也 SHALL 不宣称 QQ 用户已实际看到消息。

`/milky sticker edit <sticker_id>` SHALL 使用以下固定语法：`[--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<emotion|tags|description>[,<field>...]]`；每个 option SHALL 是单个 `--name=value` raw-args token，`description` 值 SHALL 不跨空白 token，命令 SHALL 不依赖 shell quoting。至少需要一个 set 或 clear option；未出现的字段 SHALL 保持不变；同一字段同时 set 和 clear、未知 option、空值、非法枚举、重复标签、标签不在 2–5 个范围内或描述超过 20 个字符时，整条命令 SHALL 返回 `invalid_input` 且不修改任何字段。`--clear` SHALL 清除指定字段的人工覆盖并恢复对应的视觉基线值，而不是写入空标签或空情绪。数据库 SHALL 为 `emotion`、`tags`、`description` 分别保存视觉基线、生效值和 `*_source=vision|manual`；列表中的行级 `source` SHALL 派生为任一字段为 `manual` 时为 `manual`，否则为 `vision`，并 SHALL 可返回 `field_sources`。edit 不得修改图片 bytes、file_sha256、库文件引用、技术索引、`use_count`、`last_used_at` 或 `sticker_id`。

#### Scenario: edit 只更新指定字段

- **WHEN** handler 收到 `sticker edit <sticker_id> --tags=开心,安慰,摸头`
- **THEN** 系统 SHALL 只更新 `tags` 生效值并将 `tags_source` 设为 `manual`
- **AND** `emotion`、`description` 及其来源 SHALL 保持不变
- **AND** 图片文件、file_sha256、技术索引和 `sticker_id` SHALL 保持不变

#### Scenario: edit 清除人工覆盖

- **WHEN** 某字段当前为 `manual`，且 handler 收到 `sticker edit <sticker_id> --clear=tags`
- **THEN** 系统 SHALL 将当前 `tags` 恢复为该条目的视觉基线 `detected_tags_json`
- **AND** SHALL 将 `tags_source` 恢复为 `vision`
- **AND** SHALL 不写入空数组或重新调用视觉能力

#### Scenario: edit 支持多个字段的原子部分更新

- **WHEN** handler 收到同一条命令中的合法 `--emotion=<enum>`、`--tags=<...>` 或 `--description=<text>` 的任意组合
- **THEN** 系统 SHALL 在一个数据库事务中更新这些指定字段及其来源
- **AND** 未指定字段 SHALL 保持不变
- **AND** 任一字段写入失败时 SHALL 回滚本条命令的全部字段修改

#### Scenario: edit 非法字段不产生部分写入

- **WHEN** handler 收到缺少 set/clear option、set 与 clear 同字段、非法枚举、重复标签、标签数量越界或描述超过 20 个字符的 edit 命令
- **THEN** 系统 SHALL 返回 `invalid_input`
- **AND** SHALL 不修改视觉基线、生效值、字段来源、图片文件或技术索引

#### Scenario: 重复 add 不覆盖人工字段

- **WHEN** 某条贴纸的一个或多个字段来源为 `manual`，且 inbox 中再次出现相同 file_sha256
- **THEN** add SHALL 返回 `duplicate`
- **AND** SHALL 不重新调用视觉能力，也 SHALL 不覆盖视觉基线、生效值或字段来源
- **AND** 在确认 library 中已有完整同 hash 文件后，SHALL 移除 inbox 中的冗余副本

### Requirement: 使用统计必须可追踪且不影响维护幂等性

`list` 返回的每个可见条目 SHALL 包含 `use_count` 和可空的 `last_used_at`。`use_count` SHALL 为不小于零的整数，`last_used_at` SHALL 使用 UTC 时间或 `NULL`。维护命令和搜索操作 SHALL 只读这两个字段；未来的 `sticker_send` 发送路径在有效贴纸已解析并发起发送调用时 SHALL 只递增一次，并使用原子数据库更新；Milky Action 随后的成功、失败或未知状态均不得回滚该计数；计数更新失败时 SHALL 不重发消息，并将统计持久化失败作为独立的 `storage_error` 处理。

#### Scenario: 新条目初始化使用统计

- **WHEN** 合法 `is_sticker=true` 的候选首次创建 `sticker_items`
- **THEN** `use_count` SHALL 为 `0`
- **AND** `last_used_at` SHALL 为 `NULL`

#### Scenario: 维护和搜索不改变使用统计

- **WHEN** 操作者执行 `add`、`edit`、`reanalyze`、`del`、`cleanup`、`reindex` 或 `sticker_search`
- **THEN** 系统 SHALL 不因这些操作增加 `use_count`
- **AND** SHALL 不因这些操作更新 `last_used_at`

#### Scenario: 无效发送不计数

- **WHEN** `sticker_send` 无法解析有效的 `sticker_id`、发送目标，或尚未发起 Milky 发送调用就失败
- **THEN** 系统 SHALL 不增加 `use_count`
- **AND** SHALL 不更新 `last_used_at`

#### Scenario: 发起发送后原子更新使用统计

- **WHEN** 后续 `sticker_send` 已解析有效贴纸并发起 Milky 发送调用
- **THEN** 系统 SHALL 将目标条目的 `use_count` 原子增加 `1`
- **AND** SHALL 将 `last_used_at` 更新为当前 UTC 时间
- **AND** 同一次 `sticker_send` 调用 SHALL 最多计数一次；显式发起新的 `sticker_send` 重试 SHALL 重新计数

#### Scenario: Milky 状态不影响计数

- **WHEN** Milky 发送 Action 在计数更新后返回成功、失败或结果未知
- **THEN** 系统 SHALL 不因 Milky 返回状态回滚该次使用计数
- **AND** SHALL 不重发已经被接受的消息

#### Scenario: 统计写入失败不重复发送

- **WHEN** 有效 `sticker_send` 已发起发送，但 `use_count` 或 `last_used_at` 持久化失败
- **THEN** 系统 SHALL 不因统计失败重发 Milky 消息
- **AND** 统计写入失败 SHALL 返回或记录独立的 `storage_error`

### Requirement: reanalyze 必须支持已入库贴纸的重新视觉打标

合法且 `is_sticker=true` 的 reanalyze 结果 SHALL 替换 `detected_emotion`、`detected_tags_json`、`detected_description`，写入新的 `detected_at` 并更新 `updated_at`；`created_at`、`file_sha256`、库文件和 `sticker_id` SHALL 保持不变。来源为 `vision` 的当前字段跟随新基线，来源为 `manual` 的当前字段保持不变。

`/milky sticker reanalyze <sticker_id>` SHALL 只接受当前可见的 `sticker_id`，读取该条目的 library 文件，并使用与 add 相同的固定 prompt、视觉 envelope 解析和内层 schema 校验。只有合法且 `is_sticker=true` 的结果 SHALL 更新视觉基线；当前字段来源为 `vision` 的 `emotion`、`tags`、`description` SHALL 跟随新基线更新，来源为 `manual` 的当前字段 SHALL 保持不变。图片 bytes、file_sha256、library 文件、技术索引和 `sticker_id` SHALL 保持不变。视觉失败、结果非法或合法结果的 `is_sticker=false` SHALL 保留原条目的全部数据，并分别报告 `visual_unavailable` 或 `not_sticker`；`reanalyze` SHALL 不把已入库文件移动到 `junk/`。

#### Scenario: reanalyze 成功更新视觉字段

- **WHEN** 操作者执行 `/milky sticker reanalyze <sticker_id>`，视觉返回合法对象且 `is_sticker=true`
- **THEN** 系统 SHALL 更新该条目的视觉基线
- **AND** SHALL 写入新的 `detected_at` 并更新 `updated_at`，但不改变 `created_at`
- **AND** 来源为 `vision` 的当前字段 SHALL 使用新的 emotion、tags 和 description
- **AND** 来源为 `manual` 的字段 SHALL 保持原值和 `manual` 来源
- **AND** 图片文件、file_sha256、技术索引和 sticker ID SHALL 不变

#### Scenario: reanalyze 返回非贴纸

- **WHEN** reanalyze 的视觉结果合法但 `is_sticker=false`
- **THEN** 系统 SHALL 返回 `not_sticker`
- **AND** SHALL 保留原视觉基线、当前字段、字段来源、文件和可见条目
- **AND** SHALL 不移动文件到 `junk/`、不删除条目或创建新条目

#### Scenario: reanalyze 失败保持原条目

- **WHEN** reanalyze 的视觉调用失败、外层 envelope 非法、analysis 非法或字段 schema 校验失败
- **THEN** 系统 SHALL 返回 `visual_unavailable`
- **AND** SHALL 保留原条目的视觉基线、生效字段、字段来源和文件
- **AND** SHALL 允许下一次显式 reanalyze 重试

#### Scenario: reanalyze 元数据提交失败回滚

- **WHEN** 合法 `is_sticker=true` 结果在替换视觉基线时发生数据库错误
- **THEN** 系统 SHALL 返回 `storage_error`
- **AND** SHALL 保留更新前的视觉基线、生效字段和字段来源
- **AND** SHALL 不修改图片文件或技术索引

### Requirement: 导入必须按内容去重并以原子方式提交

系统 SHALL 对候选图片 bytes 计算 SHA-256，并在同一插件库中以 content identity 去重；同一 bytes 只能对应一个可见 `sticker_id`。新条目只有在图片库文件已完整、可读取地提交且元数据变更已成功提交后才可见。任一阶段失败 SHALL 不留下半条目、损坏的可见文件或伪造的成功结果。

#### Scenario: 重复执行 add

- **WHEN** inbox 中同一图片 bytes 被 add 多次
- **THEN** 后续执行 SHALL 返回或统计 `duplicate`
- **AND** SHALL 不增加第二份库文件或第二个可见 `sticker_id`

#### Scenario: 原子提交失败

- **WHEN** 临时文件写入、原子替换、hash 校验或元数据提交失败
- **THEN** 系统 SHALL 返回或统计 `storage_error`
- **AND** SHALL 不把该图片显示为已入库

#### Scenario: 进程在导入中断

- **WHEN** add 在某个文件处理期间被取消、停止或进程中断
- **THEN** 下次维护命令 SHALL 能识别并清理未完成的临时文件
- **AND** 已提交的完整条目 SHALL 保持可见，未提交条目 SHALL 不可见

### Requirement: 维护命令必须有固定语法、受限输出和明确结果

系统 MUST 支持以下 `/milky` 子命令：`sticker add [--dry-run]`、`sticker list [--limit <n>]`、`sticker edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]`、`sticker reanalyze <sticker_id>`、`sticker del <sticker_id>`、`sticker cleanup [--dry-run]` 和 `sticker reindex`。`--dry-run` SHALL 只允许扫描、校验、视觉分析和报告，不得移动、删除或写入库文件、元数据或索引。list SHALL 使用稳定顺序和有界结果；默认最多返回 `20` 条，`--limit` SHALL 为 `1` 至 `100` 的十进制整数。结果 SHALL 只包含 `sticker_id`、格式、字节数、创建时间、当前生效的 `emotion`、有界 `tags`、有界 `description`、派生的 `source=vision|manual`、字段级 `field_sources`、固定状态和低敏计数；add 回执另 SHALL 报告 `junk` 与 `visual_unavailable`，reanalyze 回执 SHALL 报告 `not_sticker` 或 `visual_unavailable`，不包含绝对路径、URL、bytes、完整文件名或异常正文。

#### Scenario: list 查看空库

- **WHEN** 操作者执行 `/milky sticker list` 且库中没有可见条目
- **THEN** 系统 SHALL 返回空库摘要和 `count=0`
- **AND** SHALL 不触发文件扫描、视觉解析或 Milky Action

#### Scenario: list 限制输出数量

- **WHEN** 操作者执行 `/milky sticker list --limit 5`
- **THEN** 系统 SHALL 最多返回 5 个可见条目
- **AND** 条目顺序 SHALL 在同一库状态下保持稳定

#### Scenario: 非法维护语法

- **WHEN** 子命令不存在、缺少 `sticker_id`、`--limit` 越界、edit 缺少 set/clear option 或出现未声明参数
- **THEN** 系统 SHALL 返回 `invalid_input` 和固定 usage 提示
- **AND** SHALL 不修改文件、数据库或远端会话

### Requirement: 贴纸维护授权边界暂不由本 change 提供

本 change SHALL 只按插件 command handler 收到的 `raw_args` 处理贴纸维护参数，不得宣称这些参数一定来自 Milky friend/group，也不得宣称写操作具备 operator-only 边界。插件 MUST NOT 增加操作者 ID、来源判断或第二套授权配置；Hermes core 能否在 handler 前拒绝 canonical `/milky` 不属于本 change 对贴纸写操作来源的保证。授权边界待 core 向 handler 提供可信来源上下文后另行处理。

#### Scenario: handler 收到贴纸维护参数

- **WHEN** 插件 command handler 收到合法的 `sticker add`、`list`、`edit`、`reanalyze`、`del`、`cleanup` 或 `reindex` 参数
- **THEN** 系统 SHALL 按本 change 的语法、持久化和视觉规则处理参数
- **AND** SHALL 不读取或推断未随 handler 传入的 Milky friend/group、平台或操作者身份

#### Scenario: 不新增插件操作者授权配置

- **WHEN** 部署者配置插件或执行贴纸维护命令
- **THEN** 插件 SHALL 不要求或读取 `MILKY_STICKER_OPERATOR_IDS` 或等价的插件级操作者配置
- **AND** 本 change SHALL 不验证 `allow_admin_from`、`group_allow_admin_from`、`user_allowed_commands` 或 `group_user_allowed_commands` 能否约束贴纸子命令

#### Scenario: 非显式普通流程不触发维护

- **WHEN** 普通消息正文、入站图片、关键词、Will 决策或 Agent 输出没有到达贴纸维护 command handler 的显式参数路径
- **THEN** 系统 SHALL 不执行 add、edit、reanalyze、del、cleanup 或 reindex
- **AND** SHALL 不把贴纸维护作为普通消息旁路或 Agent Tool 暴露

#### Scenario: 普通消息或 Agent 输出触发维护

- **WHEN** 普通消息正文、图片、关键词、Will 决策、Agent 输出或其他事件没有显式匹配维护命令
- **THEN** 系统 SHALL 不执行 add、edit、reanalyze、del、cleanup 或 reindex
- **AND** SHALL 不把贴纸维护作为普通消息旁路或 Agent Tool 暴露

### Requirement: del 必须按可见 sticker_id 删除并保护库文件一致性

`/milky sticker del <sticker_id>` SHALL 只接受 list 返回的当前库可见 ID。`sticker_items.file_sha256` SHALL 唯一，因此本 change 不支持多个可见条目共享同一库文件。删除事务 SHALL 先验证该 `file_sha256` 只有目标条目引用，再移除可见条目并提交；事务提交后，才可回收对应库文件或将其交给 cleanup。若发现违反唯一约束的异常多引用，事务 SHALL 回滚、保留库文件并报告 `storage_error`，不得误删。未知、格式错误或已经删除的 ID SHALL 返回 `sticker_not_found` 或 `invalid_input`，不得将其解释为路径、URL、hash 查询或其他命令。

#### Scenario: 删除现有条目

- **WHEN** 操作者使用当前 list 中的有效 `sticker_id` 执行 del
- **THEN** 该条目 SHALL 从可见库中移除
- **AND** 在确认没有其他条目引用其 `file_sha256` 后，底层库文件 SHALL 才可回收

#### Scenario: 删除时发现异常多引用

- **WHEN** del 发现待删除条目的 `file_sha256` 仍被其他条目引用
- **THEN** 系统 SHALL 保留底层库文件
- **AND** SHALL 返回或统计 `storage_error`
- **AND** SHALL 不删除其他条目或其文件

#### Scenario: 删除未知 ID

- **WHEN** 操作者提交不属于当前库的 ID
- **THEN** 系统 SHALL 返回 `sticker_not_found`
- **AND** SHALL 不删除任何文件或其他条目

### Requirement: cleanup 和 reindex 必须可预览、可恢复且不误删

`cleanup` SHALL 识别库内 orphan file、缺失引用文件、残留临时文件和无效技术索引；正常模式只删除确认无可见条目引用的 orphan 或残留临时文件，发现缺失引用时 SHALL 保留元数据并报告 `missing_file`。`cleanup` SHALL NOT 删除或扫描 `junk/` 中的文件。`--dry-run` SHALL 只报告计划动作。`reindex` SHALL 只扫描 `stickers/library/`，校验受控相对路径、content-addressed 文件名、PNG/JPEG/GIF/WebP 结构、非空、`10 MiB` 上限和流式 SHA-256；通过校验的文件 SHALL 在一个数据库事务中原子重建 `sticker_files` 技术索引，事务失败 SHALL 保留旧索引。reindex SHALL 不扫描 inbox 或 `junk/`、不调用视觉、不创建或删除 `sticker_items`、不修改任何视觉基线/生效元数据或字段来源；合法但没有可见条目引用的文件 SHALL 记为 orphan，缺失的可见条目 SHALL 保留元数据并报告 `missing_file`，无法确认的库文件 SHALL 报告 `reindex_skipped`。

#### Scenario: dry-run 不产生变更

- **WHEN** 操作者执行 `/milky sticker cleanup --dry-run` 或 `/milky sticker add --dry-run`
- **THEN** 系统 SHALL 返回待创建、重复、拒绝、待删除、缺失和跳过计数
- **AND** SHALL 不写入、替换或删除任何库文件、数据库记录或 inbox 文件

#### Scenario: cleanup 发现缺失引用

- **WHEN** cleanup 发现可见条目引用的库文件已经不存在
- **THEN** 系统 SHALL 保留该条目元数据并报告 `missing_file`
- **AND** SHALL 不把该条目报告为已修复，也 SHALL 不删除其他仍被引用的内容

#### Scenario: reindex 重建技术索引

- **WHEN** reindex 扫描 library 中包含合法 content-addressed 文件，且其中部分文件没有可见条目引用
- **THEN** 系统 SHALL 为通过校验的文件重建 `sticker_files` 记录
- **AND** SHALL 将没有可见条目引用的文件报告为 orphan
- **AND** SHALL 不创建 `sticker_id`、不生成视觉元数据或提升文件为可见贴纸

#### Scenario: reindex 保留缺失条目元数据

- **WHEN** reindex 发现可见条目引用的 `file_sha256` 在 library 中没有对应文件
- **THEN** 系统 SHALL 保留该条目的视觉基线、生效字段、字段来源和 `sticker_id`
- **AND** SHALL 报告 `missing_file`

#### Scenario: reindex 发现未知库文件

- **WHEN** reindex 发现不符合受控命名或无法通过格式校验的库文件
- **THEN** 系统 SHALL 报告 `reindex_skipped`
- **AND** SHALL 不把它加入可见库或覆盖已有有效元数据

#### Scenario: reindex 事务失败回滚

- **WHEN** reindex 在替换 `sticker_files` 技术索引时发生数据库错误
- **THEN** 系统 SHALL 返回 `storage_error`
- **AND** SHALL 保留 reindex 前的技术索引和全部 `sticker_items`
- **AND** SHALL 不删除或修改任何库文件

### Requirement: 维护失败必须隔离于普通 Hermes 消息流程

贴纸目录、数据库、权限或命令处理失败 SHALL 被压缩为固定安全分类并通过命令回执返回；不得泄露 token、Authorization、QQ/群之外的敏感身份、绝对路径、URL、图片内容、原始异常或完整命令参数。维护失败 SHALL 不改变 Milky SSE、普通消息的 Gate/Will/buffer、Hermes handoff 或出站发送状态。

#### Scenario: 存储不可用

- **WHEN** 插件持久目录不可写、数据库不可用或索引版本不兼容
- **THEN** 命令 SHALL 返回 `storage_error` 或 `unsupported`
- **AND** 普通 Milky 消息 SHALL 继续使用既有入站路径

#### Scenario: 失败结果脱敏

- **WHEN** 维护命令遇到文件、数据库或权限异常
- **THEN** 用户可见回执和日志 SHALL 只包含命令名、固定分类、低基数计数和必要的脱敏关联 ID
- **AND** SHALL 不包含异常正文、绝对路径、URL、图片 bytes 或凭证
