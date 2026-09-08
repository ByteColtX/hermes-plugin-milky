## MODIFIED Requirements

### Requirement: 初始化顺序保护消息入口

适配器 MUST 在允许普通消息进入入站处理前完成登录身份确认和群禁言初始同步；主动唤醒 watcher
还 MUST 等待初始同步、已有 Hermes session route 恢复和普通消息入口开放后才启动。

#### Scenario: 初始同步完成后开始消费消息

- **WHEN** 适配器建立连接并完成登录信息、群列表和自身群成员状态同步
- **THEN** 它 SHALL 才开始将 `message_receive` 事件交给入站流水线
- **AND** 只有在已有 session route 恢复并且 adapter ready 后，才允许启动主动 watcher

#### Scenario: 初始同步失败

- **WHEN** 登录信息或必要的初始状态同步失败
- **THEN** 适配器 SHALL 保持消息入口未就绪
- **AND** SHALL 不启动主动 watcher，并报告可分类的启动或传输错误

#### Scenario: 主动策略关闭

- **WHEN** adapter ready 但 `MILKY_PROACTIVE_POLICY.enabled` 为 `false`
- **THEN** 适配器 SHALL 不创建主动 watcher
- **AND** 普通 `message_receive` 生命周期 SHALL 不受影响

### Requirement: 生命周期停止和重连不复制状态

适配器 MUST 在停止时释放事件消费者、HTTP 响应、请求、主动 watcher、定时器和状态刷新任务；
重连 MUST 不创建重复 watcher，也不恢复断线期间未知丢失的消息、进程重启前未知丢失的 proactive
epoch/每日计数、wait buffer 或 Will 分数。组件清理和 fatal error report 失败 SHALL 保留各自的错误分类，并使用
`event=milky.lifecycle` 的独立结果诊断；诊断不得输出异常正文、路径或凭证，也不得改变其余组件
的清理、连接状态或错误结果。

#### Scenario: 重复停止

- **WHEN** 已停止的适配器再次收到停止请求
- **THEN** 它 SHALL 安全返回
- **AND** SHALL 不继续调用 Hermes 或 Milky

#### Scenario: SSE 断线后重连

- **WHEN** 事件流断线并建立新的连接
- **THEN** 适配器 SHALL 使用新的事件流继续消费可见事件
- **AND** SHALL 取消旧 watcher 后最多启动一个新的 watcher
- **AND** SHALL 保留去重保护但 SHALL NOT 假设服务端补发断线期间事件或恢复进程重启前的 proactive epoch/每日计数
- **AND** 运维日志 SHALL 能区分断线、重连和重新就绪，不得伪造消息恢复

#### Scenario: 组件关闭和 fatal report 失败

- **WHEN** 生命周期清理某个组件失败，或 adapter 向 Hermes 报告 fatal error 的本地调用失败
- **THEN** 前者和后者 SHALL 保留各自的错误分类并记录独立的 `event=milky.lifecycle` 诊断
- **AND** 两者 SHALL 只使用固定组件、分类、异常类型名或 reason，且不得输出异常正文、路径或凭证
- **AND** fatal report 失败 SHALL NOT 再伪造 component close 或第二条 connect failure 终态

#### Scenario: watcher 失败不拖垮普通消息

- **WHEN** 主动 watcher 的一次 session 列表读取或候选判断失败
- **THEN** 适配器 SHALL 记录安全的 watcher failure 分类并继续维护普通事件流
- **AND** SHALL 不因该失败关闭 Milky client、阻断普通入站或伪造主动发送成功
