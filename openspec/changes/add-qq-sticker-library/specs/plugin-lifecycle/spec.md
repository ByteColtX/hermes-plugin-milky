## ADDED Requirements

### Requirement: Sticker storage and automatic classification MUST be lazy and lifecycle-owned

贴纸库访问、手动维护、Agent Tool 查询和自动分类能力 MUST 在首次需要时懒加载，且必须位于 Hermes
plugin-data 和已确认的 Hermes media 能力边界内。插件注册阶段 SHALL 不打开长期数据库连接、不扫描
贴纸文件、不读取图片、不调用视觉服务或创建常驻分类任务。每次手动命令和一次性 Tool 调用完成后，
其短生命周期 store 资源 SHALL 关闭；插件卸载、适配器断开或 reload 时 MUST 取消自动分类任务、清理
未入库 staging 并等待插件拥有的任务结束。卸载或更新代码不得删除已保存的手动或自动 library 数据。

#### Scenario: Plugin registration without sticker use

- **WHEN** Hermes 只加载并注册 Milky plugin，但没有进入图片处理或调用 sticker tool/维护命令
- **THEN** 插件 SHALL 不发起网络、图片读取、视觉调用或数据库长期操作
- **AND** SHALL 仍能完成正常 Milky platform registration

#### Scenario: Manual command owns a short-lived store

- **WHEN** command handler 收到显式贴纸维护命令
- **THEN** 系统 SHALL 只在该命令需要时打开贴纸 store
- **AND** 命令完成、失败或取消后 SHALL 关闭连接并释放本次命令资源

#### Scenario: Automatic task is cancelled on unload

- **WHEN** plugin unload、adapter close 或 Hermes reload 发生时仍有视觉判定任务
- **THEN** 系统 SHALL 取消未完成任务、等待插件拥有的任务结束并清理未入库 staging
- **AND** SHALL 不把取消报告为收藏成功
- **AND** 已确认写入的手动和自动 library 数据 SHALL 保持可读

#### Scenario: Plugin reload preserves library

- **WHEN** 插件 reload 或 Hermes 重启后重新加载 sticker 功能
- **THEN** 已确认的手动和自动条目及其文件 SHALL 保持可读
- **AND** 不得因为重新注册而重建、清空或重复导入条目

### Requirement: Existing manual storage semantics MUST survive library extension

自动 library 扩展 MUST 使用增量 schema 和可恢复迁移，保留既有手动条目、`sticker_id`、人工字段来源、
`sticker_files` 技术索引、发送使用统计以及 `inbox/library/junk` 目录语义。旧手动条目不得被默认
改成按会话隔离；迁移失败或版本未知时 SHALL 保留原数据并返回固定错误分类。

#### Scenario: Legacy database migrates conservatively

- **WHEN** 已有手动 `stickers.db` 首次加载自动 library schema
- **THEN** 系统 SHALL 保留旧条目、库文件、人工覆盖、ID 和统计
- **AND** SHALL 不重复扫描历史消息、不重复导入库文件或删除旧目录

#### Scenario: Unsupported schema does not destroy data

- **WHEN** schema 版本缺失、未知或迁移事务失败
- **THEN** 系统 SHALL 返回 `unsupported` 或 `storage_error`
- **AND** SHALL 不清空、覆盖或部分发布手动或自动条目

### Requirement: Storage and classifier degradation MUST fail closed without corrupting message handoff

数据库无法打开、schema 不兼容、视觉能力不可用、分类结果 malformed、文件缺失或 store 操作异常时，
自动收集 SHALL 跳过或返回可分类的 `unsupported`、`malformed`、`missing_file`、
`classifier_unavailable` 或 `storage_error`，不得报告创建、发送或清理成功。storage 或 classifier
旁路失败不得改变既有 Milky 入站 Gate/Will/Hermes handoff；发送失败不得因未知结果重发，使用统计
仍按既有“发起发送调用后 claim”语义处理。

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
