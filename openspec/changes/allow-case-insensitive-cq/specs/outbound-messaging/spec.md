## ADDED Requirements

### Requirement: CQ 前缀大小写不敏感

出站文本中的 CQ-compatible 控制码 MUST 识别大小写不敏感的 `CQ` 前缀，包括 `[CQ:...]`、
`[cq:...]` 和其他大小写变体；该大小写规则只适用于前缀，不得扩大已确认的 CQ 类型、字段或
Milky segment 映射。Hermes 提供含有可确认转换的 `at`、`reply` 或仅用于 sticker 的 image
CQ-compatible 控制码时，请求 body MUST 包含对应的 Milky mention、reply 或 image segment，
且 CQ-compatible 控制码本身 SHALL 不作为普通文本发送。

#### Scenario: 大小写变体的 CQ 控制码转换为 native segment

- **WHEN** Hermes 提供含有可确认转换的 `at`、`reply` 或仅用于 sticker 的 image CQ-compatible
  控制码，且 `CQ` 前缀使用任意大小写
- **THEN** 请求 body SHALL 包含对应的 Milky mention、reply 或 image segment
- **AND** CQ-compatible 控制码本身 SHALL 不作为普通文本发送

#### Scenario: CQ 控制码顺序保持不变

- **WHEN** 一条出站文本按顺序包含多个大小写变体的 CQ-compatible 控制码和普通文本
- **THEN** 对应的 Milky segments SHALL 按原始相对顺序生成
- **AND** 系统 SHALL 不因 `CQ` 前缀大小写变化增加隐式 reply 或其他 segment

#### Scenario: 未知或转换失败的大小写变体保留原文

- **WHEN** 一个大小写变体的 CQ-compatible 控制码未知、字段非法或没有确认的 Milky 映射
- **THEN** 系统 SHALL 将完整原始 CQ 字符串作为 text segment 保留
- **AND** SHALL 保留该控制码的原始大小写和参数文本，不调用未确认的 Action
