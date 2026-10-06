# Spec Delta

## ADDED Requirements

### Requirement: 多段出站结果必须按段状态聚合

一次普通多段回复 MUST 以每个发送单元的归一化结果计算整体状态；整体成功只允许在所有发送单元都得到已确认成功证据后产生。

#### Scenario: 所有分段均确认成功
- **WHEN** 多段回复的每个发送 Action 都返回可验证的远端消息序号
- **THEN** 插件 SHALL 向 Hermes 返回 `success=true`
- **AND** SHALL 使用最终段序号作为整体消息 ID
- **AND** SHALL 保留前段序号作为 continuation 信息

#### Scenario: 前段成功证据被错误标成拒绝
- **WHEN** 某段响应的协议状态异常，但该段仍有可验证的发送成功证据
- **THEN** 该段 SHALL 按已确认成功参与整体聚合
- **AND** 后续所有段确认成功时整体 SHALL 返回成功

#### Scenario: 任一段明确拒绝
- **WHEN** 某段没有可验证成功证据且被远端明确拒绝
- **THEN** 整体 SHALL 返回该段的安全失败分类
- **AND** SHALL 保留已成功段序号和失败位置
- **AND** SHALL 不把最终段状态用于覆盖该失败

#### Scenario: 任一段结果未知
- **WHEN** 某段已经进入可能产生副作用的网络边界但结果无法确认
- **THEN** 整体 SHALL 保持 `transport_unknown`
- **AND** SHALL 不伪造成功或再次提交该段 Action
