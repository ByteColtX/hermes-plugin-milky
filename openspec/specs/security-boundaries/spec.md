# security-boundaries Specification

## Purpose

定义 Milky 适配器的业务日志、QQ Tool 原始结果、Hermes 资源入口和仓库合成数据边界。

## Requirements

### Requirement: 源码和测试资料只能使用合成信息

源码、测试、fixture 和文档 MUST 只使用合成身份、合成协议值、占位正文和占位资源；不得保存真实 token、真实身份、敏感正文、真实媒体引用、媒体字节或 live 响应。

#### Scenario: 测试需要真实协议字段形状

- **WHEN** 测试需要覆盖 Milky 响应或事件字段
- **THEN** 测试 SHALL 使用字段形状等价但值为合成数据的 fixture
- **AND** SHALL NOT 保存 live 响应、真实身份、正文或媒体内容

#### Scenario: 文档展示运行时配置

- **WHEN** 文档需要展示配置、请求或资源示例
- **THEN** 示例 SHALL 使用占位符和合成值
- **AND** SHALL NOT 包含可用凭证、真实身份、真实路径或真实媒体引用

### Requirement: 业务日志和 Tool 调用日志保留原始业务值

运行时日志 MUST NOT 对必要的业务关联 ID、chat key、message ID 或结果分类执行会破坏关联的
掩码、改名或字段删除；这些值只在确实有助于运维关联时记录。已注册 Tool 的日志 SHALL 只
包含 Tool 名称、Action、结果分类、已知 HTTP 状态码、耗时和必要的低敏关联 ID，不得包含
Tool 原始入参、远端结果投影或为生成日志而复制的业务对象。该边界 MUST 排除 token、Authorization
header、原始响应 body、下载 URL、头像或其他媒体 URL、本地路径、文件内容以及自由文本理由。
Tool 调用方收到成功结果时，仍 SHALL 取得现有 Tool raw envelope 契约规定的完整协议结果；
日志实现不得改变交付结果。

#### Scenario: 记录业务关联信息

- **WHEN** 日志需要关联合法的 chat key、message ID、Action、分类或状态码
- **THEN** 日志 SHALL 保留足以定位边界的原始低敏值
- **AND** SHALL 不通过通用掩码或摘要改写这些值

#### Scenario: 记录 Tool 调用

- **WHEN** `get_private_file_download_url` 或其他 Tool 返回包含下载 URL、媒体 URL 或未知扩展字段的成功 envelope
- **THEN** Tool 调用方 SHALL 收到完整原始成功 envelope
- **AND** 日志 SHALL 只记录 Tool 名称、结果分类、已知状态码和耗时
- **AND** 日志 SHALL NOT 记录下载 URL、媒体 URL、完整响应 body、token、Authorization 或本地路径

#### Scenario: 记录带自由文本参数的 Tool 调用

- **WHEN** `reject_friend_request` 携带可选 `reason` 完成调用
- **THEN** Tool 调用方 SHALL 按既有 raw envelope 契约收到远端结果或固定错误分类
- **AND** 日志 SHALL NOT 记录完整 `reason` 文本、底层异常正文或 Tool 参数对象

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册或远端没有可确认响应
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
- **AND** 日志 MAY 记录 Tool 名称和固定失败分类，但不得记录未确认的原始结果

### Requirement: QQ Tool 成功结果原样交付

已注册 Tool 的远端成功协议结果 MUST 原样返回给当前 Tool 调用方，保留完整 envelope、未知
字段和业务字段值；插件 MUST NOT 将该结果改造成摘要 DTO 或插件状态，也不得为了生成日志而
复制、遍历、摘要或重构该结果。

#### Scenario: Tool 返回成功协议结果

- **WHEN** 已注册 Tool 的远端 Action 返回成功协议结果
- **THEN** Tool 调用方 SHALL 收到未重构的原始协议结果
- **AND** 日志 MAY 记录该调用的 Tool 名称、固定结果分类、状态码和耗时
- **AND** 日志 SHALL NOT 记录入参、结果 body、下载 URL 或媒体字段

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册或远端没有可确认响应
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
- **AND** 日志是否存在 SHALL 不改变该结果
### Requirement: 入站资源处理由 Hermes core 所有，出站本地 materialization 有界

入站 trigger 的资源引用 MUST 只交给 Hermes core 已确认的资源入口；该边界继续由 Hermes
负责远端下载、缓存、路径和权限。出站 adapter 是明确例外：对 Hermes host 传入的本地
路径、`Path` 或 `file://localhost`，plugin MAY 在 Milky Action 边界只读取一次不超过启动配置
`MILKY_MAX_LOCAL_MEDIA_BYTES` 的常规非空文件并生成 `base64://`。plugin MUST NOT 下载远端 URL、读取远端 bytes、创建
持久化缓存或下载目录、拼接 Hermes 入站路径，或复制 Hermes 的 SSRF/权限规则。

#### Scenario: 入站 Hermes 资源入口可用

- **WHEN** trigger 资源存在对应的 Hermes core 入口
- **THEN** 插件 SHALL 将资源交给该入口
- **AND** MessageEvent SHALL 只使用 Hermes 返回的资源结果

#### Scenario: 入站 Hermes 资源入口不可用

- **WHEN** 没有确认的 Hermes 资源入口
- **THEN** 系统 SHALL 返回 `unsupported` 或既有可解释占位
- **AND** SHALL 不执行插件侧远端下载、文件读取、缓存或 base64 fallback

#### Scenario: 出站本地附件由 plugin 受限 materialize

- **WHEN** 出站 adapter 收到存在的本地路径、`Path` 或 `file://localhost` 文件
- **THEN** plugin SHALL 在 Milky 网络访问前检查常规、非空和启动配置的
  `MILKY_MAX_LOCAL_MEDIA_BYTES` 上限并生成 `base64://`
- **AND** SHALL 不把本地路径、完整文件内容或 Base64 内容写入日志、异常或 `SendResult`
