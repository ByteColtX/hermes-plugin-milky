# Proposal

## Why

Hermes 会把被拒绝的 `[SILENT]` 标记替换成一条面向用户的英文兜底提示；当前 Milky adapter 会照常将其发送到 QQ。希望不修改 Hermes core，就能在插件出站边界精确抑制这条提示，同时为以后添加其他精确拦截项保留可复用机制。

## What Changes

- 在 Milky 普通文本出站路径加入可复用的精确匹配拦截机制；本次只登记 Hermes 的 silence-marker 兜底提示。
- 只有完整出站文本与该提示逐字符相等时才拦截；不得按子串、前缀、相似文本或包含该句子的较长正常回复进行拦截。
- 命中时不调用 Milky 消息 Action，且以不会触发 Hermes 自动重试的终止结果结束此次出站；媒体和文件路径不受影响。
- 在提示匹配项旁保留中文维护注释，标注文案来源为 Hermes `gateway/run_turn.py` 中的 `_UNEXPECTED_SILENCE_REPLY`，提醒上游文案变更时同步更新。
- 不修改 Hermes core，也不尝试在 Hermes 生成、存储或其他平台发送之前改写回复。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `outbound-messaging`：补充普通文本的可复用精确拦截行为、当前提示的抑制范围及未命中时保持原有发送语义。

## Impact

- 影响插件 adapter 的普通文本出站入口、出站结果处理和相关测试；不改变 Milky 协议或 Hermes core。
- 当前提示来自 Hermes 源码 `gateway/run_turn.py::_UNEXPECTED_SILENCE_REPLY`，该常量被普通 turn 与 queued follow-up 共用。
- Hermes Gateway 在 adapter 调用前创建投递 obligation，并以 `SendResult.success` 判定 obligation 是否已送达。为避免对被拦截文本进行自动重试，插件必须将拦截作为终止处理；在不改 core 的约束下，Gateway 仍可能把它记为 delivered，尽管没有 Milky 消息 Action 或远端 message ID。该账本语义需在设计和验证边界中明确，不得伪造远端 ID。
- 不在本次范围内：拦截其他 `[SILENT]` 形式、按关键词或模糊规则屏蔽消息、配置界面、影响其他平台，或清除 Hermes 已保存的回复。
