# Proposal

## Why

当前 Agent 只能按意图直接发送贴纸，无法比较候选或精确复用已知贴纸；为日常群聊提供可选的只读搜索和按 ID 发送，可以减少选图的不确定性，同时保留一次调用即可发送的快捷方式。何时发、怎么发的表达策略由用户在 SOUL 或记忆中维护，本提案只补齐工具能力，不声称工具扩展本身已改善使用意愿。

## What Changes

- 新增独立语义工具 `sticker_search(intent?, emotion?, tags?, limit?)`；至少提供一个查询条件，默认返回 5 条、最多 10 条，结果仅包含 opaque `sticker_id` 和有界的情绪、标签、描述。
- 扩展 `sticker_send` 为两种互斥模式：现有 `intent`/`emotion`/`tags` 查询发送，以及只提供 `sticker_id` 的精确发送。保留原查询参数、排序、轮换和一次调用发送能力，不要求先搜索。
- 精确发送重新验证条目、文件与当前可见性；不存在或不可见 ID 返回 `not_found`，不自动换图；搜索不发送、不更新使用统计。
- 两个工具的说明仅描述能力和必要参数约束，不增加聊天场景、频率、调用流程示例或回复收尾策略；不修改平台提示、SOUL 或记忆。
- 保留既有人工库可见范围、当前会话目标、发送前统计 claim、单次发送和未知结果不重试边界；不增加自动收藏、分类工具、缩略图、分页、同义词检索或 embedding。

## Capabilities

### New Capabilities

- `qq-sticker-search`：只读、有界的贴纸候选搜索，包含当前会话校验、确定性排序、最小结果、工具发现和简短描述边界。

### Modified Capabilities

- `qq-sticker-send`：允许互斥的 opaque ID 精确发送，明确查询模式与 ID 模式的区别、ID 失效分类以及搜索可返回 ID 而发送回执保持现状的边界。

## Impact

- 涉及 `plugin.yaml`、`outbound/tools.py`、`stickers/`、贴纸与工具注册测试，以及 README、ARCHITECTURE 和既有 QQ tools bundled skill 的能力说明。预计不增加运行时依赖或持久化 schema。
- 当前源码、测试和主规范明确拒绝 Agent 传入贴纸 ID；本 change 将同步修改这些限制。现有调用保持兼容，发送成功仍只返回 `status`、`message_id`。
- `add-qq-sticker-library` 尚未实施，规划中的 `keyword/category/index` 参数、scope 和成功后计数与本提案不同。本提案可基于当前人工库独立实施；将来的 library change 需要显式整合双模式契约与迁移，不得直接覆盖本提案。本次不编辑该 change。
- `preserve-milky-tool-results` 的远端 Action 结果工作与本地搜索结果无直接依赖；本 change 不扩大到原始 envelope 交付或通用日志改造。
- 本目录只记录规划；行为验收、真实 Hermes 工具发现及真实 Milky 发送尚未验证。
