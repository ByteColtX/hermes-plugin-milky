# security-boundaries Specification

## Purpose

定义 Milky 适配器的业务日志、QQ Tool 原始结果、Hermes 资源入口和仓库合成数据边界。

## Requirements

### Requirement: 协议业务数据不得因通用敏感键名被插件删除

插件在解析、复制、冻结和交付 Milky 协议数据时 MUST 保留远端返回的字段和值，不得仅因键名匹配通用敏感词表而递归删除、掩码、改名或摘要业务字段。该要求不改变日志、异常、配置摘要、smoke 输出和测试资料的既有最小化边界。

#### Scenario: 扩展字段名称与敏感词相同

- **WHEN** Action、事件或消息扩展字段包含 token、password 或其他通用敏感键名
- **THEN** 协议数据交付 SHALL 保留该字段和值
- **AND** 插件 SHALL 不把键名过滤误当作完整秘密保护

#### Scenario: 日志仍保持最小化

- **WHEN** 协议响应包含凭证样式字段、完整 URL 或自由文本
- **THEN** 日志 SHALL 只记录既有低敏元数据
- **AND** 日志 SHALL NOT 复制响应正文、参数或原始业务对象

#### Scenario: 本地错误没有远端响应

- **WHEN** 参数校验、客户端状态或传输阶段无法取得可确认响应
- **THEN** 插件 SHALL 返回既有固定错误分类
- **AND** SHALL 不通过异常正文或原始参数补充所谓脱敏结果

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
Tool 原始入参或为生成日志而复制的业务对象。Tool 的日志分类 SHALL 只反映是否取得远端响应体
以及本地失败类型；只要远端响应体已经取得，Tool 调用方 SHALL 收到该响应体的原始内容。该边界
MUST 排除 token、Authorization header、原始响应 body、下载 URL、头像或其他媒体 URL、本地路径、
文件内容以及自由文本理由。

#### Scenario: 记录业务关联信息

- **WHEN** 日志需要关联合法的 chat key、message ID、Action、分类或状态码
- **THEN** 日志 SHALL 保留足以定位边界的原始低敏值
- **AND** SHALL 不通过通用掩码或摘要改写这些值

#### Scenario: 记录 Tool 调用

- **WHEN** `get_private_file_download_url` 或其他 Tool 返回包含下载 URL、媒体 URL 或未知扩展字段的任意响应体
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** 日志 SHALL 只记录 Tool 名称、结果分类、已知状态码和耗时
- **AND** 日志 SHALL NOT 记录下载 URL、媒体 URL、完整响应 body、token、Authorization 或本地路径

#### Scenario: 记录带自由文本参数的 Tool 调用

- **WHEN** `reject_friend_request` 携带可选 `reason` 完成调用
- **THEN** Tool 调用方 SHALL 收到远端响应体或无响应固定错误分类
- **AND** 日志 SHALL NOT 记录完整 `reason` 文本、底层异常正文或 Tool 参数对象

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册或远端没有可确认响应
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
- **AND** 日志 MAY 记录 Tool 名称和固定失败分类，但不得记录未确认的原始结果

### Requirement: QQ Tool 远端响应原样交付

全部已注册 Tool 只要取得远端响应体，就 MUST 把该响应体原样交给 Hermes core 作为 Tool 结果。
该规则适用于成功 envelope、协议拒绝、非 2xx HTTP 状态、非对象 JSON、数组、标量、显式 `null`、
非 JSON 文本、空 body 和其他任何可获得的响应体。插件 MUST NOT 依据 HTTP 状态或响应内容将结果
改造成摘要 DTO、插件状态、固定错误或附加状态码的包装对象，MUST NOT 对结果执行脱敏、过滤、
冻结、重建或摘要。响应体转换为 Hermes core 可接受的字符串时 SHALL 使用 UTF-8 解码，无法解码的
字节 SHALL 以替换字符表示并仍然交付。Hermes core 在插件交付之后的结果变换不在本契约范围内。

#### Scenario: Tool 返回任意可获得的远端响应

- **WHEN** 任一已注册 Tool 的远端 Action 返回任意 HTTP 状态和响应体
- **THEN** Tool 调用方 SHALL 收到内容不变的远端响应体
- **AND** 结果中的未知字段和敏感键 SHALL 保持可用，不被插件剔除、掩码或改名
- **AND** 结果 SHALL 不包含插件附加的状态码、分类或包装字段
- **AND** 日志 MAY 记录该调用的 Tool 名称、固定结果分类、状态码和耗时
- **AND** 日志 SHALL NOT 记录入参、结果 body、下载 URL 或媒体字段

#### Scenario: 远端响应体不是预期 envelope

- **WHEN** 远端响应体是非 JSON 文本、JSON 数组、JSON 标量、空 body 或未知 envelope
- **THEN** Tool SHALL 仍将已取得的响应体原样交给 Tool 调用方
- **AND** SHALL 不将其归类为插件自有 `malformed` 结果或补造 envelope

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册、client 未绑定或已关闭，或传输没有取得远端响应体
- **THEN** Tool SHALL 返回 `invalid_input`、`unsupported` 或 `transport_unknown` 等固定分类
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
