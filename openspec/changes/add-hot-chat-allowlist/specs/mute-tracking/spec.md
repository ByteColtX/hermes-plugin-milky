# Spec Delta

## MODIFIED Requirements

### Requirement: 初始群禁言同步使用正确顺序和字段

连接初始化 MUST 依次获取登录信息、群列表，再只为白名单允许的群查询 Bot 自身成员信息；
在成员查询阶段，所有选中的群成员查询 SHALL 在该阶段同时发起，不得因插件侧固定并发上限
或分批等待而逐群启动。成员禁言截止时间 MUST 读取 `member.shut_up_end_time`；启动同步和主动刷新调用
`get_group_member_info` 时 MUST 传入 `no_cache=true`，以避免读取过期的成员状态缓存。
白名单为空时 SHALL 不查询任何群的 Bot 成员状态，
`dm:<id>` 白名单项不触发群成员查询。

#### Scenario: 初始化多个群

- **WHEN** 适配器完成登录信息和群列表请求且白名单显式包含 `group:*`
- **THEN** SHALL 为群列表中的每个群查询 `group_id` 与 `user_id=self_id` 的成员信息，且选中群的查询 SHALL 不等待前一个群的响应后才开始
- **AND** SHALL 在所有必要查询完成前不将消息标记为初始化完成

#### Scenario: 大规模初始化不受插件并发上限阻塞

- **WHEN** 白名单允许的群数量达到 200 个或以上且登录信息和群列表请求成功
- **THEN** 系统 SHALL 在同一个成员查询阶段同时发起所有选中群的成员查询，不设置插件侧并发上限或分批启动查询
- **AND** SHALL 等待所有查询完成后再完成初始同步，不因固定的串行等待导致初始化时间随群数线性累积

#### Scenario: 成员字段为 null

- **WHEN** 成员信息的 `shut_up_end_time` 为 null
- **THEN** member mute SHALL 表示查询成功且当前为 unmuted
- **AND** SHALL NOT 读取或推断为其他协议字段

#### Scenario: 空白名单初始化多个群

- **WHEN** 适配器完成登录信息和群列表请求且白名单为空
- **THEN** SHALL 不发起群成员查询并完成零目标初始化
- **AND** SHALL 保持普通入站全部阻止，后续新增授权群首次获准入站时按需准备群状态

#### Scenario: 初始同步只扫描群白名单

- **WHEN** 白名单包含 `group:100`、`dm:200`，而群列表包含群 `100` 和群 `101`
- **THEN** SHALL 只查询群 `100` 的 Bot 成员信息
- **AND** SHALL 不查询群 `101` 或因 `dm:200` 查询群成员

#### Scenario: 成员字段被服务端省略

- **WHEN** 成功的 `get_group_member_info` 响应省略 `member.shut_up_end_time`
- **THEN** tracker SHALL 将该次成员查询视为成功且当前 member mute 为 unmuted
- **AND** SHALL 不因字段省略把成功响应退化为永久 muted；只有请求失败或响应结构损坏时才保持既有 fail-closed 状态

#### Scenario: 成员状态查询绕过缓存

- **WHEN** tracker 在启动同步或主动刷新时查询 Bot 自身成员信息
- **THEN** SHALL 向 `get_group_member_info` 传入 `no_cache=true`
- **AND** SHALL 不因服务端返回过期缓存而把当前成员禁言误判为 unmuted

#### Scenario: 个人禁言 TTL 到期

- **WHEN** 成员查询或 `group_mute` 事件得到未来的 `shut_up_end_time`，且本地时间达到该截止时间
- **THEN** member mute SHALL 自动更新为 `unmuted`
- **AND** SHALL 不依赖新的 Milky 查询或 `duration=0` 事件才能恢复群消息处理

## ADDED Requirements

### Requirement: 热授权群在首次获准入站时准备状态

管理命令 SHALL 不查询来源群或目标群状态，新增具体规则或 group:* 不以状态查询为保存或发布前提。获准入站群在首次使用尚未准备的状态前 MUST 确认归属并查询 Bot 成员信息；仅在通过自身与白名单检查后查询，不扫描通配符对应的全部群。查询完成后 SHALL 重新检查当前授权与撤销代次，删除后重新添加也不得复活查询前的旧消息。

准备 SHALL 遵守既有冷却、并发限制和取消语义。未知、失败或确认禁言状态 SHALL 阻止当前普通消息进入 Will、缓冲和宿主；不得撤销已经保存的白名单。查询期间更新的禁言事件 MUST 被保留，旧响应不得覆盖新事实。移除授权 SHALL 保留既有出站仍需的群状态。

#### Scenario: 新增群首次入站

- **WHEN** 群规则已在线生效，该群首次收到获准入站的消息且状态尚未准备
- **THEN** 系统 SHALL 确认归属并准备该群状态，通过禁言门禁后继续处理
- **AND** 查询失败或禁言 SHALL 拒绝该消息，保留已保存规则

#### Scenario: 新增群通配符

- **WHEN** core 允许的调用者添加 group:*
- **THEN** 系统 SHALL 不查询群列表或成员即可保存并应用字面规则
- **AND** 后续各群首次获准入站 SHALL 独立准备，不批量扫描全部群

#### Scenario: 查询期间撤销后重新添加

- **WHEN** 普通消息等待群状态查询期间，其会话授权被撤销后重新添加
- **THEN** 当前消息 SHALL 因撤销代次变化而被拒绝
- **AND** SHALL 不累计 Will、缓冲或进入宿主

#### Scenario: 查询期间收到禁言事件

- **WHEN** 群状态准备期间收到该群的成员或全体禁言事件
- **THEN** 查询完成后的快照 SHALL 保留更新的事件事实
- **AND** SHALL 不因旧查询返回而把新禁言解释为可发言

#### Scenario: 管理命令不准备群状态

- **WHEN** core 允许 list、add、del 或 remove，来源或目标群状态未知或已禁言
- **THEN** 管理操作 SHALL 不执行状态查询或附加禁言提示
- **AND** 回执 SHALL 沿既有发送流程处理

#### Scenario: 刷新未知群不隐式建立跟踪

- **WHEN** 既有普通状态刷新请求指向尚未跟踪的群
- **THEN** 系统 SHALL 保持该刷新请求不成功，不据此隐式纳入跟踪或扩大白名单
- **AND** 获准入站 SHALL 可通过独立受控准备确认该群并建立状态

#### Scenario: 未跟踪群准备失败或被取消

- **WHEN** 群已确认归属并开始受控准备，但成员查询失败或操作被取消
- **THEN** 该群 SHALL 不被视为已确认可发言，当前普通消息不得继续处理
- **AND** 查询期间事件 SHALL 保留，后续准备重试 SHALL 遵守冷却与并发限制
