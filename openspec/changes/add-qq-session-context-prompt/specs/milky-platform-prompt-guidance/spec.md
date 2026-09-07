## MODIFIED Requirements

### Requirement: section 身份来自连接后的账号缓存

Milky QQ 操作指引 section MUST 从同一插件注册实例创建的 adapter 在 `connect()` 完成登录和必要初始状态同步后缓存的账号信息读取 `self_id` 与 `nickname`。该操作指引 section 的渲染 MUST 只读该缓存，MUST NOT 发起 Milky HTTP/SSE 请求、调用新的远端 Action 或从 session metadata、入站正文和配置猜测身份。新增的 QQ 会话介绍 section 与操作指引 section 分离；会话介绍可以读取已登记的本地安全资料快照，但不得改变操作指引 section 的身份来源。

#### Scenario: 连接成功后渲染真实身份

- **WHEN** `connect()` 完成账号登录信息确认和既有初始状态同步，并缓存有效的 QQ UID 与昵称
- **THEN** 新 session 的 Milky 操作指引 section 首行 SHALL 使用该缓存值渲染
- **AND** 渲染结果 SHALL 形如 `Your QQ uid is <decimal uid>, and your nickname is <nickname>.`
- **AND** 操作指引 section SHALL 使用缓存值而不是再次查询 Milky

#### Scenario: 初始同步失败时不伪造身份

- **WHEN** `connect()` 未完成或账号信息未被成功确认
- **THEN** 操作指引 section SHALL 不注入未知、默认或猜测的 UID/昵称
- **AND** SHALL 不因渲染操作指引 section 打开网络连接
- **AND** `platform_hint` SHALL 仍只提供其首句

#### Scenario: 已连接身份在 prompt 渲染期间保持只读

- **WHEN** Hermes 在同一 session 内重复构建或恢复已冻结的 system prompt
- **THEN** 操作指引 section SHALL 使用已缓存且已渲染的身份和文案
- **AND** SHALL 不触发账号信息重新获取或改变 Milky 连接、pipeline、Will 和出站生命周期

#### Scenario: 会话介绍不改变操作指引身份边界

- **WHEN** 当前 Milky chat 存在 group 或 friend 会话资料快照
- **THEN** 会话介绍 section MAY 渲染该快照
- **AND** 操作指引 section 的 QQ UID 和昵称 SHALL 仍只来自连接后的 Bot identity snapshot
- **AND** 两个 section SHALL 不互相覆盖或重复承载对方职责

### Requirement: 注册和降级保持 Milky 边界

QQ 操作指引 section 和 QQ 会话介绍 section（若宿主支持且资料可用）MUST 只由 Milky 根插件注册入口登记，不得修改 Hermes core、全局平台提示逻辑或其他平台的注册结果。section 注册阶段 MUST 遵守既有无网络、无 SSE 和无长期任务约束；会话介绍资料只能在通过 Gate/Will 的普通 trigger handoff 前由插件登记，不能在注册或 section callback 阶段查询远端。宿主不提供 section 注册 API 时，插件 MUST 安全跳过所有 section 登记并继续注册只含首句的 `platform_hint`，不得因兼容性探测抛出未处理异常。

#### Scenario: 注册阶段不产生连接副作用

- **WHEN** Hermes 调用 Milky 注册入口并提供 system prompt section 注册能力
- **THEN** 插件 SHALL 登记适用的操作指引和会话介绍 section
- **AND** SHALL NOT 调用 `get_login_info`、其他 Milky Action、SSE 或创建长期后台任务
- **AND** SHALL NOT 修改 Hermes core 文件或运行时逻辑

#### Scenario: 旧宿主缺少 section API

- **WHEN** Hermes 上下文没有 `register_system_prompt_section`
- **THEN** Milky SHALL 仍完成平台注册
- **AND** `platform_hint` SHALL 仍等于既定首句
- **AND** 插件 SHALL 不发送网络请求、不回退为包含完整操作指引或会话资料的旧 hint、也不抛出注册异常

#### Scenario: section callback 不访问远端资料

- **WHEN** Hermes 在新会话或 prompt rebuild 边界执行任一 Milky section callback
- **THEN** callback SHALL 只读取连接后的 Bot identity snapshot 或插件本地会话资料快照
- **AND** SHALL 不调用 `get_group_info`、`get_friend_info`、其他 Action、SSE 或文件系统

#### Scenario: 其他平台不受影响

- **WHEN** Hermes 同时加载 Milky 与其他 platform plugin
- **THEN** 只有 Milky 注册的 section SHALL 包含 QQ 操作指引或 QQ 会话介绍
- **AND** 其他平台的 `platform_hint`、system prompt section 和身份信息 SHALL 保持原有行为
