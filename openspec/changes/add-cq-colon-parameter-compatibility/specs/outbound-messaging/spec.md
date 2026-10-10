# Spec Delta

## ADDED Requirements

### Requirement: reply at face 参数分隔符兼容解析

出站 `reply`、`at`、`face` CQ-compatible 控制码 MUST 将每个参数中最先出现的 ASCII `=` 或 `:` 视为字段分隔符，并在后续字段校验前将 `key=value` 与 `key:value` 规范化为同一参数键值。参数可在同一控制码内混用两种写法；键名、重复键、空值、方括号、ID 范围和既有 converter 规则保持不变，分隔符之后的字符 SHALL 保留为 value。其他 CQ 类型 MUST 继续只按 `=` 分隔；它们的 `key:value` 写法 SHALL 按既有 malformed/fallback 处理。

#### Scenario: reply at face 使用冒号写法

- **WHEN** Agent 提供 `reply`、`at` 或 `face` 控制码，且一个或多个参数使用 `:` 分隔
- **THEN** 系统 SHALL 按对应 `=` 写法执行同一字段校验并生成同一 Milky native segment
- **AND** SHALL 保留控制码在消息中的原始相对顺序

#### Scenario: reply at face 参数混用两种分隔符

- **WHEN** 一个合法 `reply`、`at` 或 `face` 控制码同时包含 `key=value` 和 `key:value` 参数
- **THEN** 系统 SHALL 逐字段规范化并继续执行既有字段集合和重复键校验
- **AND** 参数值中分隔符之后的其他字符 SHALL 保持为该字段值

#### Scenario: 兼容字段值保留后续分隔符

- **WHEN** `reply`、`at` 或 `face` 的 `key:` 写法 value 中还包含 `:` 或 `=`
- **THEN** 系统 SHALL 使用字段键之后最先出现的 `=` 或 `:` 作为分隔符
- **AND** SHALL 将 value 中后续的 `:` 和 `=` 完整保留，并继续执行既有字段或数值校验

#### Scenario: 其他 CQ 类型不开放冒号写法

- **WHEN** `text`、`image`、`record`、`video` 或未知 CQ 扩展使用 `key:` 参数写法
- **THEN** 系统 SHALL 将完整原始 CQ 字符串作为单个 text segment 保留
- **AND** SHALL 不因兼容解析调用额外的 Milky segment、Action 或 Tool

#### Scenario: 兼容写法的字段或 ID 非法

- **WHEN** 使用 `key:` 的 `reply`、`at` 或 `face` 控制码包含缺少值、非法键、重复键、非法 ID、前导零 ID、越界 ID 或不支持字段
- **THEN** 系统 SHALL 将完整原始 CQ 字符串作为 text segment 保留
- **AND** SHALL 继续处理同一消息中的其他文本和 CQ 内容，不触发第二次发送

#### Scenario: 三类冒号 CQ 候选与分段边界

- **WHEN** 语法完整的 `reply`、`at` 或 `face` 冒号参数 CQ 控制码后紧邻未转义 `[SPLIT]`
- **THEN** 系统 SHALL 在 CQ 候选闭合后识别 `[SPLIT]` 的既有控制语义
- **AND** SHALL 保留该 CQ 的 native 转换或完整原文 fallback
