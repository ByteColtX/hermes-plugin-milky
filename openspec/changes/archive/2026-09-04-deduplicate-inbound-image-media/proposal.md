## Why

Milky 的同一张图片可能拥有不同的 `resource_id`，而 Hermes image helper 每次 materialize
都会生成随机本地文件名。插件当前按本地路径去重，因此同一 trigger 中相同图片会重复进入
`media_urls`，并可能被 Hermes 重复分析；同时只删除媒体列表中的重复项会留下失效的正文或
`channel_context` 文件名。

## What Changes

- 在 trigger 资源解析阶段，对 Hermes helper 已成功返回的、经过严格路径校验的本地图片执行
  一次受限流式 SHA-256 计算，并仅在当前 `ResolvedTriggerBatch` 内按实际内容去重。
- 保持历史图片优先和原始出现顺序；相同内容只保留首次物理 materialization 及其 MIME，
  `media_urls`、`media_types` 作为成对数据同步更新。
- 将被合并图片的所有可见 placeholder 改写为首次代表路径的 basename，并从改写后的历史
  正文重新生成 `channel_context`，避免引用未进入 `media_urls` 的随机文件名。
- 对当前消息正文及可见的 reply 内容应用相同的代表 basename 规则；未展示的历史嵌套 reply
  图片不得抢占媒体代表或提升为当前 turn 媒体。
- helper 失败、路径不可读、路径不在允许边界、文件状态不安全或 hash 计算失败时保持
  保守降级，不使用 `resource_id`、URL、`file_hash`、summary 或文件名推断图片相同。
- 保留现有按本地路径去重作为最终防线；不修改 Hermes core、不建立跨 batch/session 的插件
  媒体缓存，也不改变 wait 阶段的零资源 I/O 边界。

## Capabilities

### New Capabilities

无。该行为属于现有入站消息、资源解析和 Hermes 交接能力的修正与扩展。

### Modified Capabilities

- `message-segments`: 明确相同图片 occurrence 的成功 placeholder 必须引用同一个首次代表
  basename，失败和未知 hash 仍使用安全降级。
- `media-and-reply-resolution`: 在 helper 成功之后增加受限本地内容摘要读取边界，并定义
  hash 失败、路径安全、嵌套内容和不使用伪 identity 的行为。
- `hermes-message-pipeline`: 明确同一 trigger 的物理图片输入按内容去重，且重建后的
  `channel_context`、当前正文、`media_urls` 和 `media_types` 必须保持一致。

## Impact

- 预计影响 `milky/resources.py`、`inbound/pipeline.py`、`inbound/hermes_mapper.py` 及其
  入站资源、context 和 pipeline 测试。
- 需要补充受限本地文件读取的安全校验、并发/TOCTOU、失败降级和脱敏 fixture 覆盖。
- 不新增 Milky Action、协议字段、Python 依赖或 Hermes core 修改；Milky v1.3 当前没有可用
  的图片 content hash，因此不采用 helper 前置协议 hash 去重。
- 相同内容的重复 occurrence 仍可保留在正文和历史上下文中，但一次 Hermes turn 的物理
  图片输入只保留首次代表；这一可观察语义需要在实现和测试中固定。
