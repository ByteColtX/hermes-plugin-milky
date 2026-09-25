# Spec Delta

## MODIFIED Requirements

### Requirement: 维护命令必须有固定语法、受限输出和明确结果

系统 MUST 提供无副作用的 `/milky sticker` 与 `/milky sticker help` 等价静态帮助，并支持 `sticker remove <sticker_id>` 作为 `del` 的等价别名。系统 MUST 支持以下 `/milky` 子命令：`sticker add [--dry-run]`、`sticker list [--limit <n>]`、`sticker edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]`、`sticker reanalyze <sticker_id>`、`sticker del <sticker_id>`、`sticker cleanup [--dry-run]` 和 `sticker reindex`。`--dry-run` SHALL 只允许扫描、校验、视觉分析和报告，不得移动、删除或写入库文件、元数据或索引。list SHALL 使用稳定顺序和有界结果；默认最多返回 `20` 条，`--limit` SHALL 为 `1` 至 `100` 的十进制整数。slash 结果 SHALL 按 slash-commands 统一展示约定渲染为中文文本，固定状态名表示业务语义而非要求保留 JSON 或英文前缀。结果 SHALL 保留已有使用统计及最近使用时间，其他信息 SHALL 只包含 `sticker_id`、格式、字节数、创建时间、当前生效的 `emotion`、有界 `tags`、有界 `description`、派生的 `source=vision|manual`、字段级 `field_sources`、固定状态和低敏计数；add 回执另 SHALL 报告 `junk` 与 `visual_unavailable`，reanalyze 回执 SHALL 报告 `not_sticker` 或 `visual_unavailable`，不包含绝对路径、URL、bytes、完整文件名或异常正文。

#### Scenario: list 查看空库

- **WHEN** 操作者执行 `/milky sticker list` 且库中没有可见条目
- **THEN** 系统 SHALL 以“Milky · 贴纸维护”为标题，显示“尚未添加贴纸。”和返回数量为零的中文摘要，并提供 `/milky sticker help` 入口
- **AND** SHALL 不触发文件扫描、视觉解析或 Milky Action

#### Scenario: list 限制输出数量

- **WHEN** 操作者执行 `/milky sticker list --limit 5`
- **THEN** 系统 SHALL 最多返回 5 个可见条目
- **AND** 条目顺序 SHALL 在同一库状态下保持稳定

#### Scenario: 非法维护语法

- **WHEN** 子命令不存在、缺少 `sticker_id`、`--limit` 越界、edit 缺少 set/clear option 或出现未声明参数
- **THEN** 系统 SHALL 返回表示 `invalid_input` 的中文格式错误及就近的 Usage、Help 提示
- **AND** SHALL 不修改文件、数据库或远端会话

#### Scenario: 删除别名执行一次且保持目标校验

- **WHEN** core 在相同库状态下分别分发 `sticker del demo_id` 和 `sticker remove demo_id`
- **THEN** 两者 SHALL 具有相同的参数校验、删除结果和中文回执，单次调用最多执行一次删除
- **AND** 非法 ID SHALL 不被解释为路径，缺少 ID SHALL 不回退当前会话或其他条目

## ADDED Requirements

### Requirement: 贴纸帮助必须覆盖全部维护操作及参数约束

贴纸静态帮助 SHALL 使用 Usage、Commands 和必要的 Options 分段，Examples SHALL 只保留导入预览与清除人工覆盖两个示例，展示 add、list、edit、reanalyze、del、cleanup、reindex、help，优先展示 del 并标注“别名 remove”。帮助 SHALL 明确 dry-run 的适用操作及预览含义、list 的既有默认数量和有效范围、edit 的固定枚举与字段选项、单 token 约束及 set/clear 冲突规则；完整内容 SHALL 可从贴纸帮助获取，参数错误只展示有关语法。示例 SHALL 使用合成 ID 和合法参数，不要求 shell quoting、不把路径或 URL 当作输入。

#### Scenario: 从帮助发现编辑与预览

