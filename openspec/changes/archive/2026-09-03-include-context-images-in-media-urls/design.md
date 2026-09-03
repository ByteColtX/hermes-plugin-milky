## Context

当前资源 resolver 会在 detached trigger batch 中分别完成历史消息和当前消息的资源处理；历史
正文随后被渲染为 `channel_context`。但 Hermes mapper 只从当前消息的 resolved 结果构造
`media_urls`，没有携带历史消息的图片 materialization，因此 Agent 只能看到历史图片的
占位文本。

本 change 必须保持 Hermes 对远端 URL、下载、缓存、SSRF、权限和本地路径的所有权。只有
Hermes helper 返回并通过现有本地路径校验的结果才能进入 MessageEvent；`channel_context` 是
展示文本，不应被反解析来寻找媒体路径。

## Goals / Non-Goals

**Goals:**

- 为同一次 MessageEvent 提供历史 context 可见图片和当前 trigger 图片的统一有序媒体输入。
- 保留历史图片在 context 中的消息/segment 顺序，再接当前 trigger 的既有 materialization 顺序。
- 以本地路径为稳定去重键，保留首次出现的路径和 MIME，保证 `media_urls` 与 `media_types` 等长。
- 让历史图片资源失败、未确认或非图片附件继续遵循现有降级和安全边界。

**Non-Goals:**

- 不把历史音频、视频、文件、未知引用或未在 `channel_context` 展示的嵌套引用提升为历史图片。
- 不改变当前 trigger 已有的音频、视频和其他已确认附件映射行为。
- 不解析 `channel_context` 字符串，不创建新的媒体缓存、下载逻辑或 Hermes core seam。
- 不修改 Milky 协议、Gate/Will、wait buffer、消息正文或 Agent busy/follow-up 语义。

## Decisions

### 1. 在结构化 resolved 结果中传递历史图片

历史图片应从 resolver 的结构化结果传递给 mapper，而不是从 `channel_context` 的文本占位符
反推路径。解析每条消息时记录其直接正文中实际展示的成功图片 materialization；历史 batch
只使用这些记录，避免把 reply 等未出现在历史正文中的嵌套图片误加入媒体输入。

备选方案是让 mapper 扫描 `[img:file_name=...]` 文本或让 Hermes 从上下文自行解析，这会把
展示格式与本地路径耦合，也可能误认不可信文本，因此不采用。

### 2. 在 mapper 边界完成单一有序合并

合并输入固定为：历史消息的 context-visible 图片（按历史消息和 segment 顺序），随后当前
消息的既有 materialization（保留当前图片及其他已支持附件的原顺序）。只对有效本地路径
建立首次出现集合；重复路径不再追加，同时沿用首次出现项的 MIME。这样历史图片位于当前
trigger 图片之前，`media_types` 仍可按索引与 `media_urls` 对齐。

备选方案是由 resolver 全局合并或以 URL 去重。前者会让资源层承担 MessageEvent 组装职责，
后者无法识别 helper 已生成的本地路径且可能泄露远端引用，均不采用。

### 3. 保持当前附件兼容并限制新增输入

当前 resolved 消息的既有附件集合继续交给 mapper；新增的只有历史 context-visible 图片。
历史 materialization 不直接覆盖当前附件，也不改变当前 `message_type` 判定。没有有效本地
materialization 的历史图片不进入 `media_urls`，其 context 正文和安全诊断仍由既有 resolver
处理。

### 4. 以测试固定顺序、去重和失败边界

新增脱敏 pipeline fixture 覆盖两条历史图片、两条当前图片、跨历史/当前重复路径、当前非图片
附件、helper 失败和无历史图片等组合；断言事件的 `media_urls`、`media_types`、
`channel_context` 和正文同时成立。测试只使用合成本地路径，不记录远端 URL、凭证或真实媒体内容。

## Risks / Trade-offs

- [不同资源意外 materialize 到同一本地路径] → 按路径首次出现去重并保留首次 MIME，避免 Agent 重复读取；如 MIME 不一致，后续诊断仍由现有 materialization 校验负责。
- [resolver 未来改为并行处理后完成顺序漂移] → 合并逻辑使用 batch/segment 的显式顺序，不使用异步完成先后作为排序依据。
- [历史正文与历史媒体候选来源不一致] → 由 resolver 同时记录 context-visible 图片，禁止 mapper 解析文本；回归测试覆盖未展示的嵌套引用不被提升。
- [历史图片增加后单次 MessageEvent 媒体数量上升] → 仅纳入 context 中实际可见且已 materialize 的图片，并通过路径去重；不改变现有配置和 Hermes 限制。

## Migration Plan

1. 先补充脱敏 fixture 和 mapper/pipeline 回归，固定历史优先、当前随后、首次路径去重及 MIME 对齐。
2. 在 resolver 的结构化结果中提供 context-visible 图片集合，在 mapper 中合并并生成两组平行媒体字段。
3. 运行相关入站、资源和 Hermes pipeline 测试，再运行完整 pytest、Ruff、format、build、diff 和 OpenSpec strict 校验。
4. 若回滚，只移除历史图片集合的 MessageEvent 合并，保留当前附件路径和原有 context 文本；不涉及 Milky 远端状态迁移。
5. 只有自动化证据确认后，才考虑将本 change 的行为同步到主 specs；当前规划本身不代表能力已经交付。

## Open Questions

无。路径去重键、历史/当前顺序、失败降级以及当前非图片附件的兼容边界已固定在本 change 的 delta specs 中。
