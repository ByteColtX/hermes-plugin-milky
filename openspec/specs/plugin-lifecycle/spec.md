# plugin-lifecycle Specification

## Purpose

为 Hermes 提供一个可发现、可启动、可重连且可停止的 Milky 平台适配器生命周期，
并确保连接初始化完成前不会把外部消息交给入站业务处理。

## Requirements

### Requirement: 唯一插件注册入口

适配器 MUST 只通过根插件入口注册到 Hermes，并且导入或注册过程不得建立网络连接、创建长期
后台任务或写入用户全局 skills 目录；根入口 MAY 在同一注册阶段登记插件自带的只读 skill。

#### Scenario: Hermes 从目录发现插件

- **WHEN** Hermes 加载本仓库的插件目录
- **THEN** 它 SHALL 发现根入口提供的平台注册函数
- **AND** SHALL NOT 因另一个兼容模块或文档入口重复注册同一个平台

#### Scenario: 注册阶段不访问 Milky

- **WHEN** Hermes 调用平台注册函数
- **THEN** 函数 SHALL 只读取上下文、解析配置并组装依赖
- **AND** 在生命周期启动前 SHALL NOT 发起 Milky HTTP/SSE 请求

#### Scenario: 注册阶段登记 bundled skill

- **WHEN** Hermes 调用根插件入口且 `skills/milky-qq-cq-reference/SKILL.md` 存在
- **THEN** 插件 SHALL 将该文件作为插件自带的只读 skill 登记
- **AND** SHALL 不复制或改写用户全局 skills 目录中的文件

### Requirement: 初始化顺序保护消息入口

适配器 MUST 在允许普通消息进入入站处理前完成登录身份确认和群禁言初始同步。

#### Scenario: 初始同步完成后开始消费消息

- **WHEN** 适配器建立连接并完成登录信息、群列表和自身群成员状态同步
- **THEN** 它 SHALL 才开始将 `message_receive` 事件交给入站流水线

#### Scenario: 初始同步失败

- **WHEN** 登录信息或必要的初始状态同步失败
- **THEN** 适配器 SHALL 保持消息入口未就绪
- **AND** SHALL 报告可分类的启动或传输错误

### Requirement: 生命周期停止和重连不复制状态

适配器 MUST 在停止时释放事件消费者、HTTP 响应、请求、定时器和状态刷新任务；重连 MUST
不恢复断线期间未知丢失的消息、wait buffer 或 Will 分数。

#### Scenario: 重复停止

- **WHEN** 已停止的适配器再次收到停止请求
- **THEN** 它 SHALL 安全返回
- **AND** SHALL NOT 继续调用 Hermes 或 Milky

#### Scenario: SSE 断线后重连

- **WHEN** 事件流断线并建立新的连接
- **THEN** 适配器 SHALL 使用新的事件流继续消费可见事件
- **AND** SHALL 保留去重保护但 SHALL NOT 假设服务端补发断线期间事件或恢复进程内会话策略状态

#### Scenario: 组件关闭和 fatal report 失败

- **WHEN** 生命周期清理某个组件失败，或 adapter 向 Hermes 报告 fatal error 的本地调用失败
- **THEN** 前者 SHALL 记录 `milky_adapter_component_close_failed`，后者 SHALL 记录 `milky_adapter_fatal_error_report_failed`
- **AND** 两者 SHALL 使用固定的组件字段或固定 reason，且不得输出异常正文、路径或凭证
- **AND** fatal report 失败 SHALL NOT 再伪造 component close 或第二条 connect failure 终态

### Requirement: 冷启动身份和群禁言扫描结果可观测

