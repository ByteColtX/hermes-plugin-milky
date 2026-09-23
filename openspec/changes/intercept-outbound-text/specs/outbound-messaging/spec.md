# Spec Delta

## ADDED Requirements

### Requirement: 普通文本出站支持精确拦截

Milky 普通文本出站 SHALL 支持按已登记的完整文本值执行精确拦截。只有出站文本与某条登记值逐字符相等时才能拦截；系统 MUST NOT 对子串、前缀、相似文本或仅经过空白/标点变更的文本进行拦截。命中时 MUST 在任何 Milky 消息 Action 前终止该次发送，且不得让 Hermes 重试这条被过滤的回复；不得为未发生的远端发送伪造 message ID。未命中的普通文本及媒体、文件出站 MUST 保持既有行为。由于 Hermes Gateway 按 `SendResult.success` 决定投递 obligation 状态，过滤结果可能被 Gateway 记为 delivered，即使没有 Milky Action 或远端 message ID。

#### Scenario: 完整匹配 silence-marker 兜底文案

- **WHEN** 普通文本出站内容完整等于 `⚠️ The model returned only a silence marker for a message that needed a reply. Try again or rephrase.`
- **THEN** 系统 SHALL 在网络访问前拦截该文本且不调用 Milky 消息 Action
- **AND** SHALL 以终止处理结果结束发送，不触发该回复的自动重试
- **AND** SHALL 不返回伪造的远端 message ID

#### Scenario: 较长消息包含完整兜底文案

- **WHEN** 普通文本出站内容在兜底文案前后还包含其他字符
- **THEN** 系统 SHALL 不拦截该较长消息
- **AND** SHALL 按既有规则继续处理该消息

#### Scenario: 文案存在细微差异

- **WHEN** 普通文本与已登记文案存在空白、标点、大小写或其他字符差异
- **THEN** 系统 SHALL 不把该文本视为精确匹配
- **AND** SHALL 按既有规则继续处理该消息

#### Scenario: 媒体和文件出站不受文本拦截影响

- **WHEN** 出站调用使用媒体或文件专用入口
- **THEN** 系统 SHALL 不将该调用送入普通文本精确拦截
- **AND** SHALL 保持既有媒体或文件处理语义
