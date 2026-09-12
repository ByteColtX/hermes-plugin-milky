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

### Requirement: 人工贴纸 store 必须懒加载并由生命周期拥有

贴纸维护 SHALL 使用独立的 `stickers.db` 和 plugin-data 下固定的 `stickers/inbox/`、
`stickers/library/`、`stickers/junk/`。注册、普通连接和 SSE 消费阶段 MUST 不创建贴纸目录、打开
贴纸数据库、扫描图片、调用视觉服务或创建脱离命令的后台任务；有效维护命令结束后 SHALL 关闭本次
操作的 store，disconnect/reload SHALL 保留已提交条目和文件。

#### Scenario: 注册和连接无贴纸副作用

- **WHEN** Hermes 注册插件或 Milky adapter 完成普通连接
- **THEN** 贴纸目录和数据库 SHALL 保持懒加载
- **AND** 普通消息、系统事件和 Will SHALL 不触发 add、reanalyze 或其他贴纸操作

#### Scenario: disconnect 保留贴纸数据

- **WHEN** 已提交贴纸后 adapter disconnect 或插件 reload
- **THEN** 本次打开的贴纸资源 SHALL 被关闭
- **AND** 下一次显式维护命令 SHALL 能读取已提交的元数据和 library 文件

### Requirement: 贴纸库必须懒加载、可关闭并跨重载保留

贴纸数据库和库目录 SHALL 只在第一次有效贴纸维护命令需要时懒加载；插件导入、根 `register(ctx)` 和普通 Milky 连接初始化 SHALL 不读取 inbox、不打开贴纸数据库、不扫描库文件、不调用视觉能力或创建贴纸后台任务。适配器停止和插件卸载 SHALL 关闭贴纸库资源，但 SHALL 保留已经成功提交的持久化文件和元数据供下一次加载使用。

#### Scenario: 注册阶段无贴纸副作用

- **WHEN** Hermes 导入插件并调用根 `register(ctx)`
- **THEN** 插件 SHALL 只注册命令、配置和生命周期绑定
- **AND** SHALL 不创建贴纸条目、不读取图片、不打开数据库或启动贴纸任务

#### Scenario: 普通连接不触发扫描

- **WHEN** Milky adapter 完成登录、群状态同步并开始消费 SSE
- **THEN** 贴纸库 SHALL 保持未加载，除非此时正在处理显式贴纸维护命令
- **AND** 普通 `message_receive`、系统事件和 Will SHALL 不触发贴纸维护

#### Scenario: 停止后重载保留已提交数据

- **WHEN** 贴纸条目已成功提交后发生 adapter disconnect、插件卸载或进程重载
- **THEN** 贴纸库资源 SHALL 被关闭或解除绑定
- **AND** 下一次有效命令 SHALL 能读取之前已提交的条目，不得清空或重建为另一份库

#### Scenario: 关闭或加载失败

- **WHEN** 贴纸库关闭、迁移或首次加载失败
- **THEN** 维护命令 SHALL 返回固定 `storage_error` 或 `unsupported`
- **AND** 失败 SHALL 不阻塞普通 SSE 消费、普通 Hermes handoff 或其他出站能力