冷启动完成登录信息读取后 MUST 使用英文日志记录 Bot 的 `uid` 和 `nickname`；已登记的 `uid` 和被记录的群 ID
可以原样保留。群禁言扫描逐群日志 MUST 只记录确认被禁言的群，
并使用英文日志给出 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 汇总计数；未禁言、
全体禁言未知和查询失败的群不得逐群打印。扫描仍只处理 `MILKY_ALLOWED_CHATS` 中的 `group:<id>`；
白名单为空时沿用“允许所有群”的语义，`dm:<id>` 不得触发群禁言扫描。动态身份、状态和统计值 SHALL
只通过统一的安全字段渲染，同一值不得在消息文本和结构化字段中重复作为两个同义字段输出。

#### Scenario: 冷启动打印身份和扫描结果

- **WHEN** 登录身份和群列表同步成功，且白名单包含一个群会话和一个私聊会话
- **THEN** 日志 SHALL 使用英文显示原始的 `uid`、`nickname` 和确认禁言群的 member/whole 状态
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

### Requirement: Home channel 在插件生命周期中可被 Hermes 识别

当 `MILKY_HOME_CHANNEL` 配置有效时，插件 MUST 在不建立网络连接或长期后台任务的注册/配置发现阶段向 Hermes 提供 Milky home channel 元数据，并 MUST 注册 Milky 作为支持 home-channel cron delivery 的平台。该元数据 SHALL 与普通 adapter 的连接就绪状态和入站初始化顺序分离。

#### Scenario: 注册阶段暴露 home channel

- **WHEN** Hermes 发现 Milky plugin 且 `MILKY_HOME_CHANNEL` 已配置
- **THEN** Hermes SHALL 能将 Milky 识别为具有 home channel 的平台
- **AND** plugin 注册阶段 SHALL 不调用 Milky HTTP Action 或启动 SSE

#### Scenario: 配置变更只在下一次启动生效

- **WHEN** 进程启动后环境中的 `MILKY_HOME_CHANNEL` 被改变
- **THEN** 当前运行实例 SHALL 继续使用启动时解析的 home channel
- **AND** SHALL 不在运行中静默切换系统消息目标

#### Scenario: home channel 不跳过普通初始化

- **WHEN** `MILKY_HOME_CHANNEL` 已配置但 Milky 登录或必要状态同步尚未完成
- **THEN** 系统通知的 home target 元数据 MAY 已被 Hermes 发现
- **AND** 普通 `message_receive` SHALL 仍遵守既有初始化就绪门槛

### Requirement: bundled Milky QQ CQ reference skill 按插件命名空间只读提供

插件 MUST 提供一个名为 `milky-qq-cq-reference` 的 bundled skill 模板，用于承载 Milky QQ
Agent 出站 `at`、`reply`、`face` 和本地贴纸图片的 CQ-compatible 语法、入站 face placeholder
的中文名称索引以及明确的 fallback 限制。该 skill MUST 通过插件命名空间按需加载，且不得把
仅能 fallback 的 CQ 码或未注册的 ToolSpec 描述为已具备原生执行能力。

#### Scenario: Agent 按需加载 Milky QQ CQ reference skill

- **WHEN** Agent 请求加载本插件的 Milky QQ CQ reference skill
- **THEN** Hermes SHALL 能以插件命名空间形式解析该 skill
- **AND** skill 内容 SHALL 包含确认支持的 CQ 类型、face 映射索引、fallback 限制和 ID 来源约束

#### Scenario: Skill 保持只读和命名空间隔离

- **WHEN** 插件被加载或多个插件提供同名 `milky-qq-cq-reference` skill
- **THEN** 本插件 skill SHALL 保持只读并使用自身命名空间
- **AND** SHALL 不覆盖用户全局或其他插件的同名 skill

#### Scenario: Skill 不替代 ToolSpec

- **WHEN** Agent 读取 Milky QQ CQ reference skill 中的能力说明
- **THEN** 工具可用性和参数校验 SHALL 仍以实际注册的 ToolSpec 为准
- **AND** skill SHALL 不通过文字说明扩大可调用的 Milky Action 范围，也不得把 text fallback 误称为原生 CQ 执行
