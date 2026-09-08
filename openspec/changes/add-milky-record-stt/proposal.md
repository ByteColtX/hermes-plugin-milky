## Why

Milky `record` 当前虽然会在 trigger 阶段由 Hermes helper materialize，但纯语音消息被映射为 `MessageType.AUDIO`，Hermes core 因而不会将其作为自动 STT 输入。与此同时，插件正文保留的 `[record:NOT SUPPORTED]` 会与 core 的转录成功、失败或未启用提示重复。需要明确由插件提供语音媒体和正确类型，由 Hermes core 统一负责 STT 及 Agent-facing 提示。

## What Changes

- 将含有可交给 Hermes 的纯 `record` 当前消息映射为 `MessageType.VOICE`，使 Hermes core 能按既有 STT 流程处理 `media_urls` 中的本地音频。
- 保持 `record` 在 trigger 阶段通过 Hermes audio helper materialize，并以配对的本地路径和 MIME 写入 `MessageEvent.media_urls`/`media_types`；不新增插件侧 STT provider 或配置。
- 对已经成功 materialize、交给 core 处理的当前语音消息，移除插件正文中的 `[record:NOT SUPPORTED]`，避免重复显示 core 的转录或语音降级提示。
- 资源 materialization 失败或不受支持时保留现有安全诊断和可解释降级；历史 `channel_context` 中的 `record` 暂不自动 STT，继续使用其既有上下文占位策略。
- 不修改 Hermes core；core 是否配置 STT、转录失败和禁用 STT 的可见提示继续由 Hermes core 决定。

## Capabilities

### New Capabilities

无。本 change 修改已有入站媒体与 Hermes 交接契约，不引入独立能力。

### Modified Capabilities

- `hermes-message-pipeline`: 明确纯 `record` 的 `MessageType.VOICE` 映射、当前语音媒体交给 core，以及插件不重复渲染 core 已负责的 STT 提示。

## Impact

- 受影响代码：`inbound/hermes_mapper.py`、`milky/resources.py` 及其入站 normalizer、resolver、pipeline 测试。
- 受影响的 Agent-facing 行为：当前已成功 materialize 的 Milky 语音不再由插件添加 `[record:NOT SUPPORTED]`；Hermes core 的转录文本或语音失败/禁用提示成为唯一提示来源。
- 受影响的 Hermes 边界：纯语音事件类型从 `AUDIO` 调整为 `VOICE`，媒体数组仍保持本地路径与 MIME 一一对应。
- 不涉及：Milky 协议 Action 变更、Hermes core 修改、STT provider 选择、历史语音自动转录、出站 `record` 发送语义或新的环境变量。
