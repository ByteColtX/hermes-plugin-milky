# Spec Delta

## ADDED Requirements

### Requirement: 历史图片必须可归属到来源消息

历史上下文正文含 image placeholder 且该消息有稳定 `message_seq` 时，renderer SHALL 在该条历史
记录正文之后追加独立的 `[images_from_msg_seq=<message_seq>]` 行。该行 MUST 只使用消息自身的
`message_seq`，不得使用 sender、文件名、URL 或猜测值；没有 image placeholder 或
`message_seq` 缺失时 MUST NOT 追加。该标记 MUST NOT 改变 image placeholder 语法，也 MUST NOT
改变 `media_urls` 的既有顺序与去重语义。

#### Scenario: 历史图片带来源序号

- **WHEN** 一条历史消息含 image placeholder 且具有稳定 `message_seq`
- **THEN** 该历史记录正文之后 SHALL 追加 `[images_from_msg_seq=<message_seq>]`
- **AND** 正文中既有的 `[img:file_name=...]` placeholder 语法 SHALL 保持不变

#### Scenario: 无图片来源标记

- **WHEN** 历史消息不含 image placeholder，或该消息没有稳定 `message_seq`
- **THEN** 正文 SHALL NOT 追加 `images_from_msg_seq` 标记
- **AND** SHALL 不因此伪造消息序号
