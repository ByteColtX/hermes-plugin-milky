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

运行时日志 MUST NOT 对业务 ID、chat key、message ID、昵称或 Tool 调用入参、远端结果中的业务字段执行掩码、摘要、改名或字段删除。已注册 Tool 的调用日志 SHALL 包含 Tool 名称、调用入参和远端结果。认证 header 和 HTTP transport 上下文不属于 Tool 入参或结果。

#### Scenario: 记录业务关联信息

- **WHEN** 日志记录合法的业务关联字段
- **THEN** 日志 SHALL 保留该业务字段的原始值
- **AND** SHALL 不通过通用掩码改写该值

#### Scenario: 记录 Tool 调用

- **WHEN** 已注册 Tool 完成一次调用并取得远端结果
- **THEN** 日志 SHALL 记录 Tool 名称、调用入参和远端结果
- **AND** 入参和结果 SHALL 不被摘要、改名、掩码或删除未知业务字段

### Requirement: QQ Tool 成功结果原样交付

已注册 Tool 的远端成功协议结果 MUST 原样返回给当前 Tool 调用方，保留完整 envelope、未知字段和业务字段值；插件 MUST NOT 将该结果改造成摘要 DTO 或插件状态。

#### Scenario: Tool 返回成功协议结果

- **WHEN** 已注册 Tool 的远端 Action 返回成功协议结果
- **THEN** Tool 调用方 SHALL 收到未重构的原始协议结果
- **AND** 日志 SHALL 记录该调用的入参和结果

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册或远端没有可确认响应
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果

### Requirement: 入站资源处理由 Hermes core 所有，出站本地 materialization 有界

入站 trigger 的资源引用 MUST 只交给 Hermes core 已确认的资源入口；该边界继续由 Hermes
负责远端下载、缓存、路径和权限。出站 adapter 是明确例外：对 Hermes host 传入的本地
路径、`Path` 或 `file://localhost`，plugin MAY 在 Milky Action 边界只读取一次不超过 8 MiB
的常规非空文件并生成 `base64://`。plugin MUST NOT 下载远端 URL、读取远端 bytes、创建
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
- **THEN** plugin SHALL 在 Milky 网络访问前检查常规、非空和 8 MiB 上限并生成 `base64://`
- **AND** SHALL 不把本地路径、完整文件内容或 Base64 内容写入日志、异常或 `SendResult`
