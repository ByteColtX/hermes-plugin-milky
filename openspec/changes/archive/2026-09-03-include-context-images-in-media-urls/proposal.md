## Why

当前 trigger 的资源 resolver 已经为历史 wait 消息生成图片 materialization，并将图片正文放入
`channel_context`，但 Hermes `MessageEvent.media_urls` 只接收当前 trigger 的附件，导致 Agent
能看到历史图片的占位文本，却无法读取对应图片。需要统一两部分图片输入，避免上下文与媒体内容失配。

## What Changes

- 将 `channel_context` 历史消息中的已 materialize 图片与当前 trigger 图片合并为同一组 `media_urls`。
- 按历史上下文记录顺序排列历史图片，再按当前 trigger 消息中的 segment 顺序排列当前图片。
- 对合并后的本地图片路径去重，保留首次出现的位置，并使 `media_types` 与去重后的 `media_urls` 一一对应。
- 仅纳入已由 Hermes helper 返回并通过本地路径校验的图片；未 materialize 的引用继续使用既有降级行为。
- 保持当前消息只进入正文、历史消息只进入 `channel_context`，不把音频、视频、文件或未知引用误计为历史图片。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `media-and-reply-resolution`: 明确历史上下文中的图片 materialization 在 trigger 交接时仍可供 Hermes 媒体输入使用。
- `hermes-message-pipeline`: 明确 `MessageEvent.media_urls` 按历史 context 图片到当前 trigger 图片的顺序合并并去重。

## Impact

- 影响入站资源解析结果到 Hermes `MessageEvent` 的交接，以及相关 mapper、pipeline 集成测试和脱敏 fixture。
- 不改变 Milky Action、Hermes 媒体下载/缓存/权限所有权、Gate/Will 顺序、wait buffer 或消息正文渲染。
- 不新增远端查询、不把远端 URL 或未经确认的路径写入 `media_urls`，也不修改 Hermes core。
