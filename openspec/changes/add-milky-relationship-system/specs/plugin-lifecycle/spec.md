## ADDED Requirements

### Requirement: 关系持久化必须遵守插件数据生命周期

关系系统 MUST 使用 Hermes 官方插件持久化边界保存数据，数据目录必须与插件安装目录分离，
并在插件更新、卸载代码或 Gateway 重启后保留。关系数据库和 repository MUST 懒加载，注册/导入
阶段不得创建网络连接、SSE、长期任务或依赖当前 Milky 身份的关系记录。连接关闭时 MUST
释放关系数据库连接和关系维护任务；重复 close MUST 安全返回。

#### Scenario: 注册阶段不初始化关系业务

- **WHEN** Hermes 调用根 `register(ctx)`
- **THEN** 插件 SHALL 只组装关系服务依赖和静态 ToolSpec
- **AND** SHALL 不打开关系数据库、不访问 Milky、不创建关系主体或长期 scheduler

#### Scenario: Gateway 重启保留关系

- **WHEN** Gateway 重启后插件重新连接，且 Hermes 插件数据目录可用
- **THEN** 已提交的关系状态、事件幂等记录、commitment 和 flags SHALL 可继续读取
- **AND** 重连 SHALL 不把关系恢复为初始值或重复播放断线前事件

#### Scenario: 停止释放关系资源

- **WHEN** adapter disconnect 被调用一次或多次
- **THEN** 关系 repository、维护任务和底层连接 SHALL 最多关闭一次
- **AND** 关闭后新的关系写入 SHALL 返回 `storage_unavailable`，不得偷偷创建第二个连接

### Requirement: 关系存储版本必须可迁移且失败时保持安全降级

关系表结构 MUST 带有 schema version 或等价迁移标记；启动或首次使用时只能执行预先声明、
可事务回滚的迁移。迁移失败、版本未知或数据校验失败时，关系写入 MUST 停止并返回稳定存储
错误；不得删除旧数据、静默重建空库或把空库报告为已迁移成功。

#### Scenario: 已知版本迁移

- **WHEN** 关系库处于旧的受支持 schema version
- **THEN** 系统 SHALL 在事务中完成声明的向前迁移
- **AND** SHALL 保留可读的关系状态和事件账本

#### Scenario: 未知版本拒绝写入

- **WHEN** 关系库标记为插件不认识的未来版本
- **THEN** 关系服务 SHALL 返回 `schema_incompatible`
- **AND** SHALL 不写入、删除或重置任何关系主体
- **AND** 既有入站消息 SHALL 继续遵守关系旁路失败隔离规则
