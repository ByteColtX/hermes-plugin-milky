# Spec Delta

## ADDED Requirements

### Requirement: 分段发送不得用最终段盲目覆盖整体状态

普通 `[SPLIT]` 回复 MUST 保持现有顺序、最多三条和逐段 Action 语义；最终段状态仅决定已确认全成功时的最终消息 ID，不得覆盖其他段的失败或未知状态。

#### Scenario: 两段均已发送但一段状态误报
- **WHEN** 两个发送单元都已得到可验证的远端发送证据，而其中一个响应状态字段与副作用不一致
- **THEN** 插件 SHALL 将两个单元归一化为成功
- **AND** SHALL 返回整体成功
- **AND** SHALL 不触发由错误失败状态造成的整条回复恢复

#### Scenario: 前段明确失败、最终段成功
- **WHEN** 前段没有成功证据且明确失败，最终段发送成功
- **THEN** 整体 SHALL 保持失败
- **AND** SHALL 保留前段失败位置
- **AND** SHALL 不以最终段状态掩盖内容缺失

#### Scenario: 分段边界失败
- **WHEN** 分段在首个 Action 前违反目标、格式或数量边界
- **THEN** 插件 SHALL 继续在网络访问前整体失败
- **AND** SHALL 不创建部分成功结果
