## MODIFIED Requirements

### Requirement: 入站资源处理由 Hermes core 所有，出站本地 materialization 有界

入站 trigger 的资源引用 MUST 只交给 Hermes core 已确认的资源入口；该边界继续由 Hermes
负责远端下载、缓存、路径和权限。出站 adapter 是明确例外：对 Hermes host 传入的本地
路径、`Path` 或 `file://localhost`，plugin MAY 在 Milky Action 边界只读取一次不超过启动配置
`MILKY_MAX_LOCAL_MEDIA_BYTES` 的常规非空文件并生成 `base64://`；未配置时该值为 `32 MiB`。
plugin MUST NOT 下载远端 URL、读取远端 bytes、创建持久化缓存或下载目录、拼接 Hermes 入站路径，
或复制 Hermes 的 SSRF/权限规则。

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
  `MILKY_MAX_LOCAL_MEDIA_BYTES` 上限，并生成 `base64://`
- **AND** SHALL 不把本地路径、完整文件内容或 Base64 内容写入日志、异常或 `SendResult`
