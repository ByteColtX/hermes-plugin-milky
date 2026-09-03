## MODIFIED Requirements

### Requirement: friend 和 group 映射到明确 MessageEvent

正常 friend 消息 MUST 映射为 private message，正常 group 消息 MUST 映射为 group message，并保留 sender ID/name、Milky message ID 字符串、`source=milky`、正文、raw、timestamp、reply、已 materialize 的附件路径/MIME、channel_context 和安全 metadata。对于同一次 trigger，`MessageEvent.media_urls`/`media_types` MUST 将 `channel_context` 中历史消息的已 materialize 图片与当前 trigger 消息的已 materialize 图片合并；历史图片按上下文顺序在前，当前图片按当前消息顺序在后，并按本地路径去重且保持两字段一一对应。原始 `media_resource_references` 与 `file_attachment_references` 不得直接写入 `MessageEvent.media_urls`。

#### Scenario: friend 消息交接

- **WHEN** 合法 friend 消息通过 Gate 并被 Will trigger
- **THEN** Hermes SHALL 收到 private MessageEvent
- **AND** event 的 source SHALL 为 `milky`
- **AND** message ID SHALL 使用 Milky ID 字符串

#### Scenario: group 消息交接

- **WHEN** 合法 group 消息通过 Gate 并被 Will trigger
- **THEN** Hermes SHALL 收到 group MessageEvent
- **AND** event SHALL 保留 group chat key、发送者身份和 mention/quote metadata

#### Scenario: 历史图片和当前图片按顺序交给 Hermes

- **WHEN** 一个 trigger batch 包含按上下文顺序排列的两张历史图片，以及当前消息中按 segment 顺序排列的两张图片
- **THEN** `MessageEvent.media_urls` SHALL 先包含历史两张图片，再包含当前两张图片
- **AND** `MessageEvent.media_types` SHALL 与 `media_urls` 按相同顺序逐项对应
- **AND** 当前消息 SHALL 仍只作为正文，历史消息 SHALL 仍只作为 `channel_context`

#### Scenario: 历史和当前图片路径重复

- **WHEN** 历史图片与当前图片的 materialized 本地路径有重复
- **THEN** `MessageEvent.media_urls` SHALL 只保留每个重复路径的首次出现
- **AND** `MessageEvent.media_types` SHALL 不产生孤立或重复的类型项

#### Scenario: 历史图片未 materialize

- **WHEN** 历史图片未通过 Hermes helper 生成有效本地路径
- **THEN** 该图片 SHALL 不进入 `MessageEvent.media_urls`
- **AND** MessageEvent SHALL 保留历史 `channel_context` 的可解释失败占位

#### Scenario: 历史非图片附件不被误提升

- **WHEN** 历史上下文包含音频、视频、文件或未知引用，但没有对应成功的图片 materialization
- **THEN** 这些历史引用 SHALL NOT 因为存在于 `channel_context` 而被追加为历史图片媒体
- **AND** 当前消息已有的受支持附件映射 SHALL 保持既有行为
