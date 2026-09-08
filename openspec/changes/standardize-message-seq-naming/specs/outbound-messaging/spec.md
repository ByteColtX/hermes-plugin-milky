## MODIFIED Requirements

### Requirement: 发送结果和不支持能力诚实可观测

成功发送 MUST 使用远端 `data.message_seq` 生成稳定字符串形式的插件侧 `message_seq`；成功文件上传 MUST 使用远端确认的 `file_id` 作为附件结果标识；协议拒绝、传输未知、malformed 和 unsupported MUST 分别报告，未实现的编辑、撤回、reaction 等能力 MUST 返回 `unsupported`。当结果交给 Hermes 时，适配器 SHALL 将同一字符串序号映射到 Hermes 要求的 `SendResult.message_id`，不得把 Hermes 字段名反向扩散为 Milky/插件侧协议字段名。

#### Scenario: 发送成功

- **WHEN** send Action 成功并返回 `message_seq`
- **THEN** 插件侧成功结果 SHALL 保留该远端序号为 `message_seq` 的稳定字符串
- **AND** Hermes SendResult SHALL 标记成功并使用同一字符串作为其兼容的 `message_id`
- **AND** SHALL 不使用本地时间、随机值或本地计数器

#### Scenario: 群发送失败

- **WHEN** 群文本、媒体或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** MAY 通知 MuteTracker 刷新对应群，但 SHALL 不把所有错误都伪装成禁言

#### Scenario: 未实现 Action

- **WHEN** 请求编辑、撤回、reaction 或其他未实现能力
- **THEN** SendResult SHALL 为 `unsupported`
- **AND** SHALL 不根据 Action 名称猜测成功

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

#### Scenario: 媒体或文件发送失败

- **WHEN** 图片、语音、视频或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** SHALL 不伪造成功、不发送包含路径的 fallback 文本或盲目重复可能产生副作用的 Action
