## Purpose

为 Hermes 提供一个可发现、可启动、可重连且可停止的 Milky 平台适配器生命周期，
并确保连接初始化完成前不会把外部消息交给入站业务处理。

## ADDED Requirements

### Requirement: 唯一插件注册入口

适配器 MUST 只通过根插件入口注册到 Hermes，并且导入或注册过程不得建立网络连接或创建长期后台任务。

#### Scenario: Hermes 从目录发现插件

- **WHEN** Hermes 加载本仓库的插件目录
- **THEN** 它 SHALL 发现根入口提供的平台注册函数
- **AND** SHALL NOT 因另一个兼容模块或文档入口重复注册同一个平台

#### Scenario: 注册阶段不访问 Milky

- **WHEN** Hermes 调用平台注册函数
- **THEN** 函数 SHALL 只读取上下文、解析配置并组装依赖
- **AND** 在生命周期启动前 SHALL NOT 发起 Milky HTTP/SSE 请求

### Requirement: 初始化顺序保护消息入口

适配器 MUST 在允许普通消息进入入站处理前完成登录身份确认和群禁言初始同步。

#### Scenario: 初始同步完成后开始消费消息

- **WHEN** 适配器建立连接并完成登录信息、群列表和自身群成员状态同步
- **THEN** 它 SHALL 才开始将 `message_receive` 事件交给入站流水线

#### Scenario: 初始同步失败

- **WHEN** 登录信息或必要的初始状态同步失败
- **THEN** 适配器 SHALL 保持消息入口未就绪
- **AND** SHALL 报告可分类的启动或传输错误

### Requirement: 冷启动身份和群禁言扫描结果可观测

冷启动完成登录信息读取后 MUST 使用英文日志记录 Bot 的 `uid` 和 `nickname`；`uid` 和被记录的群 ID
MUST 只保留前后三位并将中间部分替换为 `*`。群禁言扫描逐群日志 MUST 只记录确认被禁言的群，
并使用英文日志给出 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 汇总计数；
未禁言、全体禁言未知和查询失败的群不得逐群打印。扫描仍只处理
`MILKY_ALLOWED_CHATS` 中的 `group:<id>`；
白名单为空时沿用“允许所有群”的语义，`dm:<id>` 不得触发群禁言扫描。

#### Scenario: 冷启动打印身份和扫描结果

- **WHEN** 登录身份和群列表同步成功，且白名单包含一个群会话和一个私聊会话
- **THEN** 日志 SHALL 使用英文显示中间脱敏的 `uid`、`nickname` 和确认禁言群的 member/whole 状态
- **AND** 无法通过 Milky 初始 Action 确认的 whole 状态 SHALL 计入汇总的 `unknown`
- **AND** 扫描汇总 SHALL 显示 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown`
- **AND** SHALL 不查询白名单外的群或因私聊白名单项查询群成员

#### Scenario: 空白名单保持全群语义

- **WHEN** `MILKY_ALLOWED_CHATS` 为空且群列表返回多个群
- **THEN** 群禁言扫描 SHALL 查询群列表中的每个群
- **AND** 扫描汇总 SHALL 显示实际扫描数量

### Requirement: 生命周期停止和重连不复制状态

适配器 MUST 在停止时释放事件消费者、HTTP 响应、请求、定时器和状态刷新任务；重连 MUST 不恢复断线期间未知丢失的消息、wait buffer 或 Will 分数。

#### Scenario: 重复停止

- **WHEN** 已停止的适配器再次收到停止请求
- **THEN** 它 SHALL 安全返回
- **AND** SHALL NOT 继续调用 Hermes 或 Milky

#### Scenario: SSE 断线后重连

- **WHEN** 事件流断线并建立新的连接
- **THEN** 适配器 SHALL 使用新的事件流继续消费可见事件
- **AND** SHALL 保留去重保护但 SHALL NOT 假设服务端补发断线期间事件或恢复进程内会话策略状态
