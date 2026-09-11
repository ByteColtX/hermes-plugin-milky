## ADDED Requirements

### Requirement: Sticker storage and automatic classification MUST be lazy and lifecycle-owned

Sticker library 的持久化资源和自动分类能力 MUST 在首次需要访问 library 或处理当前图片时懒加载，且必须位于 Hermes plugin data 和已确认的 Hermes media 能力边界内。插件注册阶段 SHALL 不打开长期数据库连接、不扫描 sticker 文件、不读取图片、不调用视觉服务或创建常驻分类任务。插件卸载、断开或 reload 时 MUST 关闭数据库、取消自动分类任务、清理未入库 staging；卸载或更新代码不得删除已保存的 library 数据。

#### Scenario: Plugin registration without sticker use

- **WHEN** Hermes 只加载并注册 Milky plugin，但没有进入图片处理或调用 sticker tool/维护命令
- **THEN** 插件 SHALL 不发起网络、图片读取、视觉调用或长期数据库操作
- **AND** SHALL 仍能完成正常 Milky platform registration

#### Scenario: Automatic task is cancelled on unload

- **WHEN** plugin unload、adapter close 或 Hermes reload 发生时仍有视觉判定任务
- **THEN** 系统 SHALL 取消未完成任务并清理未入库 staging
- **AND** SHALL 不把取消报告为收藏成功
- **AND** 已确认写入的 library 数据 SHALL 保持可读

#### Scenario: Plugin reload preserves library

- **WHEN** 插件 reload 或 Hermes 重启后重新加载 sticker 功能
- **THEN** 已确认的 library 条目和文件 SHALL 保持可读
- **AND** 不得因为重新注册而重建、清空或重复导入条目

### Requirement: Storage and classifier degradation MUST fail closed without corrupting message handoff

数据库无法打开、schema 不兼容、视觉能力不可用、分类结果 malformed、文件缺失或 store 操作异常时，自动收集 SHALL 跳过或返回可分类的 `unsupported`、`malformed`、`missing_file`、`classifier_unavailable` 或 `storage_error`，不得报告创建、发送或清理成功。storage 或 classifier 旁路失败不得改变既有 Milky 入站 Gate/Will/Hermes handoff；发送失败不得增加使用统计。

#### Scenario: Database unavailable during automatic collection

- **WHEN** 当前图片满足基础格式要求但 library database 不可用
- **THEN** 自动收集 SHALL 返回 `storage_error` 或 `unsupported`
- **AND** SHALL 不伪造收藏成功
- **AND** 当前消息 SHALL 继续完成既有 Hermes handoff

#### Scenario: Vision classifier unavailable

- **WHEN** Hermes 视觉能力不可用、超时或返回无法解析的结果
- **THEN** 自动收集 SHALL 删除未入库 staging 并跳过该图片
- **AND** SHALL 不降低质量门槛、不把图片当作合格 sticker

#### Scenario: Referenced file is missing

- **WHEN** library metadata 引用的图片文件不存在
- **THEN** `sticker_send` SHALL 返回 `missing_file`
- **AND** SHALL 不调用 Milky send Action
- **AND** cleanup SHALL 保留该 metadata 供运维修复或报告
