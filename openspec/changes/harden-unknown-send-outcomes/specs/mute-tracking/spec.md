## MODIFIED Requirements

### Requirement: 刷新受锁、冷却和并发上限保护

群状态主动刷新 MUST 具备每群锁、冷却和并发上限；群消息任意文本、图片、文件、语音或视频发送失败时 MAY 触发对应群刷新，私聊发送失败 MUST NOT 查询群成员状态。发送失败触发的刷新 SHALL 是独立的只读状态维护，不得阻塞、改变或驱动原始发送结果的 fallback、重试或第二次提交。

#### Scenario: 多条群发送失败

- **WHEN** 同一群的多条出站请求几乎同时失败
- **THEN** tracker SHALL 合并或限制刷新请求
- **AND** SHALL 不产生无界的成员查询风暴

#### Scenario: 传输未知时刷新不驱动重发

- **WHEN** 群消息发送结果为 `transport_unknown` 且刷新钩子被触发
- **THEN** tracker MAY 使用 `get_group_member_info` 更新 Bot 自身的成员禁言快照
- **AND** 刷新完成、失败或超时 SHALL 不触发 fallback、重试或第二次发送，原始 SendResult SHALL 保持 `transport_unknown`

#### Scenario: 私聊发送失败

- **WHEN** dm 发送失败
- **THEN** 系统 SHALL 原样返回发送错误
- **AND** SHALL 不调用群成员查询或刷新任何群状态

#### Scenario: SSE 重连不重新扫描

- **WHEN** 事件流断线后重新建立连接
- **THEN** MuteTracker SHALL 保留现有内存状态
- **AND** SHALL 不重新执行登录后的群列表和成员全量扫描
