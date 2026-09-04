# media-and-reply-resolution Specification

## MODIFIED Requirements

### Requirement: Hermes materialization 必须在 MessageEvent 映射前完成

resolver MUST 在 mapper 和 `handle_message()` 之前等待 detached batch 中历史消息与当前消息实际使用的异步 Hermes URL helper/materializer 完成。成功结果 SHALL 形成 Hermes 可访问的本地 materialization，包含本地路径、MIME 和 kind；历史上下文中实际展示的图片和当前 trigger 消息的图片均属于本次 Hermes 媒体输入候选。只有这些本地路径才可写入 `MessageEvent.media_urls`/`media_types`；未 materialize 的 Milky URL、`file_id` 或远端引用不得直接写入 `media_urls`。在 Hermes helper 成功返回本地图片路径之后，插件 MAY 仅为当前 trigger batch 的内容去重读取该图片文件并计算 SHA-256；该读取不得改变 Hermes 的下载、缓存、SSRF、权限或生命周期所有权。

#### Scenario: async URL helper

- **WHEN** image 或 record 的临时 URL 交给 Hermes async URL helper
- **THEN** resolver SHALL await helper 返回的本地路径后再构造 MessageEvent
- **AND** MessageEvent SHALL 只包含该本地路径及对应 MIME，不得包含未解析 URL

#### Scenario: 历史上下文图片与当前图片均完成 materialization

- **WHEN** detached batch 的历史消息和当前 trigger 消息都包含图片，且 Hermes helper 为这些图片返回有效本地路径
- **THEN** resolver SHALL 为历史消息和当前消息分别保留成功的图片 materialization
- **AND** 这些图片 SHALL 都可供同一次 MessageEvent 的 `media_urls` 使用
- **AND** 历史图片 SHALL 按其在 `channel_context` 中的顺序先于当前 trigger 图片

#### Scenario: 重复图片路径只保留一次

- **WHEN** 历史上下文图片和当前 trigger 图片的成功 materialization 使用相同本地路径
- **THEN** 同一次 MessageEvent 的媒体输入 SHALL 只保留该本地路径一次
- **AND** SHALL 保留该路径首次出现时的顺序和对应 MIME

#### Scenario: 文件没有确认的 materialization 入口

- **WHEN** 某种附件没有已确认的 Hermes 远端资源或文件 materialization 入口
- **THEN** 系统 SHALL 返回 `unsupported` 和可解释占位
- **AND** SHALL 不在插件中读取 bytes、创建路径或调用未确认的 bytes helper

#### Scenario: materialization 不支持

- **WHEN** 引用存在但当前 Hermes helper 不支持该 kind 或安全校验失败
- **THEN** mapper SHALL 保留结构化引用诊断并生成可解释占位
- **AND** SHALL 不把远端 URL、file ID 或猜测的本地路径写入 MessageEvent.media_urls

#### Scenario: 历史图片 materialization 失败

- **WHEN** 历史消息中的图片 helper 不可用、下载失败或返回无效本地路径
- **THEN** 该图片 SHALL 不进入 MessageEvent.media_urls
- **AND** 对应历史 `channel_context` SHALL 保留既有图片失败占位和安全诊断

#### Scenario: 图片内容摘要读取受限且只发生在 trigger

- **WHEN** image helper 已成功返回本地路径，并且该路径通过本地常规文件、非空、大小上限和可读性检查
- **THEN** 系统 SHALL 在 trigger resolver 完成前以受限流式方式计算 SHA-256
- **AND** wait 阶段 SHALL 不读取该文件、不调用 hash 逻辑且不改变原有零资源 I/O 边界
- **AND** 该读取 SHALL 仅用于当前 batch 内图片等价性判断

#### Scenario: 不安全或不可读图片不被猜测等价

- **WHEN** helper 返回路径不是允许的本地常规文件、文件为空、超过大小上限、状态检查失败或读取/hash 失败
- **THEN** 系统 SHALL 不使用该图片的 hash 参与内容去重
- **AND** SHALL 不从 resource_id、URL、summary、文件名或其他协议字段推断图片相同
- **AND** 仍按现有 helper materialization 和本地路径过滤规则安全降级

## ADDED Requirements

### Requirement: 当前 trigger batch 的成功图片必须按内容选择代表

对于同一个 `ResolvedTriggerBatch`，系统 MUST 以实际图片 bytes 的 SHA-256 作为成功图片的内容等价依据。系统 MUST 先处理历史 context 中可见的直接图片，再按当前 trigger 消息和可见 reply 内容的原始顺序处理图片；同一内容只保留首次成功 materialization 作为代表，并保留代表的路径、MIME 和出现位置。该规则不得跨 trigger batch、chat、session 或进程复用。

#### Scenario: 不同 resource_id 和随机路径的相同图片只保留首次代表

- **WHEN** 历史或当前输入中的两张 image 具有不同 `resource_id`、不同 helper 返回路径但文件 bytes 相同
- **THEN** 同一次 MessageEvent 的媒体输入 SHALL 只包含首次 occurrence 的路径
- **AND** 后续 occurrence SHALL 使用首次代表的 basename
- **AND** 不同 trigger batch 中相同 bytes 的图片 SHALL 分别重新判断

#### Scenario: 历史图片优先于当前图片

- **WHEN** 最后一条历史消息与当前 trigger 消息包含内容相同的成功图片
- **THEN** 历史 occurrence SHALL 成为代表
- **AND** 当前 occurrence SHALL 不增加 `media_urls` 项但其可见 placeholder SHALL 指向历史代表 basename

#### Scenario: 可见历史直接图片优先于不可见嵌套 reply 图片

- **WHEN** 历史消息的嵌套 reply 中存在与其他图片相同的 materialized image，但该 reply 图片没有进入历史
  `channel_context` 的可见图片集合
- **THEN** 该嵌套 reply 图片 SHALL 不抢占代表
- **AND** SHALL NOT 因此进入本次 MessageEvent 的历史图片媒体列表

#### Scenario: hash 失败回退到保守的路径 identity

- **WHEN** 某个成功 image materialization 无法完成受限 SHA-256
- **THEN** 系统 SHALL 不把它与其他不同路径的 materialization 合并
- **AND** 相同路径仍 MAY 按现有 exact path 规则只保留首次项
- **AND** 该降级 SHALL 使用不含 URL、完整路径、文件内容或异常正文的安全诊断

#### Scenario: 图片代表的 MIME 与媒体数组保持配对

- **WHEN** 多个图片 occurrence 中存在内容重复或 hash 失败
- **THEN** `media_urls` 和 `media_types` SHALL 只为最终保留的代表逐项生成
- **AND** 两个数组 SHALL 等长、顺序一致，并使用代表首次出现时的 MIME
