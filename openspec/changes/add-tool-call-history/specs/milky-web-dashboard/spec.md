# Spec Delta

## ADDED Requirements

### Requirement: 工具调用历史遵守 Dashboard 认证与 profile 边界

Dashboard MUST 在现有宿主认证和明确 profile 范围内提供 Milky/QQ 工具调用历史与统计的只读视图。查询结果 SHALL 仅包含所选 profile 的记录；视图 SHALL 明确显示当前 profile，并允许按时间、工具和观察状态筛选及稳定、有界分页。统计 SHALL 覆盖全部匹配记录，而非仅当前页。

#### Scenario: 已授权操作者查看历史

- **WHEN** 操作者在受支持的 Hermes Dashboard 中选择一个宿主确认的 profile 并打开工具历史
- **THEN** 页面 SHALL 显示该 profile 的历史记录和同一筛选范围内的统计
- **AND** 不同 profile 的记录 SHALL 不混入当前页面

#### Scenario: 未授权、停用或无效 profile

- **WHEN** 查询未通过宿主认证、插件已停用，或 profile 不属于宿主确认的范围
- **THEN** 系统 SHALL 在返回历史记录或统计前拒绝请求
- **AND** SHALL 不回退至默认 profile 或使用客户端提供的文件系统路径

#### Scenario: 切换 profile 时旧响应迟到

- **WHEN** 操作者从 profile A 切换到 profile B，且 A 的历史查询尚未返回
- **THEN** 后续查询 SHALL 只读取 B 的记录
- **AND** A 的迟到响应 SHALL 不得覆盖 B 的记录或统计视图

#### Scenario: 历史页面只读

- **WHEN** 操作者浏览、筛选或翻页
- **THEN** 页面 SHALL 不创建、审批、重放或修改 QQ 工具调用
- **AND** 查询 SHALL 不改变原始工具结果或调用执行状态

#### Scenario: 分页和汇总保持范围一致

- **WHEN** 操作者对符合筛选条件的历史翻页
- **THEN** 页面 SHALL 按稳定顺序返回有界记录页
- **AND** 调用总数与耗时统计 SHALL 仍覆盖全部匹配记录，不随当前页改变
