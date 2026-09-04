## Why

当前 Milky 出站 sender 只按普通文本或单次媒体入口投递，Agent 无法在一次回复中声明适合聊天节奏的多个文本消息。需要增加一个边界清晰的 `[SPLIT]` 控制标记，同时明确它与 Hermes 已有 `MEDIA:` 提取和附件投递之间的顺序，避免模型无法预测用户实际收到的消息序列。

## What Changes

- 新增 Milky 出站文本的 `[SPLIT]` 解析：只识别单独成行、大小写严格匹配的 `[SPLIT]`，删除有效标记及其分隔行，不把其他相似文本当作控制指令。
- 将包含有效标记的一次文本回复整理为按原顺序投递的最多 3 个文本消息单元；空的分段不产生空消息，超过 3 个分段时合并尾部内容而不丢失文本。现有超长文本边界仍适用；若最终物理消息数无法控制在 3 条内，则在网络访问前整体拒绝，不能截断或部分发送。
- 固定当前 Hermes 媒体边界：`MEDIA:` 由 Hermes core 提取并在文本投递完成后调用 Milky 的媒体/文件入口，因此“文本 + `[SPLIT]` + MEDIA”按文本分段顺序、再按附件顺序发送；本 change 不支持文本段和附件交错，也不修改 Hermes core。未来交错投递需要 core 提供有序的文本/附件交接契约。
- 在 `PLATFORM_GUIDANCE` 中加入 `[SPLIT]` 的使用说明，并将 `NO_REPLY` 文案替换为 `[SILENT]`；`[SILENT]` 仍完全由 Hermes core 处理，插件不新增该标记的解析或发送逻辑。
- 增加解析、边界、文本/附件顺序、错误原子性、提示文案和现有媒体回归测试，并同步稳定架构边界、README 与 OpenSpec 说明。

## Capabilities

### New Capabilities

- `outbound-message-splitting`: 定义 `[SPLIT]` 的严格解析、最多 3 条文本消息、内容保留、发送顺序和失败边界。

### Modified Capabilities

- `outbound-messaging`: 扩展文本出站分块语义，并明确与 Hermes 独立媒体/文件投递的顺序及不交错边界。
- `agent-facing-message-controls`: 为 Agent-facing 平台指引增加 `[SPLIT]` 的可选使用约定，并保持控制标记不进入用户可见文本。
- `milky-platform-prompt-guidance`: 更新 Milky system prompt section 的实际指引，将 `NO_REPLY` 统一替换为 `[SILENT]`，并加入 `[SPLIT]` 说明。

## Impact

- 影响 `outbound/sender.py`、出站文本解析/分块边界、根入口 `__init__.py` 的 `PLATFORM_GUIDANCE`，以及相关 adapter、fake Hermes/Milky 集成测试和项目文档。
- 不新增 Milky Action、ToolSpec、配置项或 Python 依赖；不修改 Hermes core，不改变 `MEDIA:` 的资源校验、native media segment、独立 file upload、`group:`/`dm:` 路由和 SendResult 分类。
- 含有效 `[SPLIT]` 的文本回复需要在投递前完成全部分段和长度校验，以保证最多 3 条和不丢内容；任一边界失败时不得先发送前序消息。
- 由于当前 Hermes 将 `MEDIA:` 附件作为文本之后的独立交接，文本/附件交错投递属于明确的后续跨仓库能力，不在本 change 的实现承诺内。
