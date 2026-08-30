## MODIFIED Requirements

### Requirement: 文本和结构化内容由统一格式转换

出站文本、mention、mention_all、face、reply、image、record、video、forward 和 light_app
MUST 按 Milky segment schema 生成；图片、语音和视频等媒体 MUST 通过 Hermes 的对应媒体
出站入口交给相同的 Milky segment 发送边界；空白消息 MUST 在网络访问前拒绝。

#### Scenario: 结构化消息

- **WHEN** Hermes 提供文本与结构化 outgoing segments
- **THEN** 请求 body SHALL 包含按原语义生成的 Milky segments
- **AND** adapter SHALL 不在生命周期代码中手工拼接不透明 Action body

#### Scenario: 图片、语音或视频消息

- **WHEN** Hermes 向合法的 group 或 dm 目标投递图片、语音或视频
- **THEN** 请求 SHALL 使用对应的 Milky `image`、`record` 或 `video` segment
- **AND** 媒体投递 SHALL 不降级为包含本地路径的普通文本

#### Scenario: 空白消息

- **WHEN** 出站内容为空或只包含空白
- **THEN** 发送 SHALL 返回本地输入错误
- **AND** SHALL 不访问网络

### Requirement: 文件使用独立上传 Action

出站文件 MUST 根据目标调用 `upload_group_file` 或 `upload_private_file`，不得将 file 放入
send message segments，也不得假设远端能访问本地路径。Hermes 提供的本地文件路径 MUST
按当前确认的临时兼容方案读取并编码为 `base64://` URI，再交给对应 upload Action。

#### Scenario: 群文件上传

- **WHEN** 合法群目标包含文件
- **THEN** 系统 SHALL 调用 `upload_group_file`
- **AND** SHALL 不把 file segment 塞入 `send_group_message`

#### Scenario: 私聊文件上传

- **WHEN** 合法 dm 目标包含文件
- **THEN** 系统 SHALL 调用 `upload_private_file`
- **AND** SHALL 返回远端确认的 `file_id`，不把文件内容作为普通文本发送

#### Scenario: 本地文件使用 base64 兼容方案

- **WHEN** 文件输入是当前主机上可读的普通本地文件或 `file://` 路径
- **THEN** 系统 SHALL 在 upload Action 的 JSON `file_uri` 中使用 `base64://` 内容
- **AND** SHALL 不把本地路径直接交给 Milky 或写入日志、错误和用户可见文本

#### Scenario: 文件路径不可读

- **WHEN** 文件路径为空、不是普通文件、不可读或目标非法
- **THEN** 系统 SHALL 在网络访问前返回可分类的本地错误
- **AND** SHALL 不调用任何消息或文件 upload Action

#### Scenario: 本地路径不可共享

- **WHEN** 文件输入是当前主机的本地路径
- **THEN** 系统 SHALL 按已确认的上传契约处理或安全拒绝
- **AND** SHALL 不假设 Milky 进程可直接读取该路径

### Requirement: Hermes 媒体入口必须执行 native 出站

当 Hermes 已将 Agent 输出中的资源解析为图片 URL、本地图片、语音、视频或文档附件时，
Milky adapter MUST 将这些资源交给对应的 native 媒体或文件出站能力，而不是使用
Hermes 基类的纯文本 fallback。显式选择的 `http(s)://` 或 `base64://` URI MAY 原样作为
远端资源引用使用；本地路径和 `file://` URI MUST 先 materialize 为 `base64://`。资源
materialization 只允许读取用户明确选择的资源，不得下载任意 URL、建立插件缓存或复制
Hermes 媒体权限规则。

#### Scenario: Agent 请求发送工作区文件

- **WHEN** Agent 输出一个已通过 Hermes 路径安全检查的工作区文件附件
- **THEN** Milky adapter SHALL 调用对应目标的独立文件上传 Action
- **AND** 用户 SHALL 收到文件附件而不是文件路径或文本 fallback

#### Scenario: Agent 请求发送本地图片、语音或视频

- **WHEN** Agent 输出一个已通过 Hermes 路径安全检查的本地图片、语音或视频附件
- **THEN** Milky adapter SHALL 将文件内容编码为 `base64://` 并放入对应 native media segment
- **AND** 请求 SHALL 使用既有 group/dm 消息 Action 完成一次媒体发送

#### Scenario: 远端媒体 URI

- **WHEN** Agent 或 Hermes 提供格式合法的 `http(s)://` 或 `base64://` 媒体 URI
- **THEN** 系统 SHALL 按对应 native media segment 或 upload URI 契约发送
- **AND** 系统 SHALL 不为了发送该 URI 在插件内执行额外下载或缓存

#### Scenario: adapter 未连接

- **WHEN** 媒体或文件投递发生在 adapter 已断开或停止之后
- **THEN** 系统 SHALL 返回 `unsupported` 或等价的未连接错误
- **AND** SHALL 不读取资源、不访问 Milky 网络且不调用 Hermes fallback

### Requirement: 发送结果和不支持能力诚实可观测

成功发送 MUST 使用远端 `data.message_seq` 生成稳定字符串消息 ID；成功文件上传 MUST 使用
远端确认的 `file_id` 作为附件结果标识；协议拒绝、传输未知、malformed 和 unsupported
MUST 分别报告，未实现的编辑、撤回、reaction 等能力 MUST 返回 `unsupported`。

#### Scenario: 发送成功

- **WHEN** send Action 成功并返回 `message_seq`
- **THEN** Hermes SendResult SHALL 标记成功并使用该序号作为 message ID
- **AND** SHALL 不使用本地时间或随机值

#### Scenario: 媒体或文件发送失败

- **WHEN** 图片、语音、视频或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** SHALL 不伪造成功、不发送包含路径的 fallback 文本或盲目重复可能产生副作用的 Action

#### Scenario: 群发送失败

- **WHEN** 群文本、媒体或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** MAY 通知 MuteTracker 刷新对应群，但 SHALL 不把所有错误都伪装成禁言

#### Scenario: 未实现 Action

- **WHEN** 请求编辑、撤回、reaction 或其他未实现能力
- **THEN** SendResult SHALL 为 `unsupported`
- **AND** SHALL 不根据 Action 名称猜测成功
