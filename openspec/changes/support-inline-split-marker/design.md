## Context

当前普通文本在出站 formatter 前经过独立的 [SPLIT] 行解析；命中后再沿用逻辑段合并、CQ-compatible formatter、文本长度分块和三条消息预检。没有有效标记的普通长文本继续使用既有无限制分块。该 change 只扩展出站文本控制语法，不改变 Hermes core、Milky Action、ToolSpec、入站 pipeline 或媒体交接。

## Goals / Non-Goals

**Goals:**

- 让未转义、大小写严格匹配的 [SPLIT] 可以出现在普通正文行中。
- 保留现有独立行的空白边界、最多三条文本消息、长度预检、按序投递和部分失败结果。
- 让 Agent 能以 [[SPLIT]] 发送可见字面量 [SPLIT]。
- 保持语法完整的 CQ-compatible、未知 type CQ 内容的原有结构化转换或原始文本 fallback；malformed CQ-like 内容按普通文本边界处理，不让未闭合候选吞掉后续 `[SPLIT]`。
- 让普通换行、行中标记两侧空白、MEDIA: 提取和文本先于附件的交接保持可预测。

**Non-Goals:**

- 不修改 [SILENT]、MEDIA:、CQ-compatible 语法的其他部分或 Hermes core。
- 不支持文本段和附件交错，不把附件计入文本三条上限。
- 不新增配置、HTTP Action、ToolSpec、重试、限流器或按聊天发送锁。
- 不把大小写变体、只有空白包围的标记行或语法完整 CQ-compatible 候选中的标记解释为控制语法；malformed CQ-like 内容不享受该保护。

## Decisions

### 1. 在现有出站文本边界扩展解析，而不是新增发送通道

在既有文本分段解析边界识别独立行和普通正文行中的有效标记；命中后继续复用当前逻辑段整理、formatter、长度分块和发送循环。这样不会复制目标路由、CQ 转换、媒体 materialization 或 SendResult 语义。

候选方案是让 Hermes core 先拆分回复。该方案会扩大跨仓库契约，并使 Milky-specific 控制语法脱离 plugin 的出站安全边界，因此不采用。

### 2. 使用受保护扫描，不使用简单 substring split

解析器按原始文本顺序扫描，区分三类内容：

1. 未转义且位于普通正文中的 [SPLIT]：形成分隔点；
2. [[SPLIT]]：还原为可见的 [SPLIT]，不形成分隔点；
3. 以 [CQ: 开始且通过基础语法校验的完整 CQ-compatible 候选：候选范围内的 [SPLIT] 不参与分段，随后交给既有 CQ-compatible formatter 或 raw fallback；找不到闭合括号或基础语法校验失败的 malformed 候选不受保护。

只有完整独立行的 [SPLIT] 才使用现有标记行边界规则；普通正文行中的标记只删除自身，不删除相邻普通空白、换行或其他文本。标记所在行除标记外没有非空白字符时，仍按当前普通文本处理，以保留带前后空白的旧边界行为。

候选方案是先调用 formatter 再在 text segment 中寻找标记。该方案不能可靠区分未知 type fallback 与 malformed 原文，也会让控制语法依赖 segment 合并方式，因此不采用。另一个简单方案是直接调用字符串 split；该方案会破坏完整 CQ-compatible 内容、转义语法和现有行边界规则，因此不采用。

完整 CQ 候选的边界和基础语法复用现有 `parse_cq_code` 契约：未知 type 只要外壳和参数语法完整，仍按 fallback 作为一个 CQ 候选保护；参数包含原始方括号、缺少闭合方括号或其他基础语法错误时，候选视为 malformed，内部 `[SPLIT]` 回到普通控制语法。这样不会把协议不存在的“CQ 内嵌 `[SPLIT]`”当作真实能力，也不会因为普通文本中的未闭合 `[CQ:` 阻止后续分段。

### 3. 把“是否存在有效控制标记”和“文本是否需要字面量归一化”分开

解析结果需要同时表达归一化后的文本和是否命中有效分段标记。只有命中有效控制标记时才进入三条消息上限和分段专用预检；只有 [[SPLIT]] 而没有有效标记时，归一化后的普通文本仍使用原有长文本分块，不被错误限制为三条。

该边界保持“转义只是正文归一化，不是分段控制”的可观察语义，也避免字面量用法意外改变普通长文本的发送上限。

### 4. 复用现有原子性和附件交接

解析与全部长度/格式预检仍在首个消息 Action 前完成。命中有效行中标记后，文本单元按原顺序串行发送；中途失败继续保留已成功消息 ID、失败分类和停止后续单元的既有结果。Hermes 独立提取的 MEDIA: 附件仍在文本完成后按提取顺序投递，plugin 不从 MEDIA: 在正文中的位置推断交错顺序。

## Risks / Trade-offs

- [旧正文中的行中 [SPLIT] 变成控制语法] → 将该行为标为 BREAKING，并在 Agent 指引和 README 中说明；需要发送字面量时使用 [[SPLIT]]。
- [CQ-like 内容保护范围过宽] → 只保护通过基础语法校验的完整 CQ 候选；未知 type 继续 fallback，malformed 或未闭合候选按普通文本处理，增加合法未知 CQ、malformed 有闭合括号和未闭合 CQ fixture。
- [行中标记导致更多消息 Action、限流或部分成功] → 复用现有最多三条、首个 Action 前预检、串行发送和不盲目重试语义。
- [转义语法本身被旧客户端当作普通文本] → 该 change 只影响安装了新 plugin 的出站边界；文案和测试明确新旧行为差异，回滚不需要远端数据迁移。
- [fixture 或日志包含敏感正文] → 使用合成文本、合成 CQ ID 和脱敏 URI；不把 token、Authorization、真实 QQ、媒体 URL、路径或完整远端响应写入证据。

## Migration Plan

1. 先扩展脱敏 fixture 和 parser/sender 契约测试，覆盖独立行、行中、连续/空段、大小写、空白、[[SPLIT]]、完整 CQ 候选与 malformed CQ 的边界和长文本预检。
2. 在现有出站文本路径中复用 CQ 基础语法校验实现受保护解析和“有效控制标记”状态传递，保持普通长文本与既有媒体入口回归通过。
3. 更新根入口平台指引、system prompt、ARCHITECTURE.md 和 README.md，说明行中用法、字面量转义和不变的媒体顺序。
4. 运行聚焦测试、完整 pytest、Ruff、format、build、diff 检查和严格 OpenSpec 校验；未经明确授权不执行真实 Milky 写入 smoke。
5. 回滚时移除行中解析、字面量归一化和对应文案/契约即可，不涉及配置迁移、远端数据或 Hermes core。

## Open Questions

无。行中标记的触发范围、字面量形式、完整 CQ 候选保护、malformed CQ 处理、空白处理、三条上限和附件顺序已在 proposal 与 delta specs 中固定。
