# Spec Delta

## MODIFIED Requirements

### Requirement: 唯一插件注册入口

适配器 MUST 只通过根插件入口注册到 Hermes，并且导入或注册过程不得建立网络连接、创建长期
后台任务或写入用户全局 skills 目录；根入口 MAY 在同一注册阶段登记插件自带的只读 skill。

插件 SHALL 另以 Hermes 声明式 Dashboard 扩展提供管理页面和受宿主保护的 API；该入口不注册第二个 QQ 平台，也不依赖 QQ 平台配置成功或连接就绪。两种入口的导入与注册 SHALL 均不联网、不打开图库、不创建维护任务或独立 Web 服务。

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

#### Scenario: 未配置时访问管理入口

- **WHEN** 用户已启用插件及其 Dashboard 扩展，但连接地址、凭证或策略尚不满足 QQ 启动条件
- **THEN** 管理页面 SHALL 仍能显示并修正配置
- **AND** QQ 平台 SHALL 继续拒绝不合法的启动，不提前开放消息或 SSE

#### Scenario: 普通 Gateway 不加载 Web 运行依赖

- **WHEN** 仅启动 Gateway 而未启用 Dashboard 服务
- **THEN** QQ 平台 SHALL 不要求加载 Web 页面、Web 运行依赖或维护 worker
- **AND** SHALL 保持唯一平台注册和既有连接初始化顺序

### Requirement: 人工贴纸 store 必须懒加载并由生命周期拥有

贴纸维护 SHALL 使用独立的 `stickers.db` 和 plugin-data 下固定的 `stickers/inbox/`、
`stickers/library/`、`stickers/junk/`。注册、普通连接和 SSE 消费阶段 MUST 不创建贴纸目录、打开
贴纸数据库、扫描图片、调用视觉服务或创建隐式后台任务；有效维护命令结束后 SHALL 关闭本次
操作的 store，disconnect/reload SHALL 保留已提交条目和文件。显式 Web 浏览 SHALL 仅只读打开已有库，缺库不创建；已授权 Web 维护 SHALL 按 Dashboard 生命周期打开并释放自己拥有的库资源和任务。命令、Web 与发送入口共享同一 profile 的持久库，资源关闭不得跨运行实例影响其他所有者。

#### Scenario: 注册和连接无贴纸副作用

- **WHEN** Hermes 注册插件或 Milky adapter 完成普通连接
- **THEN** 贴纸目录和数据库 SHALL 保持懒加载
- **AND** 普通消息、系统事件和 Will SHALL 不触发 add、reanalyze 或其他贴纸操作

#### Scenario: disconnect 保留贴纸数据

- **WHEN** 已提交贴纸后 adapter disconnect 或插件 reload
- **THEN** 本次打开的贴纸资源 SHALL 被关闭
- **AND** 下一次显式维护命令 SHALL 能读取已提交的元数据和 library 文件

### Requirement: 贴纸库必须懒加载、可关闭并跨重载保留

贴纸数据库和库目录 SHALL 在有效贴纸维护命令、既有显式贴纸工具或已授权的显式 Web 维护需要时按各自契约懒加载；显式 Web 浏览可只读访问已有库，但不得初始化或迁移缺失存储。插件导入、根 `register(ctx)` 和普通 Milky 连接初始化 SHALL 不读取 inbox、不打开贴纸数据库、不扫描库文件、不调用视觉能力或创建贴纸后台任务。适配器停止 SHALL 关闭自身拥有的贴纸库资源，Dashboard 停止或插件卸载 SHALL 按各自所有权停止任务并关闭资源；各入口 SHALL 保留已经成功提交的持久化文件和元数据供下一次加载使用。

#### Scenario: 注册阶段无贴纸副作用

- **WHEN** Hermes 导入插件并调用根 `register(ctx)`
- **THEN** 插件 SHALL 只注册命令、配置和生命周期绑定
- **AND** SHALL 不创建贴纸条目、不读取图片、不打开数据库或启动贴纸任务

#### Scenario: 普通连接不触发扫描

- **WHEN** Milky adapter 完成登录、群状态同步并开始消费 SSE
- **THEN** 贴纸库 SHALL 保持未加载，除非有效维护命令、既有显式贴纸工具或已授权显式 Web 操作已按各自生命周期打开图库
- **AND** 普通 `message_receive`、系统事件和 Will SHALL 不触发贴纸维护

#### Scenario: 停止后重载保留已提交数据

- **WHEN** 贴纸条目已成功提交后发生 adapter disconnect、插件卸载或进程重载
- **THEN** 对应实例拥有的贴纸库资源 SHALL 被关闭或解除绑定，不关闭其他实例仍拥有的资源
- **AND** 下一次有效命令或已授权 Web 操作 SHALL 能读取之前已提交的条目，不得清空或重建为另一份库

#### Scenario: 关闭或加载失败

- **WHEN** 贴纸库关闭、迁移或首次加载失败
- **THEN** 维护命令 SHALL 返回固定 `storage_error` 或 `unsupported`
- **AND** 失败 SHALL 不阻塞普通 SSE 消费、普通 Hermes handoff 或其他出站能力

#### Scenario: Web 只读访问与独立资源关闭

- **WHEN** Dashboard 浏览已有图库，随后 QQ adapter 断开
- **THEN** 浏览 SHALL 不创建、迁移或修改图库，且仍可使用 Dashboard 自身拥有的只读资源
- **AND** Dashboard 停止时 SHALL 关闭这些资源，保持已提交数据供后续显式操作使用

## ADDED Requirements

### Requirement: Dashboard 维护任务生命周期独立且可终止

Dashboard SHALL 仅在收到已授权的显式维护请求后启动有界任务；资源与任务属于创建时绑定的 profile 和 Dashboard 运行实例，不依赖活跃 QQ 会话。Dashboard 停止或插件卸载时 MUST 停止接收新任务，取消并等待可取消工作，关闭自身存储/文件资源；无法确认完成的工作 SHALL 保持中断或未知终态，不能被标为成功。QQ adapter 断开不得关闭另一个进程拥有的任务，Dashboard 维护失败不得改变 QQ 消息生命周期。

#### Scenario: 页面关闭与宿主停止

- **WHEN** 操作者关闭浏览器页面而 Dashboard 仍运行
- **THEN** 已接收任务 SHALL 继续由宿主内维护执行层拥有，并可重新查询
- **AND** Dashboard 停止时 SHALL 停止派发并释放所拥有资源，重启后将未完成任务标为 interrupted

#### Scenario: 未确认的分析不能自动重放

- **WHEN** 任务中断时存在无法确认结果的视觉请求
- **THEN** 系统 SHALL 保留已完成项与未确认项的区别
- **AND** SHALL 不在重启或页面重试后自动再次调用视觉或重新提交写入
