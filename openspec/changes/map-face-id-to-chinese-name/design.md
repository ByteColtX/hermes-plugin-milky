## Context

See `proposal.md` for the motivation. 当前 `inbound/extractor.py` 在遍历 typed `FaceSegment` 时直接把
`face_id` 放入 `[face:...]`；`milky/face_catalog.json` 已存在于插件目录，包含 `packs[].emojis[]`
及其 `qSid`、`qDes`。现行 `message-segments` 规范要求保留原始 segment 语义，并要求
normalizer 不执行网络或文件系统操作，因此目录读取不能发生在每条消息的规范化路径中。

## Goals / Non-Goals

**Goals:**

- 在插件加载的本地边界建立一次只读的 face label 映射，供无副作用的 placeholder 生成使用。
- 只映射非 `emoji 表情` pack 的有效 `qSid`/`qDes`，保留 emoji face_id 的原始可读形式。
- 对目录缺失、JSON/结构错误、无效条目和歧义映射采用确定性回退，不影响其他 segment 的处理。
- 保持入站消息顺序、策略文本、typed segment、媒体延迟引用和出站 face 行为不变。

**Non-Goals:**

- 不从网络、Milky Action、SSE 事件正文或 Hermes 上下文动态获取表情名称。
- 不把 `packName` 渲染到 placeholder，不把 `emoji 表情` 的 `qDes` 翻译成中文，也不修改 emoji 字符本身。
- 不清理或改写 `qDes` 的内容；目录中的前导 `/` 等字符按原值保留。
- 不修改 `FaceSegment` DTO、协议 parser、出站 formatter、ToolSpec、Will 或任意 Hermes core 行为。

## Decisions

### 在模块加载边界预加载并冻结映射

新增本地 catalog 解析边界，使用插件自身目录中的 `milky/face_catalog.json` 读取一次并生成只读
映射；`extract_segments()` 仅接收/使用内存中的映射，不在消息处理期间访问文件系统。读取或解析
失败时初始化为空映射，后续 placeholder 走原 `face_id` 回退，不能因为可选目录阻止插件加载。

选择预加载而不是在首次 `face` 消息时懒加载，是为了满足 normalizer 的无文件系统 I/O 契约；选择
插件目录资源而不是当前工作目录，是为了让 directory plugin 从不同启动目录运行时仍引用同一份
随插件发布的 catalog。

### 只使用 qSid/qDes，明确跳过 emoji pack

解析时遍历 `packs[].emojis[]`。只有 `packName` 不等于精确值 `emoji 表情`、`qSid` 是非空
字符串、`qDes` 是非空字符串的条目才进入映射；`packName` 本身不成为 label。命中后使用
`qDes` 原字符串，不做斜杠删除、大小写转换或其他名称规范化。这样 numeric face ID 可获得
目录描述，而 emoji face ID 保持模型已能理解的 emoji 字符。

同一 `qSid` 的重复条目若 `qDes` 相同，可视为同一映射；若出现不同的非空 `qDes`，该 key
标记为 ambiguous 并从最终映射排除。采用回退而不是按 pack 顺序覆盖，避免目录顺序变化导致
同一个 face ID 的显示名称不确定。

### 回退在 placeholder 边界完成

face label 解析只改变 `[face:...]` 中的显示值，不改变 `FaceSegment.face_id`、`segments` 或
其他特征。缺失/空白 `face_id` 继续通过现有 placeholder 规则显示 `NOT SUPPORTED`；有值但
未映射的 ID 使用该 ID 原值。目录错误不应生成额外正文、关键词、Agent 指令或敏感诊断。

### 用合成输入覆盖数据和兼容边界

测试保留现有复合消息断言，并增加：已知 numeric ID 命中、`emoji 表情` pack 跳过、未知 ID
回退、缺失 ID 回退、坏 catalog/坏条目回退、重复相同描述和冲突描述处理。测试输入使用合成
ID、名称和正文；不把 catalog 的完整内容、真实响应或路径写入日志和 fixture。加载器应提供可
独立验证的纯解析入口，使坏数据测试不需要改写仓库中的 catalog 文件。

## Risks / Trade-offs

- [目录在部署中未被带上或格式被手工修改] → 加载失败时保留原 ID/`NOT SUPPORTED`，并在构建/协议 fixture 检查中确认 `milky/face_catalog.json` 被纳入插件目录。
- [目录包含同一 ID 的不同名称] → 将该 ID 标记为不确定并回退，不按隐含顺序选值；无冲突 key 仍继续可用。
- [预加载增加导入时读取和少量内存占用] → 只读取一次小型本地 JSON，使用冻结映射，避免每条消息重复解析。
- [qDes 带有前导 `/` 不符合未来的展示偏好] → 当前按目录原值固定契约；如需纯中文名，另行提出明确的格式变更，不在本 change 中隐式清理。

## Migration Plan

这是向后兼容的入站展示变更，不需要配置、数据库或远端协议迁移。将 catalog 与解析边界随
适配器发布；启动后已知非 emoji face 显示 `qDes`，目录不可用时仍显示旧 ID。回滚时移除
映射并恢复 `[face:<face_id>]` 即可，不影响历史 session、去重 key、出站消息或 Milky 服务端。

## Open Questions

无。`qDes` 原值、`emoji 表情` pack 的跳过规则以及冲突条目的回退行为已在本 change 中固定。
