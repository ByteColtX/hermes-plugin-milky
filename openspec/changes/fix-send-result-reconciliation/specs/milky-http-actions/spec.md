# Spec Delta

## ADDED Requirements

### Requirement: 发送响应必须保留可验证的副作用证据

发送类非 Tool Action MUST 在严格 HTTP、envelope 和字段校验边界内区分协议状态与可验证的发送结果；HTTP 200 或单一状态字段 SHALL NOT 单独代表成功。

#### Scenario: 异常 envelope 含可验证序号
- **WHEN** 消息发送响应的协议状态异常，但响应仍提供符合发送契约且可验证的远端 `message_seq`
- **THEN** 插件 SHALL 将该响应归一化为已确认发送结果
- **AND** SHALL 保留该序号作为发送结果标识
- **AND** SHALL 不把 HTTP 200 单独作为成功依据

#### Scenario: 异常 envelope 没有成功证据
- **WHEN** 消息发送响应被拒绝、结构异常或传输结果未知，且没有可验证的远端发送证据
- **THEN** 插件 SHALL 保持 `rejected`、`malformed` 或 `transport_unknown` 分类
- **AND** SHALL 不生成本地消息序号或假成功

#### Scenario: 非发送 Action 不继承发送归一化
- **WHEN** 登录、状态、资源、上传或其他非发送 Action 返回协议异常
- **THEN** 插件 SHALL 继续使用该 Action 既有的严格错误分类
- **AND** SHALL 不因响应包含通用字段而报告发送成功
