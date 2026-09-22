# Spec Delta

## ADDED Requirements

### Requirement: 协议业务数据不得因通用敏感键名被插件删除

插件在解析、复制、冻结和交付 Milky 协议数据时 MUST 保留远端返回的字段和值，不得仅因键名匹配通用敏感词表而递归删除、掩码、改名或摘要业务字段。该要求不改变日志、异常、配置摘要、smoke 输出和测试资料的既有最小化边界。

#### Scenario: 扩展字段名称与敏感词相同
- **WHEN** Action、事件或消息扩展字段包含 token、password 或其他通用敏感键名
- **THEN** 协议数据交付 SHALL 保留该字段和值
- **AND** 插件 SHALL 不把键名过滤误当作完整秘密保护

#### Scenario: 日志仍保持最小化
- **WHEN** 协议响应包含凭证样式字段、完整 URL 或自由文本
- **THEN** 日志 SHALL 只记录既有低敏元数据
- **AND** 日志 SHALL NOT 复制响应正文、参数或原始业务对象

#### Scenario: 本地错误没有远端响应
- **WHEN** 参数校验、客户端状态或传输阶段无法取得可确认响应
- **THEN** 插件 SHALL 返回既有固定错误分类
- **AND** SHALL 不通过异常正文或原始参数补充所谓脱敏结果
