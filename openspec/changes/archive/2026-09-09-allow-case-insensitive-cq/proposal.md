## Why

当前出站 CQ 解析只接受字面量 `[CQ:` 前缀，而 Hermes/Agent 可能产生小写或混合大小写的
`[cq:...]` 控制码，导致原本可转换的 `at`、`reply` 和媒体控制码被当成普通文本发送。
CQ 前缀不承载语义，允许大小写变体可以消除这类兼容性差异，同时不扩大已确认的 CQ 类型或
Milky segment 映射范围。

## What Changes

- CQ-compatible 控制码的前缀 `CQ` 改为大小写不敏感，至少支持 `[CQ:...]`、`[cq:...]` 和
  `[Cq:...]`。
- 所有使用 CQ 候选边界的出站路径统一采用相同的大小写不敏感识别规则，包括普通 segment
  转换和 `[SPLIT]` 边界保护。
- 可转换的 CQ 类型继续使用既有 Milky segment 映射；未知、格式错误、字段非法或转换失败的
  控制码继续保留完整原始字符串作为 text fallback，原始大小写不得被改写。
- 补充大小写变体的 formatter、sender 和分段回归测试，并更新 Agent-facing 指引与 CQ
  reference 文档。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `outbound-messaging`: 出站 CQ-compatible 控制码的识别前缀不再区分大小写，同时保持既有
  类型映射、顺序和安全 fallback 契约。
- `agent-facing-message-controls`: Agent 生成的 CQ-compatible 控制码允许使用任意大小写
  的 `CQ` 前缀，并继续受真实 ID 和已确认能力约束。
- `outbound-message-splitting`: CQ 候选边界保护必须与普通出站 CQ 解析保持一致，大小写变体
  的完整 CQ 控制码不得误吞其中或后续的 `[SPLIT]` 标记。

## Impact

- 主要影响 `outbound/formatter.py`、`outbound/splitting.py` 及其测试。
- 需要更新 `__init__.py` 中的平台提示和 `skills/milky-qq-cq-reference/SKILL.md` 的语法
  说明；不新增 Milky Action、ToolSpec、网络请求或配置项。
- 需要修改对应的 OpenSpec delta spec；现有大写 CQ、未知 CQ、malformed CQ 和普通文本行为
  应保持兼容。
