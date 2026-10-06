# Spec Delta

## ADDED Requirements

### Requirement: 结果归一化后的状态必须在日志中一致

Action 层和出站层 MUST 对同一发送单元使用一致的归一化结果分类；日志 SHALL 能区分协议状态异常、已确认发送和结果未知，且不得记录原始响应或正文。

#### Scenario: 异常状态但确认发送
- **WHEN** 发送响应存在异常协议状态但被插件确认已产生发送副作用
- **THEN** Action 和出站日志 SHALL 记录已确认发送分类
- **AND** SHALL 可通过安全计数、耗时和必要关联 ID 关联两个边界
- **AND** SHALL 不记录响应正文、消息正文或凭证

#### Scenario: 结果未知
- **WHEN** 发送 Action 已进入网络边界但无法确认副作用
- **THEN** Action 和出站日志 SHALL 记录 `transport_unknown`
- **AND** SHALL 不记录成功或拒绝的矛盾终态

#### Scenario: 多段整体结果
- **WHEN** 多段回复完成逐段聚合
- **THEN** 出站日志 SHALL 记录聚合后的最终分类和分段计数
- **AND** SHALL 不把前段已确认成功的结果重新记录为失败
