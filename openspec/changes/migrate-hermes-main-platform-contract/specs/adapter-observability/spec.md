# Spec Delta

## ADDED Requirements

### Requirement: Gateway 接收回执准确记录 handoff 状态

普通 MessageEvent handoff 日志 MUST 仅在 Hermes admission receipt 明确表示已接收或排队时记录 Gateway accepted。普通 handler 调用返回、Agent turn 完成和 QQ 出站送达属于不同边界，不得互相推断；未确认接收时 MUST 保留非成功或 unknown 分类。成员事件调用 `inject_message()` 的 `True` 只表示注入请求已排队，MUST 记录为 scheduled，不得据此记录 Gateway accepted 或 Agent turn 已接收。

#### Scenario: Gateway 明确接收事件

- **WHEN** Hermes 为提交的 MessageEvent 返回已接收回执
- **THEN** `event=milky.inbound` SHALL 记录 Gateway accepted
- **AND** 日志 SHALL 不表示 Agent turn 完成或 QQ 已送达

#### Scenario: handler 返回但未确认接收

- **WHEN** handoff 调用正常返回但没有已确认的 Gateway 接收回执
- **THEN** 日志 SHALL 记录未接收或 unknown 的固定分类
- **AND** SHALL NOT 记录 accepted、Agent 完成或 QQ 送达

#### Scenario: handoff 调用抛出异常

- **WHEN** Hermes handler 调用抛出异常
- **THEN** 日志 SHALL 保持安全的 handoff 失败分类
- **AND** SHALL 不记录 Gateway accepted 或触发自动重提

#### Scenario: 成员事件注入只完成排队

- **WHEN** 成员事件的 `inject_message()` 同步返回 `True`，但插件没有异步分发或 ingress admission 回执
- **THEN** `event=milky.inbound` SHALL 将结果记录为 scheduled
- **AND** SHALL NOT 记录 Gateway accepted、Agent turn 已创建或 QQ 已送达
