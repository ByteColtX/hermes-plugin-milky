## MODIFIED Requirements

### Requirement: 发送结果和不支持能力诚实可观测

成功发送 MUST 使用远端 `data.message_seq` 生成稳定字符串消息 ID；协议拒绝、传输未知、malformed 和 unsupported MUST 分别报告，未实现的编辑、撤回、reaction 等能力 MUST 返回 `unsupported`。已经进入网络请求边界但结果为 `transport_unknown` 的消息 MUST 保留未知语义，禁止 plain-text fallback、自动重试或第二次提交。

#### Scenario: 发送成功

- **WHEN** send Action 成功并返回 `message_seq`
- **THEN** Hermes SendResult SHALL 标记成功并使用该序号作为 message ID
- **AND** SHALL 不使用本地时间或随机值

#### Scenario: 群发送失败

- **WHEN** 群文本、媒体或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** MAY 通知 MuteTracker 刷新对应群，但 SHALL 不把所有错误都伪装成禁言

#### Scenario: 未知发送结果不得降级重发

- **WHEN** 一个群或私聊消息的发送 Action 已进入网络边界并返回 `transport_unknown`
- **THEN** 系统 SHALL 返回 `transport_unknown`，不得报告发送失败为“未执行”或假成功
- **AND** SHALL NOT 调用 plain-text fallback、再次调用对应 send Action 或改变原始消息内容后重发

#### Scenario: 宿主通用发送包装

- **WHEN** Hermes Gateway 通过 Milky adapter 的发送包装交付消息
- **THEN** Milky adapter SHALL 只调用一次自身 sender 并原样返回该结果
- **AND** SHALL NOT 委托给会 retry、发送用户可见失败通知或 plain-text fallback 的通用宿主实现

#### Scenario: 本地格式化失败

- **WHEN** 消息在发送 Action 之前因空白、非法目标或不支持的出站内容被本地拒绝
- **THEN** 系统 SHALL 在网络访问前返回对应错误
- **AND** SHALL NOT 使用 fallback 发送一个可能不同或带诊断文本的用户可见消息

#### Scenario: 未实现 Action

- **WHEN** 请求编辑、撤回、reaction 或其他未实现能力
- **THEN** SendResult SHALL 为 `unsupported`
- **AND** SHALL 不根据 Action 名称猜测成功
