## MODIFIED Requirements

### Requirement: Hermes materialization 必须在 MessageEvent 映射前完成

resolver MUST 在 mapper 和 `handle_message()` 之前等待 detached batch 中历史消息与当前消息实际使用的异步 Hermes URL helper/materializer 完成。成功结果 SHALL 形成 `hermes_attachment_materializations`，包含 Hermes 可访问的本地路径、MIME 和 kind；历史上下文中实际展示的图片和当前 trigger 消息的图片均属于本次 Hermes 媒体输入候选。只有这些本地路径才可写入 `MessageEvent.media_urls`/`media_types`；未 materialize 的 Milky URL、`file_id` 或远端引用不得直接写入 `media_urls`。

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
