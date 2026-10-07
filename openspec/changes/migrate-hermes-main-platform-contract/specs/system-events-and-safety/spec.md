# Spec Delta

## MODIFIED Requirements

### Requirement: 成员事件通知配置开关

系统 MUST 在启动时读取 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS`，将大小写不敏感的 `true` 和 `false`
解析为布尔值；未设置时 MUST 使用 `false`，以保持默认不产生即时成员通知的低副作用行为。
配置解析完成后该值在本次插件生命周期内 MUST 保持不变，不提供运行中热切换。除 `true`、`false`
或未设置以外的值 MUST 被视为配置错误并阻止插件启动，不得静默猜测默认值。

当该值为 `false` 时，系统 MUST 继续观察字段完整的成员增加/减少事件，并将不带 `Tip` 的基础
英文 body 写入 system context；系统 SHALL 不因该成员事件立即创建 Agent turn，事件继续等待
下一次普通消息触发时消费。该开关 MUST NOT 改变 nudge、message_recall、请求、文件上传或
其他系统事件的既有 observe-only/context-only 行为。

当该值为 `true` 时，系统 MUST 在成员事件 body 末尾附加固定 `Tip`，并仅在当前插件 profile
已明确授权 Gateway injection、事件可形成已确认的 Milky 群来源时调用 Hermes 公开的
profile-scoped `inject_message(origin=...)`。该 API 同步返回 `True` 只表示请求已排入 Gateway
调度；系统 SHALL 将待处理 context 随请求提交并 drain 一次，但 MUST NOT 把该返回值解释为异步
分发、Gateway ingress admission 或 Agent turn 已接收/完成。同步预检失败、返回 `False` 或抛错时，
系统 MUST 保留带 `Tip` 的 system context，并记录安全的 unsupported/failed 诊断。返回 `True` 后，
Gateway 仍可能在异步分发阶段拒绝请求；该结果不会回传给插件，因此系统不保证已 drain 的 context
可恢复，也不得自动重试或声称 Agent turn 已创建。该即时请求 SHALL 不经过普通 `message_receive`
的 Gate/Will，不扣 reply cost，不直接调用 Milky Action。注入授权 SHALL 不授予 Action 权限，也不得由事件正文扩大。

#### Scenario: 未配置时保持成员事件通知

- **WHEN** 启动环境未设置 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS`，随后收到字段完整的成员增加或减少事件
- **THEN** 系统 SHALL 使用不带 `Tip` 的英文基础 body 将事件写入对应群 chat 的 system context
- **AND** 系统 SHALL NOT 因该事件立即创建 Agent turn，而是在下一次普通消息触发时消费该事件

#### Scenario: 显式启用成员事件通知

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 的值为 `true`（大小写不敏感），随后收到字段完整的成员增加或减少事件
- **THEN** 系统 SHALL 使用带固定 `Tip` 的完整英文 body、JSON Details 和可选字段省略规则
- **AND** 当前 profile 已授权注入且 origin 已确认时，系统 SHALL 提交一个 profile-scoped 注入请求
- **AND** 注入 API 返回 `True` 时 SHALL 将该请求分类为已排队并 drain 已提交的 system context
- **AND** `True` SHALL NOT 表示异步分发、Gateway admission 或 Agent turn 已成功
- **AND** 该请求 SHALL 不经过普通消息 Gate/Will，且 SHALL 不扣 reply cost
- **AND** 该授权 SHALL NOT 扩大到 Milky Action 或其他 profile

#### Scenario: 显式关闭成员事件通知

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 的值为 `false`（大小写不敏感），随后收到字段完整的成员增加或减少事件
- **THEN** 系统 SHALL 记录观察结果并将不带 `Tip` 的英文基础 body 放入对应群 chat 的 system context
- **AND** 系统 SHALL 不立即消费该 system context，不创建 Agent turn、修改 Gate/Will 状态或扣 reply cost

#### Scenario: 即时注入不可用

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 为 `true`，但事件来源无法构造成已确认的群 origin、当前 profile 未授予 `allow_gateway_injection`、宿主没有 live Gateway，或注入 API 同步返回 `False`/抛出异常
- **THEN** 系统 SHALL 将带固定 `Tip` 的成员事件保留在对应群 chat 的 system context
- **AND** 系统 SHALL 记录安全的 unsupported/failed 诊断
- **AND** 后续普通消息 SHALL 仍可消费该事件，系统 SHALL 不因注入失败丢弃或重复创建即时 turn

#### Scenario: 注入排队后的异步分发失败

- **WHEN** 注入 API 已返回 `True`，但 Gateway 随后的异步授权复查、adapter 路由或 ingress admission 拒绝该请求
- **THEN** 该异步结果 SHALL 由 Gateway 调度路径处理，插件 SHALL 不把排队结果报告为 Gateway accepted 或 Agent turn 已创建
- **AND** 插件 SHALL NOT 将 Gateway 自身诊断视为可读取的异步完成回执
- **AND** 插件 SHALL 不自动重试，且不保证已 drain 的 system context 可恢复

#### Scenario: 成员事件通知配置非法

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 被设置为除 `true`/`false`（大小写不敏感）以外的值
- **THEN** 系统 SHALL 将其报告为启动配置错误
- **AND** SHALL 不以 `true`、`false` 或其他默认值继续运行

#### Scenario: 关闭开关不影响其他系统事件

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 为 `false`，随后收到合法的 `group_nudge`、`friend_nudge` 或 `message_recall`
- **THEN** 系统 SHALL 继续按对应英文 body 和既有 context-only 规则处理这些事件
- **AND** SHALL 不把成员事件开关解释为全局系统事件开关
