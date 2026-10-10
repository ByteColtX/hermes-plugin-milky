# Proposal

## Why

Agent 输出 `reply`、`at` 或 `face` CQ-compatible 控制码时，偶尔会把参数分隔符 `=` 写成
`:`，例如 `[CQ:reply,id:29568]`。当前 parser 将这些控制码视为 malformed，随后把完整控制码
作为普通文本发送，导致本应形成的 native segment 没有生效。现有 prompt 和 QQ reference
skill 已经以 `=` 提供规范写法，但规范写法不能覆盖模型偶发的等价拼写错误。

## What Changes

- 仅在 `reply`、`at`、`face` CQ-compatible 控制码的参数解析边界接受字段中最先出现的 `=` 或 `:` 作为分隔符；规范化后的参数继续复用现有字段、ID、范围和重复键校验，并保留分隔符之后的全部值内容。
- 其他已登记类型和未知 CQ 扩展继续只接受 `=`；它们使用 `key:` 时保留完整原文 text fallback。三类兼容类型仍只有已有确认映射时才转换为 Milky native segment。
- 保持 `=` 为 Agent-facing prompt、QQ reference skill、fixture 和文档中的规范写法；不引导 Agent 使用 `:`。
- 从 `PLATFORM_GUIDANCE` 移除 “Use `id=`, never `id:`.”，保留 `[CQ:reply,id=<msg_seq>]` 的规范示例和真实 ID 来源约束。
- 保持 ID 来源约束属于 Agent-facing 指引；当前出站 parser 只负责 CQ 语法和数值边界校验，不新增上下文 metadata 传递或来源证明能力。
- 增加覆盖三类兼容类型的 mixed separator、非法值、重复键、其他类型冒号写法原文 fallback、CQ 顺序以及 `[SPLIT]` 候选边界的测试和证据。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `outbound-messaging`: CQ-compatible 参数的兼容解析和原文 fallback 行为发生变化。
- `agent-facing-message-controls`: Agent 可见 CQ 语法的容错边界扩大，但规范示例和 native 映射范围保持不变。

## Impact

- 影响出站 CQ parser、CQ 分段/分块候选边界及其单元测试；冒号兼容只对 `reply`、`at`、`face` 生效，不新增 Milky Action、ToolSpec、网络请求或资源权限。
- 影响 `__init__.py` 中渲染的 Milky platform guidance 文案；`skills/milky-qq-cq-reference/SKILL.md` 继续使用 `=` 作为规范写法。
- 需要同步脱敏 CQ fixture 与 OpenSpec delta，验证三类 native 类型、其他类型冒号写法的 fallback 和 malformed 输入仍遵守既有安全边界。
