# Spec Delta

## ADDED Requirements

### Requirement: 未知 segment 的 raw 保真与安全降级分离

未知 segment SHALL 保留完整递归结构和值供诊断；保真不得改变未知 segment 不进入正文、策略关键词、工具调用或授权判断的边界。

#### Scenario: 未知 segment 含通用敏感键名
- **WHEN** 未知 segment 的数据包含 token、authorization 或其他未建模字段
- **THEN** segment raw SHALL 保留这些字段和值
- **AND** segment SHALL 仍只进入 raw 和诊断

#### Scenario: 未知 segment 与正文并存
- **WHEN** 消息同时包含未知 segment 和合法文本或结构化 segment
- **THEN** 合法内容 SHALL 按既有顺序处理
- **AND** 未知 segment SHALL 不被转换为普通文本或可执行指令
