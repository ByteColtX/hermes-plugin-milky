## Why

当前 `[SPLIT]` 只有单独成行时才生效。Agent 在生成短句式回复或上游压缩换行时，无法在同一行声明消息边界；需要在保留现有顺序、长度预检和失败语义的前提下支持行中分段。

## What Changes

- **BREAKING** 扩展 `[SPLIT]` 识别范围：大小写严格匹配的未转义行中标记也会形成文本分段；现有独立行语义继续保留。
- 保持标记删除、空段过滤、最多三个文本消息、尾部合并、既有长度分块、首个 Action 前整体预检和按序部分失败结果。
- 定义 `[[SPLIT]]` 为字面量转义形式，出站显示为 `[SPLIT]`，不触发分段；仅保护语法完整的 CQ-compatible 候选（包括未知 type）中的 `[SPLIT]`，malformed 或未闭合的 `[CQ:` 内容按普通文本规则处理，避免宽泛保护吞掉后续分段。
- 明确行中标记两侧的非标记空白不自动 trim；普通换行、正文空白、CQ segment 顺序和文本先于 `MEDIA:` 附件的现有交接保持不变。
- 更新 Agent-facing 指引、架构文档、README、脱敏 fixture 和出站回归测试，并保留不含有效标记的普通长文本原有多条分块行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `outbound-message-splitting`: 将严格独立行标记扩展为支持未转义行中标记，并定义字面量转义、语法完整 CQ 候选保护、malformed CQ-like 普通文本处理和空白边界。
- `outbound-messaging`: 更新有效分段的识别、长度预检和文本/附件交接契约。
- `agent-facing-message-controls`: 更新 Agent 可见的 `[SPLIT]` 行中用法和 `[[SPLIT]]` 字面量用法。
- `milky-platform-prompt-guidance`: 更新 Milky system prompt section 中的分段语法说明。

## Impact

- 影响 `outbound/splitting.py`、`outbound/sender.py`、相关 fixture 和测试，以及根入口提示文案、`ARCHITECTURE.md`、`README.md`。
- 影响出站文本的可观察消息数量和正文边界；含未转义行中 `[SPLIT]` 的旧正文将按新契约被视为控制语法，属于明确的兼容性变化。
- 不新增依赖、配置、HTTP Action 或 ToolSpec；不修改 Hermes core、入站 pipeline、Gate、Will、reply cost、媒体 materialization 或文本先于附件的交接。
