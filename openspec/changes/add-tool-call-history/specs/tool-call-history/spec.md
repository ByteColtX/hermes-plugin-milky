# Spec Delta

## Purpose

让操作者能够在本地持久化历史中查看 Milky/QQ 工具的调用方式、发生时间和运行统计，同时遵守插件已有的日志、响应交付与 profile 隔离边界。

## ADDED Requirements

### Requirement: 只观察本插件声明的 Milky/QQ 工具

插件 MUST 只为自身 manifest 声明的 Milky/QQ 工具保存调用记录。记录通过 Hermes 的调用后观察事件产生；观察和持久化 SHALL 不改变工具参数、结果、调用顺序或是否执行，也 SHALL NOT 注册审批或拦截行为。

#### Scenario: 记录已声明的 Milky 工具

- **WHEN** 本插件声明的任一 Milky/QQ 工具触发调用后观察事件
- **THEN** 系统 SHALL 为该次观察创建一条历史记录
- **AND** SHALL 不要求该调用来自普通 QQ 消息流程

#### Scenario: 其他工具或非观察事件

- **WHEN** Hermes 的其他工具触发相同观察事件，或本插件收到其他工具事件
- **THEN** 系统 SHALL 不将其写入 Milky/QQ 工具历史
- **AND** SHALL 不通过审批或拦截事件改变调用结果

### Requirement: 记录调用时间、耗时和受限状态

每条记录 MUST 保存工具名、带时区的观察时间、Hermes 提供的非负耗时，以及归一化的观察状态。观察时间表示插件收到调用完成事件的时间；状态只描述 Hermes 对工具调用的观察结果，不代表 QQ 远端业务成功。

#### Scenario: 完成调用被观察

- **WHEN** 插件收到有工具名和有效耗时的调用完成观察事件
- **THEN** 历史 SHALL 保存 UTC 观察时间、耗时和工具名
- **AND** 状态 SHALL 归一化到受支持的固定分类，未知值 SHALL 显示为 `unknown`

#### Scenario: 状态无法证明 QQ 业务结果

- **WHEN** Hermes 将一个 Tool 结果标为 `ok` 或 `error`
- **THEN** 历史和统计 SHALL 只将其展示为 Hermes 观察状态
- **AND** SHALL NOT 将其解释为 QQ 已执行成功、拒绝或产生特定业务结果

### Requirement: 参数摘要按工具白名单保留用法信息

记录 MUST 为每个声明的工具生成独立的参数摘要白名单，以便查看实际调用目标和选项。摘要 MAY 保存必要的数值 QQ ID、序号、数量、布尔选项和贴纸 ID；非白名单字段 SHALL 只标示字段是否提供，不保存原值。

#### Scenario: 查看工具的目标和选项

- **WHEN** 操作者查看一条包含白名单参数的工具记录
- **THEN** 页面 SHALL 显示该工具名、字段名及白名单允许的字段值
- **AND** SHALL 不把参数摘要伪装成可重新执行的请求

#### Scenario: 调用携带非白名单内容

- **WHEN** 参数中包含自由文本、资源标识、URL、路径、凭证、媒体引用、文件内容或未知字段
- **THEN** 记录 SHALL 不保存这些字段的原值
- **AND** 原始参数对象 SHALL NOT 被持久化

### Requirement: 原始结果和 hook 诊断内容不进入历史

工具调用历史 MUST NOT 持久化完整 Tool 结果、错误正文、异常文本或 middleware trace。若观察事件提供状态类型，系统 MAY 在固定白名单内保存规范化类型；未知类型 SHALL 归为 `unknown`。

#### Scenario: Milky Tool 返回不透明响应

- **WHEN** Milky/QQ 工具返回任意远端响应体或下载链接
- **THEN** 历史 SHALL 只保存观察状态和参数摘要
- **AND** SHALL NOT 复制或解析远端响应体来生成历史记录

#### Scenario: 观察事件带错误文本或中间件轨迹

- **WHEN** 调用后事件包含自由文本错误、参数错误详情或 middleware trace
- **THEN** 历史 SHALL 不保存这些内容
- **AND** 工具的原有结果 SHALL 保持不变

### Requirement: 历史保留和统计有界

每个 profile 的记录 SHALL 独立持久化，并在重启后可查询。系统 MUST 为历史设置有界保留期和数量上限，并提供与当前筛选范围一致的调用总数、按工具/观察状态计数和耗时统计。

#### Scenario: 查询统计范围

- **WHEN** 操作者按时间、工具或观察状态筛选记录
- **THEN** 汇总计数和耗时统计 SHALL 只基于同一筛选范围
- **AND** 不同 profile 的记录 SHALL 不得混入统计

#### Scenario: 记录达到保留上限

- **WHEN** profile 的记录超过 30 天或 10,000 条中的任一上限
- **THEN** 系统 SHALL 自动清理超出保留范围的最早记录
- **AND** SHALL 不影响其他 profile 的记录

#### Scenario: 调用观察未能持久化

- **WHEN** Hermes 未触发观察事件，或插件 hook 超时/持久化失败
- **THEN** 工具调用 SHALL 继续遵守其原有结果和执行语义
- **AND** 系统 SHALL 不宣称历史覆盖了所有已发起的调用
