# Spec Delta

## ADDED Requirements

### Requirement: bundled skill 登记必须携带描述且失败可见

插件登记 bundled skill 时 MUST 从 SKILL.md frontmatter 读取 `description` 并随登记传入，使
宿主渲染的 skill 索引包含可读描述。读取失败或宿主不支持该参数时 MAY 退回仅登记路径，但
MUST NOT 静默跳过。宿主缺少 `register_skill` 或 skill 文件缺失时 MUST 记录固定分类告警，
且告警 MUST NOT 包含路径或文件内容。

#### Scenario: 登记带描述

- **WHEN** 插件登记 `skills/<name>/SKILL.md` 且 frontmatter 含 `description`
- **THEN** 登记调用 SHALL 携带该描述
- **AND** SHALL 不复制或改写用户全局 skills 目录

#### Scenario: 宿主不支持描述参数

- **WHEN** 宿主的 `register_skill` 不接受描述参数
- **THEN** 插件 SHALL 退回仅登记名称与路径
- **AND** SHALL NOT 因该参数抛出注册失败

#### Scenario: 缺少注册能力或文件

- **WHEN** 宿主没有 `register_skill`，或 skill 文件不存在
- **THEN** 插件 SHALL 记录固定分类告警
- **AND** 告警 SHALL NOT 包含本地路径、文件内容或凭证
