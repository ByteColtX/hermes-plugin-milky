# hermes-message-pipeline Specification

## MODIFIED Requirements

### Requirement: friend 和 group 映射到明确 MessageEvent

正常 friend 消息 MUST 映射为 private message，正常 group 消息 MUST 映射为 group message，并保留 sender ID/name、Milky message ID 字符串、`source=milky`、正文、raw、timestamp、reply、已 materialize 的附件路径/MIME、channel_context 和安全 metadata。对于同一次 trigger，`MessageEvent.media_urls`/`media_types` MUST 将 `channel_context` 中历史消息的已 materialize 直接图片与当前 trigger 消息和可见 reply 内容的已 materialize 图片按规定顺序合并；相同图片 bytes 只保留当前 batch 中首次出现的代表，hash 不可用时仅按本地路径去重。历史图片按上下文顺序在前，当前图片按当前消息顺序在后，并同步维护两字段一一对应。原始 `media_resource_references` 与 `file_attachment_references` 不得直接写入 `MessageEvent.media_urls`。

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
- **THEN** `MessageEvent.media_urls` SHALL 先包含历史图片代表，再包含当前图片代表
- **AND** `MessageEvent.media_types` SHALL 与 `media_urls` 按相同顺序逐项对应
- **AND** 当前消息 SHALL 仍只作为正文，历史消息 SHALL 仍只作为 `channel_context`

#### Scenario: 历史和当前图片路径重复

- **WHEN** 历史图片与当前图片的 materialized 本地路径不同但文件内容相同
- **THEN** `MessageEvent.media_urls` SHALL 只保留历史 occurrence 的首次代表路径
- **AND** 当前正文中对应的 image placeholder SHALL 使用历史代表 basename
- **AND** `MessageEvent.media_types` SHALL 保留历史代表首次出现时的 MIME 且不产生孤立项

#### Scenario: hash 不可用时不推断图片相同

- **WHEN** 两个不同本地路径的 image materialization 无法安全计算 hash
- **THEN** 两个路径 SHALL 不因 resource_id、URL、summary 或文件名相似而合并
- **AND** 系统 SHALL 仅执行既有的 exact path 去重

#### Scenario: 历史图片未 materialize

- **WHEN** 历史图片未通过 Hermes helper 生成有效本地路径
- **THEN** 该图片 SHALL 不进入 `MessageEvent.media_urls`
- **AND** MessageEvent SHALL 保留历史 `channel_context` 的可解释失败占位

#### Scenario: 历史非图片附件不被误提升

- **WHEN** 历史上下文包含音频、视频、文件或未知引用，但没有对应成功的图片 materialization
- **THEN** 这些历史引用 SHALL NOT 因为存在于 `channel_context` 而被追加为历史图片媒体
- **AND** 当前消息已有的受支持附件映射 SHALL 保持既有行为

### Requirement: Agent-facing 文本区分历史上下文和当前消息

当存在 detached 历史时，适配器 MUST 将历史紧凑记录只放入 `MessageEvent.channel_context`，并使用资源解析及 batch 内容去重完成后的历史正文；当前 trigger 消息 MUST 以同一紧凑 header 格式放入 `MessageEvent.text`，并使用与其媒体代表一致的图片 basename。适配器 MUST NOT 把 `[New message]` 标记或当前消息复制到 `channel_context`；Hermes 已有的 Agent 输入组装语义负责在历史块和当前消息之间加入该标记。没有历史时，适配器 MUST 保持 `channel_context=None`，并只交付当前消息正文。

#### Scenario: Agent 收到历史和当前消息

- **WHEN** 两条历史消息后收到一条当前 trigger 消息，且历史中有重复内容图片
- **THEN** `channel_context` SHALL 仅为按顺序渲染的历史记录块，并引用首次代表 basename
- **AND** `text` SHALL 仅为当前消息记录，并引用 batch 选择的图片代表 basename
- **AND** Hermes 的有效 Agent 输入 SHALL 在历史块后以空行和 `[New message]` 分隔当前消息
- **AND** 当前消息 SHALL 不出现在 `channel_context`

#### Scenario: 没有历史时交付当前消息

- **WHEN** trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** `text` SHALL 仍使用当前消息的紧凑 header 和规范化正文
- **AND** 适配器 SHALL 不伪造历史标题或空的上下文 block

## ADDED Requirements

### Requirement: batch 内容去重后的正文和媒体引用必须一致

一次 trigger 映射 MUST 使用同一份 batch 内容代表结果生成历史正文、当前正文、`channel_context`、`media_urls` 和 `media_types`。任何成功 image occurrence 的 placeholder 不得引用未进入媒体输入且没有保守降级依据的随机 helper basename；相同内容的 occurrence 可以继续出现在正文和历史上下文中，但 MUST 全部引用同一个代表 basename。

#### Scenario: 相同图片保留多个正文 occurrence

- **WHEN** 历史和当前正文各出现一次内容相同的图片
- **THEN** 两处正文 SHALL 都保留各自原始 occurrence 的位置
- **AND** 两处 placeholder SHALL 使用同一个首次代表 basename
- **AND** `media_urls` SHALL 只包含该代表一次

#### Scenario: channel_context 从最终正文重建

- **WHEN** resolver 完成图片内容代表选择后生成历史上下文
- **THEN** `channel_context` SHALL 从已经改写的历史 `ResolvedMessage.body` 渲染
- **AND** SHALL NOT 从 canonical 临时正文或未改写 helper 路径重新生成
- **AND** `media_urls` 与 `media_types` SHALL 与该上下文中的可见图片代表保持同一顺序和 identity

#### Scenario: 失败和未知 hash 不泄露路径

- **WHEN** 图片 hash 失败或 helper 未返回可用 materialization
- **THEN** 正文和诊断 SHALL 只保留安全 basename、失败 placeholder 或固定分类
- **AND** SHALL NOT 写入远端 URL、完整本地路径、文件内容或异常正文
