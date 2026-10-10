# Design

## Context

当前出站 CQ parser 对每个参数只按第一个 `=` 分隔；解析失败时，formatter 将当前完整 CQ
字符串保留为 text。CQ 分段器也复用该完整性判断来决定 `[SPLIT]` 是否位于受保护的 CQ 候选中。
现有 registry 只为已确认的 `text`、`face`、`image`、`record`、`video`、`at` 和 `reply`
提供 native converter，其余登记类型和未知扩展均按原文 fallback。

## Goals / Non-Goals

**Goals:**

- 仅在 `reply`、`at`、`face` 的 parser 边界接受 ASCII `=` 或 `:` 作为参数字段的首个分隔符，支持三类控制码内部混用两种写法。
- 将三类兼容写法规范化后交给现有字段集合、重复键、ID 和 segment 校验；其他类型继续沿用 `=`-only 解析。
- 保持其他合法 CQ 类型和未知扩展的原文 fallback，不因冒号兼容扩大 native 能力。
- 保持 `=` 为 platform guidance、QQ reference skill、fixture 和文档中的 canonical 写法。
- 保持 ID 是否来自当前消息或 `channel_context` 的判断属于 Agent-facing 指引，不在出站 parser 中伪造来源证明。

**Non-Goals:**

- 不新增任何 Milky native segment、Action、ToolSpec、CQ 类型或未确认字段映射。
- 不接受全角冒号、空白键名、缺少值、重复键、方括号值或其他现有 malformed 形式。
- 不改变入站 CQ/segment 解析、媒体下载、文件上传、目标路由或 Hermes core 行为。
- 不把 `:` 兼容写法写入 Agent 指引作为推荐输出格式。
- 不新增 sender metadata、reply context 或跨边界的 ID 来源校验。

## Decisions

### 仅在三类 CQ 的字段解析层提供兼容分隔符

先解析 CQ 类型名称；仅当名称为 `reply`、`at` 或 `face` 时，每个逗号分隔字段才查找其中最先
出现的 ASCII `=` 或 `:`，以该位置作为唯一字段分隔符。分隔符两侧都必须得到同一合法键名和非空
字段结构，随后共用重复键检查、实体解码和 converter。这样 `[CQ:reply,id:29568]`、
`[CQ:at,qq:10001]` 和 `[CQ:face,id:14,large:1]` 无需维护逐字段 alias 表；其他类型仍只按
`=` 分隔，`[CQ:image,file:https://...]`、未知扩展和其他冒号写法继续进入原文 fallback。

选择字段层而非全文替换，是为了保留三类兼容字段值中的后续冒号或等号；例如
`id:12=tail` 仍以首个 `:` 分隔，再交给既有数值校验。键名不会被隐式改写，找不到分隔符或键名
不合法的输入仍进入原文 fallback。媒体 URI 的冒号兼容不在本 change 范围内。

### 保持转换注册表作为能力闸门

参数规范化只改变三类控制码的语法入口。已有 converter 继续决定是否生成 Milky segment，converter
缺失或抛出转换错误时仍只回退当前原始 CQ 文本，不调用额外 Action、不重试、不改变其他消息片段。

### 让完整性判断复用同一 parser

分段逻辑继续以规范化 parser 的成功结果判定三类冒号参数 CQ 是否为完整候选；因此候选内部的
`[SPLIT]` 不触发分段，候选闭合后的 `[SPLIT]` 仍按既有规则处理。其他类型的冒号写法继续按
malformed 文本处理，普通长度分块仍保留其现有 CQ 边界策略。

### 规范文案与兼容入口分离

实现只移除 `PLATFORM_GUIDANCE` 中的 “Use `id=`, never `id:`.”，并保留 canonical
`[CQ:reply,id=<msg_seq>]`、`[CQ:at,qq=<uid>]` 文案。QQ reference skill 和脱敏 fixture
继续只展示 `=`，避免模型把容错拼写当作首选格式。当前 parser 不接收上下文 metadata，
因此只执行语法和数值边界校验；真实 ID 来源仍由 Agent-facing 指引和上游上下文负责。

## Risks / Trade-offs

- **[风险]** 三类控制码中更多带冒号的 CQ-like 文本会被视为完整候选，可能改变其中 `[SPLIT]` 的保护边界。→ **缓解：** 仅接受合法键和值结构，增加三类 native、malformed 和分段边界测试；转换能力仍由 registry 限制。
- **[风险]** Agent 的参数拼写错误可能意外触发已有 `reply`/`at`/`face` native 入口。→ **缓解：** 继续执行现有 ID、字段和数值边界；其他类型保持 `=`-only，canonical 文案仍只使用 `=`。

## Migration Plan

这是纯 parser 和提示文案兼容变更，不需要配置、数据库、Milky wire protocol 或远端迁移。实现时
先更新 parser、CQ 分段边界测试和 prompt 快照，再运行聚焦 CQ/分段/出站测试及项目质量门禁。若需
回滚，恢复 `=`-only parser 和原 prompt 行即可；既有 canonical 输出无需转换。
