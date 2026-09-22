# Spec Delta

## ADDED Requirements

### Requirement: Action 数据保留与成功判断解耦

Action 调用 SHALL 将协议数据保留边界与成功判断边界分开：非 Tool Action 继续按既有 HTTP、envelope、字段和副作用契约分类；协议对象中的未知字段不得因通用敏感键名被删除。已取得响应体的 Tool 透传语义由关联的 Tool 结果变更统一定义。

#### Scenario: 非 Tool 成功响应含扩展字段
- **WHEN** 登录、状态同步、发送或上传 Action 返回成功 envelope 及未建模扩展字段
- **THEN** 调用 SHALL 继续执行既有最小结构校验
- **AND** 成功结果中的扩展字段 SHALL 保留

#### Scenario: 非 Tool 响应含敏感命名字段
- **WHEN** 非 Tool 响应的 data 或 extras 含通用敏感键名
- **THEN** 字段 SHALL 保留在协议对象中
- **AND** 缺失、错误类型或协议拒绝仍 SHALL 使用既有错误分类
