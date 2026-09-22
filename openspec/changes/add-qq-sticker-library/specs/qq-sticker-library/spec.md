## Purpose

在已交付的手动 QQ 贴纸维护库上增加安全、可恢复的自动收集和按会话可见性，使普通图片可以沉淀为可复用条目，同时不改变旧库和维护命令的既有行为。

## ADDED Requirements

### Requirement: 自动库必须兼容既有手动贴纸库

启用本能力后，既有手动条目、库文件、opaque `sticker_id`、人工字段覆盖、视觉基线、
`use_count`、`last_used_at` 和发送使用历史 MUST 保持可读且语义不变。现有
`/milky sticker add/list/edit/reanalyze/del/cleanup/reindex` MUST 继续遵守手动维护规范；
自动收集不得通过重复导入、重分析或默认重命名覆盖既有手动记录。

#### Scenario: 首次启用保留手动条目

- **WHEN** 已有手动贴纸库首次启用自动收集
- **THEN** 系统 SHALL 保留已有条目、文件、ID、人工覆盖和发送统计
- **AND** SHALL 不扫描历史消息、不重复视觉分析已有文件或创建重复可见条目

#### Scenario: 手动维护继续有效

- **WHEN** 操作者执行既有 `sticker add`、`edit`、`reanalyze`、`del`、`cleanup` 或 `reindex`
- **THEN** 系统 SHALL 按手动维护契约处理
- **AND** 自动条目的存在 SHALL 不改变 inbox、junk、字段级 source、原子提交和失败分类语义

#### Scenario: 自动重复命中手动条目

- **WHEN** 当前消息图片的 content ID 已对应完整的手动库条目
- **THEN** 自动收集 SHALL 返回或记录 `duplicate`
- **AND** SHALL 不覆盖手动字段、重新调用视觉能力或增加新的手动条目

### Requirement: 手动条目和自动条目必须具有明确的可见性

旧手动条目 MUST 保持现有插件级共享可见性，不得被追溯迁移为按会话条目。新自动条目默认
MUST 绑定当前已确认的 QQ 会话：friend 使用 `dm:<peer_id>`，group 使用 `group:<group_id>`；
只有启动配置显式启用 global 模式时，自动条目才可写入或读取 `global`。Agent Tool 不得
接受任意 `scope_key` 或发送目标。

#### Scenario: 自动条目按当前会话隔离

- **WHEN** 两个不同 QQ 会话收到相同且已判定合格的图片
- **THEN** 每个会话 SHALL 只能看到自己作用域中的自动条目和共享的旧手动条目
- **AND** 一个会话的自动分类、标签和使用统计 SHALL 不改变另一个会话的对应值

#### Scenario: global 未显式启用

- **WHEN** scope 配置缺失、非法或未明确启用 global
- **THEN** 自动条目 SHALL 使用当前确认的 dm/group scope
- **AND** SHALL 不写入或读取自动 `global` 条目

#### Scenario: 物理内容可以安全复用

- **WHEN** 不同作用域的自动条目引用相同图片 bytes
- **THEN** 系统 MAY 复用同一个受控 content-addressed 文件
- **AND** SHALL 保持各作用域的条目 ID、分类、标签和使用统计彼此隔离

### Requirement: 自动收集必须只接受高质量且可复用的图片

当前消息顶层图片只有在已由 Hermes media helper materialize、通过 PNG/JPEG/GIF/WebP、非空、
可读、大小和文件完整性校验，并经视觉能力确认 `class=sticker`、`quality=good`、
`reusable=true`、`privacy_risk=low` 时，才 MAY 创建自动条目。截图、新闻、聊天记录、文档、
二维码、海报、普通照片、低质量图片和拒绝标签 MUST 不入库。

#### Scenario: 反应图自动入库

- **WHEN** 当前顶层图片通过确定性校验，且视觉结果确认其为高质量可复用贴纸
- **THEN** 系统 SHALL 在当前自动 scope 创建条目
- **AND** SHALL 保存有界分类、标签和质量元数据
- **AND** SHALL 不要求用户或 Agent 先调用收藏工具

#### Scenario: 非贴纸图片被拒绝

- **WHEN** 图片被识别为截图、新闻、聊天截屏、文档、二维码、海报、普通照片或低质量内容
- **THEN** 系统 SHALL 返回或记录 `rejected`
- **AND** SHALL 不创建可搜索的 asset 或 entry

#### Scenario: 质量结果未知

- **WHEN** 视觉能力不可用、超时、返回 malformed、字段不完整或 privacy risk 为 unknown
- **THEN** 系统 SHALL 执行 `defer` 或 `classifier_unavailable`
- **AND** SHALL 清理未入库 staging
- **AND** SHALL 不降低门槛、不创建条目或报告自动收藏成功

