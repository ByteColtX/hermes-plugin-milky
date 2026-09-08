## Context

当前出站路径有两个 CQ 识别边界：普通消息 formatter 解析控制码，以及 `[SPLIT]` parser
扫描完整 CQ 候选以保护其内部内容。前者只接受字面量 `[CQ:`，后者也只搜索该大写前缀，导致
小写或混合大小写前缀无法转换，并可能使 `[SPLIT]` 在大小写变体 CQ 候选中被错误解释。
具体动机见 `proposal.md`，目标行为见本 change 的三个 delta spec。

## Goals / Non-Goals

**Goals:**

- 让 `CQ` 前缀的大小写变体共用现有解析、转换、分块和 fallback 语义。
- 让 formatter 与 `[SPLIT]` 边界扫描使用一致的 CQ 候选识别规则。
- 保留 fallback 原文的字节级内容，包括前缀大小写、参数顺序和参数文本。
- 用脱敏测试覆盖大小写变体、混合正文、未知/非法 CQ 和完整/损坏 CQ 中的 `[SPLIT]`。

**Non-Goals:**

- 不扩大已确认支持的 CQ 类型或 Milky outgoing segment 映射。
- 不让 CQ 类型名、字段名或字段值变为大小写不敏感；本 change 只放宽 `CQ` 前缀。
- 不新增 Action、ToolSpec、配置项、网络请求或媒体处理逻辑。
- 不改变 `[SPLIT]` 本身的大小写严格匹配规则。

## Decisions

### 1. 只在 CQ 前缀边界做大小写归一化

解析器 SHALL 仅对开头的 `[CQ:` 标记执行大小写不敏感比较，随后继续使用现有 type、参数键、
参数值和转换器校验。这样 `[CQ:AT,...]` 当前已有的 type 归一化行为不被重新设计，参数字段
的安全校验也不会因整串 lowercasing 而放宽。

候选扫描应使用同一套大小写不敏感的前缀定位规则，而不能先把整条正文转换成小写：后者会
破坏普通文本、CQ 参数值和 fallback 原文。保留原始 slice 交给解析和 fallback，只有解析得到
的 type 继续使用既有规范化结果。

### 2. formatter 和分段扫描共享 CQ 边界语义

普通 formatter 负责把完整候选转换为 native segment；分段扫描只负责识别完整候选范围并保护其
内部的 `[SPLIT]`。两者应共享同一个大小写不敏感的候选起点规则，并继续由完整语法解析结果
决定候选是否有效：未知 type 可以作为完整候选保护并按原文 fallback，缺少闭合括号、参数含
原始方括号或基础语法无效的内容不能获得保护。

这样可以保证大小写变体在普通发送和带 `[SPLIT]` 的发送中拥有同一解释，同时不把 malformed
CQ-like 文本误判为不可拆分区域。

### 3. 文档只声明兼容性，不伪造能力

平台提示和 `milky-qq-cq-reference` skill 增加“`CQ` 前缀大小写不敏感”的说明，但继续使用
现有的 at、reply、face 和 sticker 语法及真实 ID 约束。未知 CQ 仍只是原文 fallback，不因
大小写放宽而成为 Milky 原生能力。

### 4. 通过回归矩阵验证原始大小写和边界

测试应覆盖大写、小写和混合大小写前缀，至少验证 at、reply、未知 CQ、非法 CQ、多个控制码和
普通文本混排。分段测试应分别覆盖有效大小写变体 CQ 后的 `[SPLIT]`，以及未闭合/含方括号的
malformed 大小写变体 CQ。现有大写 fixture 必须继续通过。

## Risks / Trade-offs

- [风险] 原本想发送字面量 `[cq:...]` 的文本可能被识别为 CQ 控制码。→ 这是本 change 的
  明确兼容性目标；未知或转换失败的控制码仍原样发送，已确认类型则遵守既有 CQ 语义。
- [风险] formatter 和分段扫描若各自维护大小写逻辑会再次产生边界漂移。→ 使用同一候选
  定位/解析语义，并增加跨 formatter、sender 和 split 的回归测试。
- [风险] 对 malformed CQ-like 文本放宽搜索可能改变 `[SPLIT]` 的拆分结果。→ 只有完整解析的
  候选才受保护；损坏候选继续按普通文本规则处理，并保留原有 malformed 测试。

## Migration Plan

1. 先更新 delta spec、实现、测试和 Agent-facing 文档，再运行聚焦测试与完整质量门禁。
2. 发布后无需迁移配置、持久化数据或远端协议；旧版仍可回滚到仅识别大写前缀的行为。
3. 回滚时恢复对应代码和文档版本，不需要发送补偿消息或调用额外 Milky Action。
