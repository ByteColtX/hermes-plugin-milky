# Proposal

## Why

入站视频目前只呈现为 `[video:NOT SUPPORTED]`，Agent 看不到可用于后续查询的资源标识和时长。Milky v1.3.0 已定义视频段的 `resource_id`、`duration` 及 `get_resource_temp_url` Action；将资源链接查询暴露为显式工具，可以让 Agent 根据上下文需要再取链接，而不在普通入站路径中为当前不支持的视频预取资源。

## What Changes

- 入站视频占位符展示协议提供的 `resource_id` 和秒级 `duration`；缺失值使用 `NOT SUPPORTED`，不展示 `temp_url`。
- 普通消息处理将视频保留为上下文引用，不自动请求临时 URL 或尝试 materialize 视频。
- 新增固定 Milky Action 工具 `get_resource_temp_url`，只接受非空 `resource_id`，仅在 Agent 显式调用时请求对应 Action，并按现有 Action 工具契约原样交付响应体。
- 不增加视频下载、解码、抽帧、转录或内容理解能力；获得 URL 不代表 Hermes 或 Agent 已能处理视频内容。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `message-segments`：更新入站视频的可见占位符，展示资源 ID 和时长。
- `media-and-reply-resolution`：视频在普通 trigger 中仅作为上下文引用，不自动查询或 materialize。
- `qq-action-tools`：固定 Action ToolSpec 目录增加 `get_resource_temp_url`，定义参数、显式调用及原始响应交付。

## Impact

Milky v1.3.0 OpenAPI 已确认视频段字段以及 `get_resource_temp_url(resource_id) -> url`。当前 parser 已解析视频资源 ID 和时长，资源客户端已有内部临时 URL 查询；但视频 resolver 会在部分路径查询 URL 后因缺少 materializer 降级，且该 Action 尚未注册为 Agent 工具。变更影响入站占位符与资源解析、Action ToolSpec/manifest/client 路由、相关合成 fixture 和测试，以及 README/ARCHITECTURE 能力说明。不会增加依赖，也不改变资源下载与 SSRF 所有权。
