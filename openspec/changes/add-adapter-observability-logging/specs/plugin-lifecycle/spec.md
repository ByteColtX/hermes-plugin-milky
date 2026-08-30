## MODIFIED Requirements

### Requirement: 生命周期停止和重连不复制状态

适配器 MUST 在停止时释放事件消费者、HTTP 响应、请求、定时器和状态刷新任务；重连 MUST 不恢复断线期间未知丢失的消息、wait buffer 或 Will 分数。生命周期的开始、初始同步失败、ready、停止和组件关闭失败 SHALL 使用 Hermes-agent 风格的 `[Milky] ` 前缀和对应的 `info`、`warning` 或 `error` 级别记录；这些日志不得输出未脱敏身份、凭证、URL、正文或路径。组件关闭失败与 fatal error report 失败 SHALL 使用各自准确的 event name，不得以另一个生命周期终态替代。

#### Scenario: 重复停止

- **WHEN** 已停止的适配器再次收到停止请求
- **THEN** 它 SHALL 安全返回
- **AND** SHALL NOT 继续调用 Hermes 或 Milky
- **AND** SHALL 不重复输出同一停止状态的 lifecycle 日志

#### Scenario: SSE 断线后重连

- **WHEN** 事件流断线并建立新的连接
- **THEN** 适配器 SHALL 使用新的事件流继续消费可见事件
- **AND** SHALL 保留去重保护但 SHALL NOT 假设服务端补发断线期间事件或恢复进程内会话策略状态
- **AND** adapter lifecycle 日志 SHALL 与 event stream 的断连/重连日志保持阶段区分，不重复伪造 transport 事件

#### Scenario: 组件关闭和 fatal report 失败

- **WHEN** 生命周期清理某个组件失败，或 adapter 向 Hermes 报告 fatal error 的本地调用失败
- **THEN** 前者 SHALL 记录 `milky_adapter_component_close_failed`，后者 SHALL 记录 `milky_adapter_fatal_error_report_failed`
- **AND** 两者 SHALL 使用固定的组件字段或固定 reason，且不得输出异常正文、路径或凭证
- **AND** fatal report 失败 SHALL NOT 再伪造 component close 或第二条 connect failure 终态

### Requirement: 冷启动身份和群禁言扫描结果可观测

冷启动完成登录信息读取后 MUST 使用英文日志记录 Bot 的 `uid` 和 `nickname`；`uid` 和被记录的群 ID
MUST 只保留前后三位并将中间部分替换为 `*`。群禁言扫描逐群日志 MUST 只记录确认被禁言的群，
并使用英文日志给出 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 汇总计数；未禁言、
全体禁言未知和查询失败的群不得逐群打印。扫描仍只处理 `MILKY_ALLOWED_CHATS` 中的 `group:<id>`；
白名单为空时沿用“允许所有群”的语义，`dm:<id>` 不得触发群禁言扫描。动态身份、状态和统计值 SHALL
只通过统一的安全字段渲染，同一值不得在消息文本和结构化字段中重复作为两个同义字段输出。

#### Scenario: 冷启动打印身份和扫描结果

- **WHEN** 登录身份和群列表同步成功，且白名单包含一个群会话和一个私聊会话
- **THEN** 日志 SHALL 使用英文显示中间脱敏的 `uid`、`nickname` 和确认禁言群的 member/whole 状态
- **AND** 无法通过 Milky 初始 Action 确认的 whole 状态 SHALL 计入汇总的 `unknown`
- **AND** 扫描汇总 SHALL 显示 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown`，每个统计字段只出现一次
- **AND** SHALL 不查询白名单外的群或因私聊白名单项查询群成员

#### Scenario: 空白名单保持全群语义

- **WHEN** `MILKY_ALLOWED_CHATS` 为空且群列表返回多个群
- **THEN** 群禁言扫描 SHALL 查询群列表中的每个群
- **AND** 扫描汇总 SHALL 显示实际扫描数量

#### Scenario: 冷启动日志不重复身份和状态字段

- **WHEN** 冷启动需要显示 UID、nickname 或确认禁言群的 member/whole 状态
- **THEN** 每个值 SHALL 通过一个规范字段输出一次
- **AND** 日志 SHALL 不同时输出 `uid`/`self_id` 或 `group`/`group_id` 这类同义字段
