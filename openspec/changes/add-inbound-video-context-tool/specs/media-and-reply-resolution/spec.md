# Spec Delta

## ADDED Requirements

### Requirement: 入站视频保持上下文引用并延迟获取链接

普通消息的 wait 与 trigger 流程 SHALL 保留视频的协议引用供 Agent 上下文展示。自动资源解析 MUST NOT 为视频调用 `get_resource_temp_url`、下载视频或调用媒体 materializer；临时链接仅能由 Agent 显式调用固定的 `get_resource_temp_url` 工具取得。视频引用缺少 `resource_id` 时 SHALL 保留可解释 placeholder，不得从临时 URL 或其他字段推断资源 ID。

#### Scenario: wait 中的视频引用不触网

- **WHEN** 含 video segment 的消息被 Will 判定为 wait
- **THEN** 缓冲 SHALL 保留视频资源引用供后续上下文使用
- **AND** SHALL NOT 调用 `get_resource_temp_url`、下载或媒体 materializer

#### Scenario: trigger 中的视频只展示上下文信息

- **WHEN** 含 video segment 的消息进入普通 trigger
- **THEN** 正文 SHALL 保留协议提供的 `resource_id` 和 `duration` placeholder
- **AND** resolver SHALL NOT 自动请求临时 URL、下载视频或尝试 materialize

#### Scenario: Agent 显式查询视频资源链接

- **WHEN** Agent 根据入站视频 placeholder 显式调用 `get_resource_temp_url` 并提供其 `resource_id`
- **THEN** 插件 SHALL 仅为该工具调用请求 Milky 临时资源链接
- **AND** 工具结果 SHALL 只交付给该 Tool 调用，不得自动插入普通入站正文或 Hermes `media_urls`
