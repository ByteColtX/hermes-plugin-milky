## MODIFIED Requirements

### Requirement: 生命周期停止和重连不复制状态

适配器 MUST 在停止时释放事件消费者、HTTP 响应、请求、定时器和状态刷新任务；重连 MUST
不恢复断线期间未知丢失的消息、wait buffer 或 Will 分数。组件清理和 fatal error report 失败
SHALL 保留各自的错误分类，并使用 `event=milky.lifecycle` 的独立结果诊断；诊断不得输出
异常正文、路径或凭证，也不得改变其余组件的清理、连接状态或错误结果。

#### Scenario: 重复停止

- **WHEN** 已停止的适配器再次收到停止请求
- **THEN** 它 SHALL 安全返回
- **AND** SHALL NOT 继续调用 Hermes 或 Milky

#### Scenario: SSE 断线后重连

- **WHEN** 事件流断线并建立新的连接
- **THEN** 适配器 SHALL 使用新的事件流继续消费可见事件
- **AND** SHALL 保留去重保护但 SHALL NOT 假设服务端补发断线期间事件或恢复进程内会话策略状态
- **AND** 运维日志 SHALL 能区分断线、重连和重新就绪，不得伪造消息恢复

#### Scenario: 组件关闭和 fatal report 失败

- **WHEN** 生命周期清理某个组件失败，或 adapter 向 Hermes 报告 fatal error 的本地调用失败
- **THEN** 前者和后者 SHALL 保留各自的错误分类并记录独立的 `event=milky.lifecycle` 诊断
- **AND** 两者 SHALL 只使用固定组件、分类、异常类型名或 reason，且不得输出异常正文、路径或凭证
- **AND** fatal report 失败 SHALL NOT 再伪造 component close 或第二条 connect failure 终态

### Requirement: 冷启动身份和群禁言扫描结果可观测

冷启动完成登录信息读取后 MUST 使用 `event=milky.lifecycle` 记录 ready 所需的必要身份关联
信息；已登记的 `uid` 和被记录的群 ID 可以原样保留，但昵称不作为常规运维字段。群禁言扫描
MUST 使用日志给出 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 汇总计数；
未禁言、全体禁言未知和查询失败的群不得逐群打印，除非 DEBUG 诊断确实需要安全的状态变更。
扫描仍只处理 `MILKY_ALLOWED_CHATS` 中的 `group:<id>`；白名单为空时沿用“允许所有群”的语义，
`dm:<id>` 不得触发群禁言扫描。动态身份、状态和统计值 SHALL 只出现一次，不得写入原始异常或正文。

#### Scenario: 冷启动打印身份和扫描结果

- **WHEN** 登录身份和群列表同步成功，且白名单包含一个群会话和一个私聊会话
- **THEN** 日志 SHALL 记录 ready、必要的 uid 和确认禁言群状态，以及 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 汇总
- **AND** 无法通过 Milky 初始 Action 确认的 whole 状态 SHALL 计入汇总的 `unknown`
- **AND** SHALL 不记录 nickname、响应正文、请求 body 或未确认的群状态

#### Scenario: 空白名单保持全群语义

- **WHEN** `MILKY_ALLOWED_CHATS` 为空且群列表返回多个群
- **THEN** 群禁言扫描 SHALL 查询群列表中的每个群
- **AND** 扫描汇总 SHALL 显示实际扫描数量

#### Scenario: 冷启动日志不重复身份和状态字段

- **WHEN** 冷启动需要显示 UID 或确认禁言群的 member/whole 状态
- **THEN** 每个值 SHALL 通过一个规范字段输出一次
- **AND** 日志 SHALL 不同时输出 `uid`/`self_id` 或 `group`/`group_id` 这类同义字段
