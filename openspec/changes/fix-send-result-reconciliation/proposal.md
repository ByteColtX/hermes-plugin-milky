# Proposal

## Why

线上一条包含多段普通文本的回复已经在群里出现，但插件仍把其中一次发送结果报告为 `rejected`，Hermes 随后按失败恢复并重发整条回复，造成重复消息和误导性的恢复提示。现有证据表明问题位于插件侧的发送响应归一化与结果交接边界；不能通过修改 Hermes core 或简单采用“最终段覆盖整体状态”来修复。

## What Changes

- 为发送类 Milky Action 建立可验证的结果归一化边界，区分已确认成功、明确拒绝、结果未知和响应结构异常。
- 保留严格的 HTTP、协议 envelope 和最小字段校验；只在发送结果能够提供可靠成功证据时修正错误的失败分类，不把 HTTP 200 单独视为成功。
- 调整多段普通消息的状态聚合：所有段均确认成功后才向 Hermes 返回成功；最终段只用于选择最终消息 ID，不覆盖前段失败或未知状态。
- 保留已成功段的远端消息序号、失败位置和安全分类，避免把部分成功误报为整条成功。
- 增加针对“远端副作用已发生但响应状态异常”、多段全成功、部分成功和结果未知的脱敏测试与可观测性断言。
- 明确不修改 Hermes core、delivery ledger、恢复提示或普通多段消息的用户展示方式。
- 明确不放宽其他非发送 Action 的协议成功条件，不把不确定结果伪造成成功，也不自动重复提交可能已产生副作用的 Action。

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `milky-http-actions`: 发送 Action 需要在严格协议校验下保留并归一化可验证的发送成功证据。
- `outbound-messaging`: 多段发送结果必须按每段真实状态聚合，并向 Hermes 交付诚实的整体结果。
- `outbound-message-splitting`: 分段发送的全成功、部分成功和未知结果需要明确可观察的状态语义。
- `adapter-observability`: Action 层和出站层的分类必须反映归一化后的边界，不能把已确认成功记录为拒绝。

## Impact

- 主要影响插件的 Milky HTTP client、普通出站 sender、结果日志和相关测试/fixtures。
- Hermes core、delivery ledger、宿主 `SendResult` 接口和现有 `[SPLIT]` 展示语义保持不变。
- Milky 服务端对异常 envelope 与已落地副作用之间的实际契约仍需以脱敏协议证据确认；在证据不足时结果必须保持 `unknown`，不能假设成功。
