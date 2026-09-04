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

- **WHEN** Hermes 提供含有可确认转换的 at、reply 或仅用于 sticker 的 image CQ-compatible 控制码的文本
- **THEN** 请求 body SHALL 包含对应的 Milky mention、reply 或 image segment
- **AND** CQ-compatible 控制码本身 SHALL 不作为普通文本发送

#### Scenario: CQ sticker 本地 URI

- **WHEN** Hermes 提供仅用于 sticker 的 `[CQ:image,file=file:///...,type=sticker]` 控制码
- **THEN** 系统 SHALL 在调用消息 Action 前将该本地常规文件只读取一次并转换为 `base64://`
- **AND** 请求 SHALL 包含 `image` segment 及 `sub_type=sticker`，不得包含原始 `file://` URI
- **AND** 本地文件不存在、不可读、为空或超过 8 MiB 时 SHALL 在网络访问前返回 `invalid_input`
- **AND** SHALL 不发送原始 CQ 文本或其他用户可见 fallback

#### Scenario: 普通图片使用 MEDIA 入口

- **WHEN** Hermes 需要发送普通图片
- **THEN** Agent SHALL 使用 `MEDIA:<local_path>` 入口
- **AND** Agent SHALL NOT 使用 CQ image 语法代替普通图片发送

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

超过 Milky 或 LLBot 限制的文本 MUST 按明确且可诊断的边界拆分为多个发送单元，每个单元的结果 SHALL 可独立观察。包含有效 `[SPLIT]` 行的回复 MUST 先按 `[SPLIT]` 形成最多三个逻辑文本单元，再应用既有长度边界；空逻辑单元不得发送，超过三个逻辑单元时尾部内容 MUST 合并到第三个单元。若长度拆分使实际文本消息数超过三条，系统 MUST 在网络访问前整体拒绝该分段回复，不得截断或部分发送。未包含有效 `[SPLIT]` 的普通长文本继续遵守既有长度拆分，不受三条分段上限影响。

#### Scenario: 超长普通文本

- **WHEN** 未包含有效 `[SPLIT]` 的文本超过配置或协议允许的长度
- **THEN** 系统 SHALL 按边界拆分而不是截断内容
- **AND** SHALL 依次处理每个发送单元并保留失败位置

#### Scenario: 超长文本

- **WHEN** 文本超过配置或协议允许的长度
- **THEN** 系统 SHALL 按边界拆分而不是截断内容
- **AND** SHALL 依次处理每个发送单元并保留失败位置

#### Scenario: 有效分段先于长度拆分

- **WHEN** 文本包含独立成行、大小写严格匹配的 `[SPLIT]` 且任一逻辑段超过长度上限
- **THEN** 系统 SHALL 先移除有效标记并确定逻辑段，再对逻辑段应用长度拆分
- **AND** SHALL 保持所有可见文本及其相对顺序

#### Scenario: 分段后的物理消息超过上限

- **WHEN** 有效 `[SPLIT]` 回复经长度拆分后需要四条或更多文本消息
- **THEN** 系统 SHALL 在任何消息 Action 前返回可分类的本地边界失败
- **AND** SHALL 不发送前序文本或截断后续文本

### Requirement: 文本分段与附件投递保持当前交接顺序

当 Hermes 从同一 Agent 回复中提取 `MEDIA:` 附件时，包含有效 `[SPLIT]` 的文本部分 MUST 先由 Hermes 的文本投递路径按顺序交给 Milky；随后附件 MUST 按 Hermes 提取顺序通过既有图片、语音、视频 native message Action 或独立文件 upload Action 投递。`[SPLIT]` MUST NOT 改写、吞并或重排 `MEDIA:` 指令。当前能力不支持文本段和附件在同一回复内交错投递；文本分段的最多三条限制只约束插件管理的文本发送单元，不把 Hermes 独立附件 Action 假装纳入同一文本批次。

#### Scenario: 文本、分段标记和媒体附件同现

- **WHEN** Agent 回复包含第一段文本、有效 `[SPLIT]` 行、第二段文本和一个有效 `MEDIA:` 附件指令
- **THEN** 用户 SHALL 先收到第一段文本，再收到第二段文本，最后收到该附件
- **AND** 有效 `[SPLIT]` 和 `MEDIA:` 指令 SHALL 不作为普通可见文本发送

#### Scenario: 多个附件跟随文本完成后发送

- **WHEN** Agent 回复包含多个文本段和多个按顺序提取的媒体或文件附件
- **THEN** 所有文本发送单元 SHALL 在第一个附件 Action 前完成其既定顺序提交
- **AND** 附件 SHALL 按 Hermes 提取顺序逐项投递
- **AND** 文本段与附件 SHALL 不交错

#### Scenario: 附件失败不伪造交错成功

- **WHEN** 文本已成功投递但后续媒体或文件 Action 失败
- **THEN** 系统 SHALL 保留文本成功结果和附件的安全失败分类
- **AND** SHALL 不将附件失败改写为文本成功或发送路径文本 fallback

#### Scenario: 需要交错交接时保持未支持边界

- **WHEN** 上游只提供文本正文和独立附件列表而没有带顺序的文本/附件事件流
- **THEN** Milky plugin SHALL 继续使用文本先于附件的固定顺序
- **AND** SHALL 不根据原始回复正文中的 `MEDIA:` 位置猜测或模拟交错顺序
- **AND** SHALL 将真正的交错投递保留为需要 Hermes core 有序交接契约的后续能力

### Requirement: 文件使用独立上传 Action

出站文件 MUST 根据目标调用 `upload_group_file` 或 `upload_private_file`，不得将 file 放入
send message segments，也不得假设远端能访问本地路径。对当前 Hermes adapter 传入的本地
路径、`Path` 或 `file://localhost`，plugin MUST 在出站边界只读取一次常规、非空且不超过
8 MiB 的文件并生成 `base64://`；合法 `http(s)://` 和显式 `base64://` MUST 原样保留，
不得下载或解码。其他本地资源边界失败时 MUST 在网络访问前返回 `invalid_input` 或
`unsupported`。

#### Scenario: 群文件上传

- **WHEN** 合法群目标包含文件
- **THEN** 系统 SHALL 调用 `upload_group_file`
- **AND** SHALL 不把 file segment 塞入 `send_group_message`

#### Scenario: 本地路径由 plugin materialize

- **WHEN** 文件输入是当前主机的本地路径
- **THEN** plugin SHALL 读取该常规文件并生成 `base64://` URI
- **AND** SHALL 使用该 URI 调用对应的独立文件上传 Action

#### Scenario: 私聊文件上传

- **WHEN** 合法 dm 目标包含文件
- **THEN** 系统 SHALL 调用 `upload_private_file`
- **AND** SHALL 返回远端确认的 `file_id`，不把文件内容作为普通文本发送

#### Scenario: 本地文件超出 plugin 边界

- **WHEN** 文件输入为空、不是常规文件、不可读、超过 8 MiB 或是远端 `file://` URI
- **THEN** 系统 SHALL 返回 `invalid_input` 或 `unsupported`
- **AND** SHALL 不把路径交给 Milky 或生成部分 `base64://` 内容

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
