# outbound-messaging Specification

## Purpose

定义 Hermes 出站内容到 Milky 目标和 segment 的安全映射，覆盖 group、dm 以及临时目标的明确拒绝、
长文本、结构化媒体、文件上传与稳定 SendResult，确保目标错误不会误投递或假成功。

## Requirements

### Requirement: 出站目标按命名空间路由

`group:<id>` MUST 使用 `send_group_message`，`dm:<id>` MUST 使用 `send_private_message`；`MILKY_HOME_CHANNEL` 只能由 Hermes core/cron 在调用 adapter 前解析为这两种完整 chat key，adapter MUST NOT 将空目标或任意 `home` 标记隐式转换为 home channel。临时会话目标和其他非法目标 MUST 返回 `unsupported` 或本地目标校验失败；目标解析失败 MUST 在网络访问前返回且不得回退默认频道、home channel 或其他目标。

#### Scenario: 群消息发送

- **WHEN** Hermes 向合法 `group:<id>` 目标发送非空消息
- **THEN** 系统 SHALL 调用 `send_group_message`
- **AND** 请求 SHALL 使用该群 ID 而不是默认目标

#### Scenario: 临时会话目标

- **WHEN** Hermes 向临时会话目标发送消息
- **THEN** 发送 SHALL 在网络访问前返回 `unsupported`
- **AND** SHALL 不调用私聊 Action 或群聊 Action

#### Scenario: 非法目标

- **WHEN** 目标为空、负数、非数字或包含额外分隔符
- **THEN** 发送 SHALL 在网络访问前失败
- **AND** SHALL 不回退为 dm、默认目标、home channel 或其他目标

#### Scenario: 系统消息使用已解析的 home target

- **WHEN** Hermes 已将 `MILKY_HOME_CHANNEL` 解析为合法 `group:<id>` 或 `dm:<id>`，再向 adapter 发送系统消息
- **THEN** 系统 SHALL 按该 chat key 的命名空间选择对应 Milky Action
- **AND** adapter SHALL 不重新读取环境变量或改变该目标

### Requirement: 文本和结构化内容由统一格式转换

出站文本、mention、mention_all、face、reply、image、record、video、forward 和 light_app
MUST 按 Milky segment schema 生成；图片、语音和视频等媒体 MUST 通过 Hermes 的对应媒体
出站入口交给相同的 Milky segment 发送边界；空白消息 MUST 在网络访问前拒绝。

#### Scenario: 结构化消息

- **WHEN** Hermes 提供文本与结构化 outgoing segments
- **THEN** 请求 body SHALL 包含按原语义生成的 Milky segments
- **AND** adapter SHALL 不在生命周期代码中手工拼接不透明 Action body

#### Scenario: 空白消息

- **WHEN** 出站内容为空或只包含空白
- **THEN** 发送 SHALL 返回本地输入错误
- **AND** SHALL 不访问网络

#### Scenario: CQ-compatible 控制码

- **WHEN** Hermes 提供含有可确认转换的 at 或 reply CQ-compatible 控制码的文本
- **THEN** 请求 body SHALL 包含对应的 Milky mention 或 reply segment
- **AND** CQ-compatible 控制码本身 SHALL 不作为普通文本发送

#### Scenario: 全部文档 CQ 类型进入解析路径

- **WHEN** Hermes 提供 NapCat 文档列出的任一 CQ 类型
- **THEN** 系统 SHALL 识别该 CQ 类型并尝试形成 Milky outgoing segment
- **AND** 系统 SHALL 保留该 CQ 类型在消息中的原始顺序

#### Scenario: CQ 类型转换失败

- **WHEN** 已识别的 CQ 类型没有确认的 Milky 映射或转换过程失败
- **THEN** 系统 SHALL 使用完整原始 CQ 字符串生成 text segment
- **AND** SHALL 不静默丢弃该 CQ 内容或调用未确认的 Action

#### Scenario: 图片、语音或视频消息

- **WHEN** Hermes 向合法的 group 或 dm 目标投递图片、语音或视频
- **THEN** 请求 SHALL 使用对应的 Milky `image`、`record` 或 `video` segment
- **AND** 媒体投递 SHALL 不降级为包含本地路径的普通文本

### Requirement: 超长文本按明确边界拆分

超过 Milky 或 LLBot 限制的文本 MUST 按明确且可诊断的边界拆分为多个发送单元，每个单元的结果 SHALL 可独立观察。

#### Scenario: 超长文本

- **WHEN** 文本超过配置或协议允许的长度
- **THEN** 系统 SHALL 按边界拆分而不是截断内容
- **AND** SHALL 依次处理每个发送单元并保留失败位置

### Requirement: 文件使用独立上传 Action

出站文件 MUST 根据目标调用 `upload_group_file` 或 `upload_private_file`，不得将 file 放入
send message segments，也不得假设远端能访问本地路径。Hermes 提供的本地文件路径 MUST
按当前确认的临时兼容方案读取并编码为 `base64://` URI，再交给对应 upload Action。

#### Scenario: 群文件上传

- **WHEN** 合法群目标包含文件
- **THEN** 系统 SHALL 调用 `upload_group_file`
- **AND** SHALL 不把 file segment 塞入 `send_group_message`

#### Scenario: 本地路径不可共享

