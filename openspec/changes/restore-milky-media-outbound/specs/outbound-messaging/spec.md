## MODIFIED Requirements

### Requirement: Hermes 媒体入口必须执行 native 出站

当 Hermes 将 Agent 输出中的资源解析为图片、语音、视频或文档附件时，Milky plugin MUST
在出站边界统一 materialize 资源。对本地路径、`Path` 或 `file://localhost`，plugin MUST
只读取常规、非空且不超过 8 MiB 的文件一次并生成 `base64://` URI；对合法 `http(s)://`
或显式 `base64://`，plugin MUST 原样保留且不得下载或解码。所有失败 MUST 在 Milky
网络访问前分类返回，并且不得把路径、URI、Base64 内容或完整异常写入结果或日志。

图片、语音和视频 MUST 使用对应的 `image`、`record` 或 `video` native segment；文档
MUST 使用对应目标的独立 file upload。系统 MUST 不依赖 Hermes outbound materialization
seam，不把媒体降级成路径文本，也不使用 Hermes 基类的纯文本 fallback。

Agent-facing Milky guidance MUST identify the `MEDIA:<local_path>` directive as the native
local-attachment entry point for images, audio, video and documents. In a normal reply, the
directive MUST be placed in the final response; when the Agent explicitly calls Hermes
`send_message`, the directive MUST be placed in its `message` argument. The guidance MUST
distinguish this entry point from the fixed QQ ToolSpec list and MUST NOT instruct the Agent to use
plain text when an attachment was requested. The Agent MUST report missing media capability only
after the send entry point returns a failure.

#### Scenario: Agent 请求发送本地视频

- **WHEN** Hermes host 将一个存在的本地视频路径传给 Milky adapter
- **THEN** plugin SHALL 读取该常规文件并生成 `base64://` URI
- **AND** SHALL 将 URI 放入 `video` segment 并调用合法目标对应的 message Action

#### Scenario: Agent 通过通用发送入口请求本地视频

- **WHEN** Agent 需要发送本地视频，且生成 `MEDIA:<local_path>` 发送指令
- **THEN** Hermes SHALL 将该指令解析为 Milky adapter 的 `send_video` 入口
- **AND** Agent SHALL NOT 因固定 QQ ToolSpec 列表没有 `send_video` 而报告媒体能力不存在

#### Scenario: Agent 请求发送本地图片、语音或视频

- **WHEN** Hermes host 将一个存在的本地图片、语音或视频路径传给 Milky adapter
- **THEN** plugin SHALL 分别生成 `image`、`record` 或 `video` segment
- **AND** SHALL 保持 group/dm 路由和附件顺序

#### Scenario: Agent 请求发送本地工作区文件

- **WHEN** Hermes host 将一个存在的本地文档路径传给 Milky adapter
- **THEN** plugin SHALL 将其 materialize 为 `base64://` 并调用独立 file upload Action
- **AND** 请求 SHALL 包含安全文件名且不得包含 `file` message segment

#### Scenario: 远端媒体 URI

- **WHEN** 输入是格式合法的 `http(s)://` 或 `base64://`
- **THEN** 系统 SHALL 原样发送该 URI
- **AND** SHALL 不在 plugin 内执行额外下载、读取或解码

#### Scenario: 本地附件超过边界

- **WHEN** 本地路径不存在、不是常规文件、为空、超过 8 MiB、使用远端 `file://` 或
  使用未知 scheme
- **THEN** plugin SHALL 在 Milky 网络访问前返回 `invalid_input` 或 `unsupported`
- **AND** SHALL 不执行 message/upload Action，不回显路径或资源内容

#### Scenario: adapter 未连接

- **WHEN** 媒体或文件投递发生在 adapter 已断开或停止之后
- **THEN** plugin SHALL 返回 `unsupported`
- **AND** SHALL 不读取资源、不访问 Milky 网络或调用 Hermes fallback

#### Scenario: Agent 只产生文本

- **WHEN** Agent turn 只产生普通文本
- **THEN** 系统 SHALL 只执行普通文本出站
- **AND** SHALL 不猜测附件、不读取本地文件、不调用媒体或文件 Action

#### Scenario: 多附件部分失败

- **WHEN** 一个 Agent turn 按顺序产生多个附件且其中一个 Action 失败
- **THEN** 系统 SHALL 保留已成功结果和首个失败分类
- **AND** 每个可能产生副作用的 Action 最多调用一次，不发送纯文本 fallback 或盲目重试
