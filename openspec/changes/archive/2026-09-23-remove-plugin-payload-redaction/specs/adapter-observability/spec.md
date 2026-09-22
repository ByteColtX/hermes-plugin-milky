# Spec Delta

## ADDED Requirements

### Requirement: 日志安全不依赖协议 payload 过滤

运行时日志 SHALL 只使用调用方明确选择的固定分类、状态码、耗时、计数和必要关联 ID；日志安全不得依赖插件先删除协议 payload 字段。插件 SHALL 不新增独立日志脱敏器、响应摘要或原始结果复制路径。

#### Scenario: Action 响应含敏感命名字段
- **WHEN** Action 响应包含凭证样式字段或未知扩展
- **THEN** Action 和 Tool 日志 SHALL 只记录既有低基数元数据
- **AND** SHALL 不遍历、摘要或复制响应对象

#### Scenario: 入站 raw 含未知字段
- **WHEN** 入站消息 raw 保留额外协议字段
- **THEN** inbound、resource 和 handoff 日志 SHALL 仍只记录固定分类及必要关联字段
- **AND** SHALL 不把 raw、正文或媒体引用写入日志
