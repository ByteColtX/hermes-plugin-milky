# Spec Delta

## ADDED Requirements

### Requirement: CQ 规范文案继续使用等号

Milky platform guidance 和 QQ reference skill MUST 继续以 `key=value` 展示 CQ-compatible 规范写法，并 MUST 保留 `[CQ:at,qq=<uid>]`、`[CQ:reply,id=<message_seq>]` 等 canonical 示例。文案不得要求 Agent 使用 `key:`，兼容解析属于出站边界行为，不扩大 Agent 可调用的 ToolSpec 或 native CQ 映射；ID 来源约束仍由 Agent-facing 上下文指引负责，出站 parser 只执行语法和数值边界校验。

#### Scenario: platform guidance 保留 canonical CQ 示例

- **WHEN** Hermes 为 Milky 会话渲染平台操作指引
- **THEN** 指引 SHALL 继续展示 `[CQ:at,qq=<uid>]` 和 `[CQ:reply,id=<msg_seq>]` 的等号写法
- **AND** 指引 SHALL 不包含 “Use `id=`, never `id:`.” 这条负面禁用文案

#### Scenario: QQ reference skill 保留 canonical CQ 示例

- **WHEN** Agent 按需读取 Milky QQ CQ reference skill
- **THEN** `at`、`reply`、`face` 和 sticker image 示例 SHALL 继续使用 `=` 参数分隔符
- **AND** skill SHALL 不把 `:` 兼容写法描述为 Agent 的规范输出格式

#### Scenario: 三类兼容写法不改变真实 ID 指引

- **WHEN** 当前消息和 `channel_context` 没有可靠的消息序号或用户 UID
- **THEN** platform guidance 和 QQ reference skill SHALL 继续要求 Agent 省略对应的 `reply` 或 `at` 控制码
- **AND** 若 Agent 仍提交带数字的 `reply,id:` 或 `at,qq:`，出站 parser SHALL 只按既有语法、字段和数值范围校验处理，不得声称已验证其上下文来源或从其他字段推断目标
- **AND** `face,id:`/`face,large:` 只改变字段分隔符，仍沿用现有字段和值校验，不新增上下文来源证明
