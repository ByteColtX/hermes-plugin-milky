## Why

当前 willingness 在 `trigger` 决策后才启动 detached handoff，并等资源解析和 Hermes `handle_message()` 返回后扣除 `replyCost`。高峰期多条消息可以在前一次扣分前完成决策，导致同一 chat 在短时间内连续 `trigger`；将“决定参与对话”与“远端处理成功”绑定也增加了不必要的异步状态复杂度。

## What Changes

- **BREAKING** 将 willingness 的 `replyCost` 定义为一次 `trigger` 决策的参与成本，在 `trigger` 决策完成后同步扣除。
- 一次通过 Gate 且得到 `trigger` 的普通消息最多扣除一次；`wait`、Gate deny、命令、系统事件和 temp 消息不扣分。
- 扣分不再等待资源解析、Hermes `handle_message()` 或最终 QQ 发送，也不因后续处理失败回滚。
- 删除成功 handoff 后才反馈 reply cost 的滞后路径，保持 routing engine 的既有行为不变。
- 为连续同 chat 消息补充回归测试，确认下一条消息能观察到前一次 `trigger` 的扣分，并覆盖失败 handoff 仍扣分的语义。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `will-willingness`: 修改 `replyCost` 的计费时点和失败语义，使其在 `trigger` 决策时同步扣除且不回滚。
- `hermes-message-pipeline`: 修改 trigger 与 Will 反馈的交接边界，不再以 Hermes `handle_message()` 成功返回作为扣费条件。

## Impact

- 影响 `inbound/pipeline.py` 的 trigger admission 和 detached handoff，以及 `will/willingness.py` 的 reply cost 反馈接口。
- 需要更新对应 OpenSpec delta、willingness/pipeline 回归测试和描述该行为的架构或 README 文档。
- 不改变 Gate 顺序、`wait` buffer、资源解析、Hermes Agent 调度、出站 `send_*_message` Action 或 routing 规则。
