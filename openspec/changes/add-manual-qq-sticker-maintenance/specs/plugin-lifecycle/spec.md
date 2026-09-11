## ADDED Requirements

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
