# outbound-messaging Specification

## Purpose

定义 Hermes 出站内容到 Milky 目标和 segment 的安全映射，覆盖 group、dm 以及临时目标的明确拒绝、
长文本、结构化媒体、文件上传与稳定 SendResult，确保目标错误不会误投递或假成功。

## Requirements

### Requirement: 出站目标按命名空间路由

`group:<id>` MUST 使用 `send_group_message`，`dm:<id>` MUST 使用 `send_private_message`；临时会话目标和其他非法目标 MUST 返回 `unsupported` 或本地目标校验失败；目标解析失败 MUST 在网络访问前返回且不得回退默认频道或私聊。

#### Scenario: 群消息发送

- **WHEN** Hermes 向合法 `group:<id>` 目标发送非空消息
- **THEN** 系统 SHALL 调用 `send_group_message`
- **AND** 请求 SHALL 使用该群 ID 而不是默认目标

#### Scenario: 临时会话目标

- **WHEN** Hermes 向临时会话目标发送消息
- **THEN** 发送 SHALL 在网络访问前返回 `unsupported`
- **AND** SHALL 不调用私聊 Action 或群聊 Action

#### Scenario: 非法目标

- **WHEN** 目标为空、负数、非数字或包含额外分隔符
- **THEN** 发送 SHALL 在网络访问前失败
- **AND** SHALL 不回退为 dm、默认频道或其他目标

### Requirement: 文本和结构化内容由统一格式转换

出站文本、mention、mention_all、face、reply、image、record、video、forward 和 light_app MUST 按 Milky segment schema 生成；空白消息 MUST 在网络访问前拒绝。

#### Scenario: 结构化消息

- **WHEN** Hermes 提供文本与结构化 outgoing segments
- **THEN** 请求 body SHALL 包含按原语义生成的 Milky segments
- **AND** adapter SHALL 不在生命周期代码中手工拼接不透明 Action body

#### Scenario: 空白消息

- **WHEN** 出站内容为空或只包含空白
- **THEN** 发送 SHALL 返回本地输入错误
- **AND** SHALL 不访问网络

### Requirement: 超长文本按明确边界拆分

超过 Milky 或 LLBot 限制的文本 MUST 按明确且可诊断的边界拆分为多个发送单元，每个单元的结果 SHALL 可独立观察。

#### Scenario: 超长文本

- **WHEN** 文本超过配置或协议允许的长度
- **THEN** 系统 SHALL 按边界拆分而不是截断内容
- **AND** SHALL 依次处理每个发送单元并保留失败位置

### Requirement: 文件使用独立上传 Action

出站文件 MUST 根据目标调用 `upload_group_file` 或 `upload_private_file`，不得将 file 放入 send message segments，也不得假设远端能访问本地路径。

#### Scenario: 群文件上传

- **WHEN** 合法群目标包含文件
- **THEN** 系统 SHALL 调用 `upload_group_file`
- **AND** SHALL 不把 file segment 塞入 `send_group_message`

#### Scenario: 本地路径不可共享

- **WHEN** 文件输入是当前主机的本地路径
- **THEN** 系统 SHALL 按已确认的上传契约处理或安全拒绝
- **AND** SHALL 不假设 Milky 进程可直接读取该路径

### Requirement: 发送结果和不支持能力诚实可观测

成功发送 MUST 使用远端 `data.message_seq` 生成稳定字符串消息 ID；协议拒绝、传输未知、malformed 和 unsupported MUST 分别报告，未实现的编辑、撤回、reaction 等能力 MUST 返回 `unsupported`。

#### Scenario: 发送成功

- **WHEN** send Action 成功并返回 `message_seq`
- **THEN** Hermes SendResult SHALL 标记成功并使用该序号作为 message ID
- **AND** SHALL 不使用本地时间或随机值

#### Scenario: 群发送失败

- **WHEN** 群文本、媒体或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** MAY 通知 MuteTracker 刷新对应群，但 SHALL 不把所有错误都伪装成禁言

#### Scenario: 未实现 Action

- **WHEN** 请求编辑、撤回、reaction 或其他未实现能力
- **THEN** SendResult SHALL 为 `unsupported`
- **AND** SHALL 不根据 Action 名称猜测成功
