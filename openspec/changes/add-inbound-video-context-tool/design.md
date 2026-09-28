# Design

## Context

参见 proposal.md 的 Why。Milky v1.3.0 OpenAPI 定义 video segment 的 `resource_id`、`temp_url`、`width`、`height` 和秒级 `duration`，并定义 `get_resource_temp_url` 的 `resource_id` 输入和 URL 响应。仓库 parser 已解析视频 ID 与时长；入站正文目前固定显示不支持占位符。

当前 trigger resolver 对媒体引用执行 URL 查找，包含 video；但其已确认的 Hermes URL helper 只覆盖图片和语音，所以视频不会形成可交给 Hermes 的本地 materialization。Milky client 已有内部 `get_resource_temp_url` 调用，返回解析后的 Action envelope；已注册 Action Tool 则沿不透明响应体路径交付。两个使用者需要保持不同的响应契约。

## Goals / Non-Goals

**Goals:**

- 让消息正文和历史 `channel_context` 中的视频引用显示协议提供的资源 ID 和时长。
- 让 Agent 显式调用固定 Action Tool 获取临时 URL，保留当前静态工具目录及其参数、生命周期、错误和日志边界。
- 普通消息路径不再为视频自动请求 URL 或执行无结果的媒体 materialization。

**Non-Goals:**

- 下载、缓存、解码、抽帧、转录或分析视频内容。
- 将 Milky 临时 URL 写入 `MessageEvent.media_urls`，或猜测 Hermes 存在视频处理 helper。
- 改变图片、语音、文件和回复资源处理规则。

## Decisions

### 视频引用在规范化正文中提供有限信息

沿用 segment placeholder 的原始顺序展示 `resource_id` 和秒级 `duration`，各字段缺失时单独使用 `NOT SUPPORTED`。不在正文中渲染 `temp_url`、尺寸或原始 segment；这样 Agent 可以把可见 ID 作为后续显式 Tool 调用参数，同时避免将临时链接复制进普通消息文本。选择 placeholder 而非单独的隐藏 metadata，是因为当前 Agent 的稳定可见输入是规范化正文和 context record。

### 自动 resolver 对视频短路

资源解析遇到 `video` 引用时保留 placeholder 和引用诊断，不查询 inline 或按 ID 获取的临时 URL，也不调用 materializer。图片和语音继续使用现有 resolver 路径。另一种方案是保留目前的 URL 查询再返回 `unsupported`；它会在 Agent 尚未决定是否使用视频前产生无用网络操作，与惰性引用目标不符。

### Tool 与内部资源查询使用独立响应路径

新增 Tool 只接受一个非空字符串 `resource_id`，请求固定的 `get_resource_temp_url` operationId。复用现有 client 生命周期和 HTTP Action 边界，但为 Tool 保持原始响应体交付；内部资源解析继续使用其既有的已解析 envelope 契约，不把 Tool 的不透明字符串反向用作 resolver 输入。

Tool 仅由 Agent 显式调用。参数校验和 client 可用性检查发生在网络前；取得响应体后不做 JSON/envelope/data 校验或重建；未取得响应体时使用既有 `transport_unknown` 分类。工具注册阶段仍只登记 schema 和 handler，不联网。其日志遵守既有 `milky.tool` 最小化边界，不记录资源 ID、URL、请求参数或响应体。

## Risks / Trade-offs

- [临时 URL 会过期，且 Tool 返回由 Hermes core 继续交付] → Agent 需要在实际使用时显式重新查询；插件不将 URL 持久化或自动复用，也不承诺宿主转录对 Tool 结果的后续处理。
- [获得 URL 不代表模型具备视频输入能力] → 能力描述明确限制为获取链接；视频下载、分析和宿主媒体支持保持未确认。
- [视频现在不再自动请求资源 Action] → 这是惰性上下文行为所需的可观察变化；图片、语音和文件路径保持原状，并用 resolver 调用断言防止回归。