- **WHEN** 用户查看贴纸帮助
- **THEN** 用户 SHALL 能通过命令语法和必要示例找到合法的导入预览、限制列表、编辑字段、清除人工覆盖和删除用法
- **AND** 所列参数和枚举 SHALL 与实际接受的参数一致，不展示尚未交付的操作

### Requirement: 贴纸查询与单项维护必须提供可读且可核验的结果

列表 SHALL 使用“Milky · 贴纸维护”标题，每个条目以不透明 ID 独立标识，按稳定顺序显示受限元数据、字段来源、格式/大小/创建时间与已有使用统计。情绪 SHALL 提供中文含义并保留可用于 edit 的枚举值；字段来源 SHALL 可区分人工设置和视觉分析。最近使用时间为空 SHALL 显示“尚未使用”，非空 SHALL 明示 UTC。数量 SHALL 表述为“本次显示 N 条”，不得将有界返回数量冒充全库总量；空库不输出空 JSON 数组。

edit、reanalyze、del/remove 的成功反馈 SHALL 说明实际动作和目标 ID；条目不存在、文件缺失、非贴纸判定、视觉不可用、竞争、存储失败与 unsupported SHALL 使用各自固定中文解释。仅在业务结果已保证时才能声称原条目未变或本次未执行；无法确认提交结果时 SHALL 提示先核验，不自动重复操作。

#### Scenario: 有界列表不冒充总数

- **WHEN** 库内条目数超过用户指定的合法 list 限制
- **THEN** 回复 SHALL 按实际返回结果展示条目和“本次显示 N 条”
- **AND** SHALL 保留条目 ID、字段来源和使用统计，不额外查询总量或写入状态

#### Scenario: 重新分析判定为非贴纸

- **WHEN** reanalyze 返回 not_sticker
- **THEN** 回执 SHALL 说明本次未更新及原条目保留
- **AND** SHALL 不声称已删除、隔离或更新成功

### Requirement: 贴纸批次与预览必须保留结果差异

add、cleanup、reindex SHALL 使用中文结果标题和分类计数，并显示已确认且与本操作有关的安全细节。add SHALL 区分已添加、重复、非贴纸隔离、拒绝、视觉失败、存储失败与批次延后；正式成功条目的 ID SHALL 保留。cleanup SHALL 区分未引用文件、临时文件、缺失引用与跳过，reindex SHALL 区分已索引、未引用、缺失与跳过，不声称缺失文件已修复。只要存在失败或延后，标题或正文 SHALL 明确有未完成项；零处理结果 SHALL 不表述为新增成功。

所有 dry-run SHALL 明示“预览”和“未作更改。”，使用“待添加”“待隔离”“待清理”等计划措辞，不把候选数写为已完成数。add 预览 SHALL 保留每个已分析候选的受限情绪、标签、描述和是否为贴纸的判定，不虚构待创建条目 ID。中文展示 SHALL 不改变既有计数单位、不强行合计不同单位的计数，也不得截断当前批次已有结果；较长输出 SHALL 使用既有发送流程。

#### Scenario: 部分导入失败

- **WHEN** add 同时存在已创建条目、视觉失败和批次延后
- **THEN** 回执 SHALL 以“贴纸导入部分完成”为标题，分别展示各结果的实际计数并明确存在未完成项
- **AND** SHALL 保留已提交条目 ID，不报告全部成功或自动重试失败候选

#### Scenario: 预览不冒充写入

- **WHEN** add dry-run 分别产生 would_add 与 would_move_to_junk，或 cleanup dry-run 发现待清理文件
- **THEN** 回复 SHALL 使用预览标题与计划计数，并明确未作更改
- **AND** add 预览 SHALL 保留候选元数据及判定，不声称已经入库或移动

#### Scenario: 修复命令发现缺失与跳过

- **WHEN** cleanup 或 reindex 报告 missing_file 或 reindex_skipped
- **THEN** 中文回执 SHALL 明确缺失或跳过对象的计数
- **AND** SHALL 不把发现缺失表述为已恢复文件，也不把索引重建表述为新增贴纸
