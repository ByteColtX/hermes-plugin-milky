## MODIFIED Requirements

### Requirement: 文件使用独立上传 Action

出站文件 MUST 根据目标调用 `upload_group_file` 或 `upload_private_file`，不得将 file 放入 send message segments，也不得假设远端能访问本地路径。文件资源 MUST 来自 Hermes core 已确认的出站资源入口；插件不得自行读取本地文件、下载远端文件、创建临时缓存或把路径转换为 `base64://` fallback。没有确认的 Hermes 出站资源入口时 SHALL 返回 `unsupported`。

#### Scenario: 群文件上传

- **WHEN** 合法群目标包含由 Hermes core 提供的可上传文件资源
- **THEN** 系统 SHALL 调用 `upload_group_file`
- **AND** SHALL 不把 file segment 塞入 `send_group_message`

#### Scenario: 本地路径不可共享

- **WHEN** 文件输入只是当前主机的本地路径，且没有 Hermes core 提供的已确认资源入口
- **THEN** 系统 SHALL 返回 `unsupported` 或本地资源错误
- **AND** SHALL 不读取该路径、不把路径直接交给 Milky、不创建插件侧 base64 fallback

#### Scenario: 私聊文件上传

- **WHEN** 合法 dm 目标包含由 Hermes core 提供的可上传文件资源
- **THEN** 系统 SHALL 调用 `upload_private_file`
- **AND** SHALL 返回远端确认的 `file_id`，不把文件内容作为普通文本发送

#### Scenario: 本地文件使用 base64 兼容方案

- **WHEN** 文件输入是当前主机上的本地文件或 `file://` 路径，但没有 Hermes core 提供的已确认出站资源入口
- **THEN** 系统 SHALL 返回 `unsupported` 或本地资源错误，不在插件侧生成 `base64://`
- **AND** SHALL 不读取本地文件、不把本地路径交给 Milky

#### Scenario: 文件路径不可读

- **WHEN** Hermes 没有提供可用的文件资源入口，或资源权限/路径校验失败
- **THEN** 系统 SHALL 在 Milky 网络访问前返回可分类错误
- **AND** SHALL 不调用任何消息或文件 upload Action

### Requirement: Hermes 媒体入口必须执行 native 出站

当 Hermes 已将 Agent 输出中的资源解析并 materialize 为可供出站的资源时，Milky adapter MUST 将该资源交给对应的 native 媒体或文件出站能力，而不是使用纯文本 fallback。资源下载、读取、缓存、权限和本地路径由 Hermes core 负责；插件不得为了发送资源自行下载、读取本地文件、建立缓存或生成 `base64://` fallback。

#### Scenario: Agent 请求发送工作区文件

- **WHEN** Agent 输出一个已通过 Hermes 路径安全检查并由 Hermes core 提供的工作区文件附件
- **THEN** Milky adapter SHALL 调用对应目标的独立文件上传 Action
- **AND** 用户 SHALL 收到文件附件而不是文件路径或文本 fallback

#### Scenario: Agent 请求发送本地图片、语音或视频

- **WHEN** Agent 输出一个已由 Hermes core materialize 的本地图片、语音或视频附件
- **THEN** Milky adapter SHALL 将 Hermes 提供的可上传资源交给对应 native media 能力
- **AND** SHALL 不在插件侧读取路径、编码 bytes 或创建 `base64://` fallback

#### Scenario: 远端媒体 URI

- **WHEN** Agent 或 Hermes 提供远端媒体 URI
- **THEN** 系统 SHALL 仅在该 URI 已由 Hermes core 通过确认的资源入口提供时交给对应 native media 或 upload 能力
- **AND** 没有该入口时 SHALL 返回 `unsupported`，不得在插件内执行额外下载或缓存

#### Scenario: adapter 未连接

- **WHEN** 媒体或文件投递发生在 adapter 已断开或停止之后
- **THEN** 系统 SHALL 返回 `unsupported` 或等价的未连接错误
- **AND** SHALL 不读取资源、不访问 Milky 网络且不调用 Hermes fallback
