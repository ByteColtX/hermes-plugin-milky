# Spec Delta

## ADDED Requirements

### Requirement: canonical raw 保留协议字段但不扩大业务解释范围

canonical 记录中的 raw、metadata 和未知扩展 SHALL 保留已接收的协议字段和值，不得因通用敏感键名被插件删除；这些字段仍 SHALL 只用于诊断和协议保真，不得成为会话介绍字段、正文、关键词或隐式工具调用来源。

#### Scenario: raw 含未知扩展字段
- **WHEN** 普通消息包含未知扩展及其任意嵌套字段
- **THEN** canonical raw SHALL 保留该扩展的结构和值
- **AND** 未知扩展 SHALL 不进入正文、关键词或会话介绍

#### Scenario: 会话介绍字段保持白名单
- **WHEN** raw 或未知扩展包含额外身份字段
- **THEN** 会话介绍 SHALL 继续只使用既有场景资料白名单
- **AND** SHALL 不因 raw 字段保真而改变身份确认或 chat key 规则
