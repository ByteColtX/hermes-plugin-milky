## MODIFIED Requirements

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

- **WHEN** Hermes 调用根插件入口且 `skills/qq-reference/SKILL.md` 存在
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

## ADDED Requirements

### Requirement: bundled QQ reference skill 按插件命名空间只读提供

插件 MUST 提供一个名为 `qq-reference` 的 bundled skill 模板，用于承载基础 CQ-compatible
语法之外的全部 NapCat 文档 CQ 类型、各类型的 Milky 转换状态、转换失败时的原样 text
fallback、Milky 映射、QQ 工具说明和待补充项。该 skill MUST 通过插件命名空间按需加载，
且不得把仅能 fallback 的 CQ 码或未注册的 ToolSpec 描述为已具备原生执行能力。

#### Scenario: Agent 按需加载 QQ reference skill

- **WHEN** Agent 请求加载本插件的 QQ reference skill
- **THEN** Hermes SHALL 能以插件命名空间形式解析该 skill
- **AND** skill 内容 SHALL 包含全部文档 CQ 类型、当前转换状态、fallback 限制和明确的待补充项

#### Scenario: Skill 保持只读和命名空间隔离

- **WHEN** 插件被加载或多个插件提供同名 `qq-reference` skill
- **THEN** 本插件 skill SHALL 保持只读并使用自身命名空间
- **AND** SHALL 不覆盖用户全局或其他插件的同名 skill

#### Scenario: Skill 不替代 ToolSpec

- **WHEN** Agent 读取 QQ reference skill 中的工具说明
- **THEN** 工具可用性和参数校验 SHALL 仍以实际注册的 ToolSpec 为准
- **AND** skill SHALL 不通过文字说明扩大可调用的 Milky Action 范围，也不得把 text fallback 误称为原生 CQ 执行