### Requirement: 自动条目必须复用手动库的内容身份和可恢复文件边界

相同图片 bytes MUST 使用相同的 SHA-256 content ID；同一自动 scope 内相同 content ID MUST
最多对应一个可见自动条目。自动条目和旧手动条目引用的物理文件 MUST 位于 plugin-data 的
受控 library 内；文件写入、元数据提交和清理失败不得留下可见半条目或删除仍被其他条目引用的文件。

#### Scenario: 同一作用域重复自动收集

- **WHEN** 同一作用域两次收到完全相同且已判定合格的图片 bytes
- **THEN** 第二次操作 SHALL 返回或记录 `duplicate`
- **AND** SHALL 不增加第二份文件、条目、质量调用或使用统计

#### Scenario: 跨作用域复用内容

- **WHEN** 当前 scope 尚无条目但其他 scope 已有相同 content ID 的合格内容
- **THEN** 系统 MAY 建立当前 scope 的独立条目并复用已验证文件
- **AND** SHALL 不复制不必要的图片 bytes，也 SHALL 不复制其他 scope 的分类和统计

#### Scenario: 存储提交失败

- **WHEN** 临时文件写入、原子提交、数据库事务或引用检查失败
- **THEN** 系统 SHALL 返回或记录 `storage_error`
- **AND** SHALL 不报告 `created`、不暴露半条目且不影响普通 Hermes handoff

### Requirement: 查询、发送和纠错必须使用受限的当前可见条目

`sticker_categories`、`sticker_search`、`sticker_send` 和 `sticker_forget` MUST 只操作当前
已确认会话可见的条目；手动共享条目和当前自动 scope 条目可以组成查询结果。`sticker_search`
和 `sticker_send` MUST 沿用既有及 `add-sticker-search-and-id-send` 的 intent/emotion/tags、
opaque ID、当前目标和一次发送契约，不得从本 change 引入任意 `scope_key`、路径、URL、
`category/keyword/index` 目标参数。`sticker_forget` 只允许删除自动条目，手动条目仍由显式
`/milky sticker del` 管理。

#### Scenario: 查询不越过当前 scope

- **WHEN** 当前会话调用 categories 或 search
- **THEN** 结果 SHALL 只包含手动共享条目和当前自动 scope 的合法条目
- **AND** SHALL 不返回其他会话的自动分类、标签、统计或 opaque ID

#### Scenario: 发送复用现有出站边界

- **WHEN** Agent 选择当前可见条目调用 `sticker_send`
- **THEN** 系统 SHALL 只向当前已确认的 dm/group target 发送一次原始图片
- **AND** SHALL 复用既有本地文件大小、materialization、Action 错误分类和未知结果不重试边界

#### Scenario: 发送统计保持既有 claim 语义

- **WHEN** 有效条目已完成选择、文件校验并发起发送调用
- **THEN** 系统 SHALL 原子记录一次使用统计
- **AND** Milky 随后的成功、失败或未知状态 SHALL 不回滚该统计，也 SHALL 不触发重发

#### Scenario: Agent 忘记自动条目

- **WHEN** Agent 使用当前可见自动条目的 opaque ID 调用 `sticker_forget`
- **THEN** 系统 SHALL 只删除当前自动 scope 的 entry
- **AND** SHALL 保留手动条目、其他 scope 的 entry 和仍被引用的物理文件

#### Scenario: Agent 试图删除手动条目

- **WHEN** `sticker_forget` 的 ID 对应旧手动条目
- **THEN** 工具 SHALL 返回固定的 `unsupported` 或 `unauthorized`
- **AND** SHALL 不删除手动条目或库文件

### Requirement: 自动收集和手动维护必须安全降级且互不触发

自动收集失败、自动条目缺文件、数据库不兼容或清理异常 MUST 使用固定的
`unsupported`、`missing_file`、`classifier_unavailable`、`storage_error` 等分类；不得改变
手动命令、Milky SSE、Gate、Will、buffer、Hermes handoff 或既有发送状态。普通消息、关键词、
Will、Agent 输出和自动分类任务 MUST NOT 隐式触发 `/milky sticker add/edit/reanalyze/del/cleanup/reindex`。

#### Scenario: 自动旁路失败

- **WHEN** 自动 staging、视觉判定、作用域解析或 store 操作失败
- **THEN** 普通消息 SHALL 继续完成既有 Hermes handoff
- **AND** 系统 SHALL 不伪造收藏成功、不执行额外 Milky Action 或修改手动维护状态

#### Scenario: 手动命令不会触发自动收集

- **WHEN** command handler 收到显式 `/milky sticker add` 或 `reanalyze`
- **THEN** 系统 SHALL 只执行手动维护规范定义的固定目录和视觉流程
- **AND** SHALL 不把命令中的图片或库文件再次提交给当前消息自动收集旁路