- **WHEN** 文件输入是当前主机的本地路径
- **THEN** 系统 SHALL 按已确认的上传契约处理或安全拒绝
- **AND** SHALL 不假设 Milky 进程可直接读取该路径

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

### Requirement: 发送结果和不支持能力诚实可观测

成功发送 MUST 使用远端 `data.message_seq` 生成稳定字符串消息 ID；成功文件上传 MUST 使用
远端确认的 `file_id` 作为附件结果标识；协议拒绝、传输未知、malformed 和 unsupported
MUST 分别报告，未实现的编辑、撤回、reaction 等能力 MUST 返回 `unsupported`。

#### Scenario: 发送成功

- **WHEN** send Action 成功并返回 `message_seq`
- **THEN** Hermes SendResult SHALL 标记成功并使用该序号作为 message ID
- **AND** SHALL 不使用本地时间或随机值

#### Scenario: 群发送失败

- **WHEN** 群文本、媒体或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** MAY 通知 MuteTracker 刷新对应群，但 SHALL 不把所有错误都伪装成禁言

#### Scenario: 未实现 Action

- **WHEN** 请求编辑、撤回、reaction 或其他未实现能力
- **THEN** SendResult SHALL 为 `unsupported`
- **AND** SHALL 不根据 Action 名称猜测成功

#### Scenario: 未知发送结果不得降级重发

- **WHEN** 一个群或私聊消息的发送 Action 已进入网络边界并返回 `transport_unknown`
- **THEN** 系统 SHALL 返回 `transport_unknown`，不得报告发送失败为“未执行”或假成功
- **AND** SHALL NOT 调用 plain-text fallback、再次调用对应 send Action 或改变原始消息内容后重发

#### Scenario: 宿主通用发送包装

- **WHEN** Hermes Gateway 通过 Milky adapter 的发送包装交付消息
- **THEN** Milky adapter SHALL 只调用一次自身 sender 并原样返回该结果
- **AND** SHALL NOT 委托给会 retry、发送用户可见失败通知或 plain-text fallback 的通用宿主实现

#### Scenario: 本地格式化失败

- **WHEN** 消息在发送 Action 之前因空白、非法目标或不支持的出站内容被本地拒绝
- **THEN** 系统 SHALL 在网络访问前返回对应错误
- **AND** SHALL NOT 使用 fallback 发送一个可能不同或带诊断文本的用户可见消息

#### Scenario: 媒体或文件发送失败

- **WHEN** 图片、语音、视频或文件发送失败
- **THEN** SendResult SHALL 返回原始安全错误类别
- **AND** SHALL 不伪造成功、不发送包含路径的 fallback 文本或盲目重复可能产生副作用的 Action

### Requirement: Agent 选择是否引用或提及

对于 Hermes 为普通 Agent 回复提供的隐式当前消息 reply anchor，出站边界 MUST 默认忽略该
anchor；只有消息正文中显式的合法 CQ-compatible 控制码或未来明确的结构化输入，才可以产生
mention 或 reply segment。没有显式控制码时，系统 MUST NOT 自动引用当前入站消息。

#### Scenario: 没有控制码的普通回复

- **WHEN** Agent 输出普通文本且 Hermes 同时提供当前消息的隐式 reply anchor
- **THEN** 出站请求 SHALL 只包含普通文本
- **AND** SHALL 不包含 reply segment

#### Scenario: 显式 reply 覆盖隐式 anchor

- **WHEN** Agent 输出 `[CQ:reply,id=9001]答复` 且 Hermes 提供另一个隐式 reply anchor
- **THEN** 出站请求 SHALL 只使用显式的 `9001` reply 目标
- **AND** SHALL 不追加隐式 anchor 对应的第二个 reply

#### Scenario: 显式 at 不改变引用状态

- **WHEN** Agent 输出 `[CQ:at,qq=101]答复` 且 Hermes 提供隐式 reply anchor
- **THEN** 出站请求 SHALL 包含 mention `101`
- **AND** SHALL 不因隐式 anchor 增加 reply segment

### Requirement: CQ-compatible 控制码未知或转换失败时原样放行

未知 CQ 码、malformed CQ-compatible 控制码、参数缺失以及已知 CQ 码转换失败时，系统 MUST
将完整原始 CQ 字符串保留为 text segment，并继续发送整条消息。该 fallback 不得触发额外
的 CQ 专用错误、通用文本 fallback、自动重试或第二次发送；目标非法、消息为空等独立的
出站校验仍按既有契约处理。

#### Scenario: malformed 控制码原样放行

- **WHEN** CQ-compatible at 或 reply 控制码的名称、参数或 ID 不符合语法
- **THEN** 发送内容 SHALL 包含完整原始 CQ 字符串对应的 text segment
- **AND** SHALL 不因该 CQ 片段单独阻止整条消息发送

#### Scenario: 未知控制码原样放行

- **WHEN** 文本包含尚未实现的 CQ-compatible 控制码
- **THEN** 发送内容 SHALL 包含未修改的原始 CQ 字符串 text segment
- **AND** SHALL 不把未知控制码转换成未确认的 Milky segment

#### Scenario: 已知 CQ 的转换器失败

- **WHEN** 已知 CQ 类型的字段符合基本格式但转换器无法生成合法 Milky segment
- **THEN** 发送内容 SHALL 回退为该 CQ 片段的原始 text segment
- **AND** 同一条消息的其他内容 SHALL 继续按原顺序发送

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
