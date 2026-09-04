# message-segments Specification

## Purpose

定义 Milky 消息 segment 的容错解析和可解释降级，让文本、提及、引用、媒体与未知
扩展既能形成稳定策略信号，又不会把协议未知内容悄悄伪装成普通文本或执行指令。

## Requirements

### Requirement: 支持的 segment 必须保留类型和语义

消息 SHALL 容错识别 Milky v1.3 的 incoming segment：text、mention、mention_all、face、reply、
image、record、video、file、forward、market_face、light_app、xml 和 markdown，并保留每种
segment 的 typed 内容与必要 raw 字段。`image`、`record`、`video` SHALL 生成
`media_resource_references`，保留 `resource_id`、可选 `temp_url` 和 MIME/大小提示；`file`
SHALL 生成独立的 `file_attachment_references`，保留 `file_id`、`file_name`、`file_size`、
可选 `file_hash`，不得将其放入前一集合。

规范化正文 MUST 按原顺序使用以下可解释展示：`face` 为 `[face:<face_id>]`；mention_all 为
`@全体成员`；`image` 为 `[img:file_name=<summary>]`，没有 summary 时回退为
`[img:file_name=<resource_id>]`；`record` 为 `[record:NOT SUPPORTED]`；`video` 为
`[video:NOT SUPPORTED]`；`file` 为
`[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]`；`forward` 为
`[forward:forward_id=<forward_id>]`；`market_face` 为 `[market_face:summary=<summary>]`；
`xml` 为 `[xml:NOT SUPPORTED]`。缺少对应字段、字段为 `null` 或字段不可用时，字段值 MUST
使用 `NOT SUPPORTED`，不得补造 ID、文件名或哈希。

`light_app` SHALL 解析 `json_payload`。当 payload 是 JSON object 且存在 `meta` 字段时，
正文 MUST 以 `[light_app:{"meta":...}]` 开始，并完整递归保留 `meta` 字段下的所有 key、
value、数组和 null；不得假设 `meta` 下的字段数量、名称或层级。payload 顶层除 `meta` 外
的字段 MUST 忽略。`contact` 等具体卡片类型仍统一展示为 `light_app`，不得增加独立
segment 类型。payload 无法解析或没有 `meta` 字段时，正文 MUST 为
`[light_app:NOT SUPPORTED]`。Markdown 内容 SHALL 原样进入正文。

完整 inline `reply` SHALL 只保留 reply 目标供 `reply_to` header 和 Hermes reply metadata 使用，
不得在正文中额外追加 `[引用]` 或其他成功占位符。reply 缺少协议必填字段或 trigger 查询失败
时，正文 MAY 使用 `[reply:NOT SUPPORTED]`，并保留 malformed 或安全资源诊断。

normalizer 阶段生成的 image placeholder 是临时展示。trigger 阶段 image 经 Hermes image helper
成功落盘后，最终正文 MUST 将对应 image occurrence 替换为其在当前
`ResolvedTriggerBatch` 中选定的首次代表路径 basename；所有已确认内容相同的可见 occurrence
MUST 使用同一个代表 basename。代表 basename MUST 与交给 Hermes `media_urls` 的对应路径
basename 一致。helper 不可用、下载失败或返回无效本地路径时，正文 MUST 使用
`[img:file_name=NOT SUPPORTED]`；hash 不可用时不得用 summary、resource_id、URL、文件名或
其他协议字段推断图片相同。

`file` 只属于入站消息，不属于 outgoing message segment。除架构明确允许主消息
`message_seq` 缺失并进入 `no_stable_message_id` 降级外，规范化 SHALL 不补造 OpenAPI 必填
字段；reply 的 `message_seq`、`sender_id`、`time` 和 `segments` 缺失时 SHALL 保持 malformed
诊断。

#### Scenario: 复合消息占位符保持顺序

- **WHEN** 消息按顺序包含文本、face、image、record、video、file、forward、market_face 和 xml
- **THEN** 规范化正文 SHALL 按相同顺序包含各自 placeholder
- **AND** file placeholder SHALL 同时包含 `file_id`、`file_name` 和 `file_hash`
- **AND** SHALL 不把未支持的 record、video、market_face 或 xml 静默变成普通文本

#### Scenario: 复合消息

- **WHEN** 消息同时包含文本、提及、回复和图片
- **THEN** 规范化结果 SHALL 保留各 segment 的顺序和类型
- **AND** SHALL 生成对应的正文、mention、quote 和 image 信号

#### Scenario: 文件入站

- **WHEN** 消息包含 file segment
- **THEN** 规范化结果 SHALL 保留 file ID、名称、大小提示和可用 hash 的独立文件引用
- **AND** SHALL 将这些值按 `file_id`、`file_name`、`file_hash` 顺序写入文件 placeholder
- **AND** SHALL NOT 将其当成出站文件 segment 或本地路径

#### Scenario: Milky v1.3 真实字段形状

- **WHEN** 消息包含 image、reply 或 forward
- **THEN** 规范化 SHALL 保留 resource、reply 和 forward 的协议字段及原始类型
- **AND** SHALL 不将这些字段改名为 OneBot 字段或把 forward 误当成已展开消息

#### Scenario: 文件字段只有协议引用

- **WHEN** file segment 提供 `file_id`、`file_name`、`file_size` 和可空 `file_hash`
- **THEN** 结果 SHALL 将这些字段保留为独立文件引用
- **AND** file placeholder SHALL 展示可用的 `file_hash` 或 `file_hash=NOT SUPPORTED`
- **AND** SHALL NOT 要求 file segment 提供 temp_url 或把 file_name 解释成本地路径

#### Scenario: light_app 保留完整 meta 根对象

- **WHEN** `light_app.json_payload` 是包含任意嵌套 `meta` object 的合法 JSON
- **THEN** 正文 SHALL 以 `[light_app:{"meta":` 开始
- **AND** SHALL 保留 `meta` 下所有递归字段和值
- **AND** SHALL 忽略 payload 顶层的 `app`、`prompt`、`config`、`view` 和 `ver` 等字段

#### Scenario: contact card 仍使用 light_app

- **WHEN** `light_app` payload 表示 contact card
- **THEN** 正文 SHALL 使用 `[light_app:{"meta":...}]` 形式
- **AND** SHALL NOT 生成 `[contact:...]` 或新的 contact segment

#### Scenario: light_app payload 缺少 meta

- **WHEN** `json_payload` 不是合法 JSON object 或不包含 `meta`
- **THEN** 正文 SHALL 使用 `[light_app:NOT SUPPORTED]`
- **AND** SHALL 不把未知顶层字段猜测为正文

#### Scenario: image placeholder follows Hermes basename

- **WHEN** trigger 阶段 image helper 成功返回本地落盘路径，且该 occurrence 在当前 batch 中可计算
  内容摘要
- **THEN** 最终正文 SHALL 使用当前 batch 选定的首次代表路径 basename
- **AND** 该 basename SHALL 与 Hermes `media_urls` 中对应路径的 basename 相同
- **AND** SHALL 不使用 image `summary`、`resource_id` 或 helper 的其他随机命名作为跨 occurrence
  的 identity

#### Scenario: multiple image placeholders keep helper basename order

- **WHEN** 一条消息或其可见 reply 内容按顺序包含多个 image occurrence，且其中若干 helper 返回
  路径的文件内容完全相同
- **THEN** 内容相同的 occurrence 的 placeholder SHALL 全部使用首次 occurrence 的代表 basename
- **AND** 内容不同的 occurrence SHALL 按首次出现顺序使用各自代表 basename
- **AND** 正文中 occurrence 的数量和原始顺序 SHALL 保持不变

#### Scenario: image hash unavailable keeps conservative identity

- **WHEN** image helper 成功但本地文件不可安全读取、文件状态不符合限制或 SHA-256 计算失败
- **THEN** 系统 SHALL 不宣称该 occurrence 与其他图片内容相同
- **AND** SHALL 保留该 occurrence 的独立 helper basename（若其路径仍是可交给 Hermes 的本地路径）或
  现有失败占位

#### Scenario: image helper failure keeps typed fallback

- **WHEN** image helper 不可用、下载失败或返回无效路径
- **THEN** 对应正文 SHALL 使用 `[img:file_name=NOT SUPPORTED]`
- **AND** SHALL 不泄露远端 URL 或本地完整路径

#### Scenario: file placeholder preserves protocol fields

- **WHEN** file segment 提供 `file_id` 和 `file_name`，且资源 Action 不可用或失败
- **THEN** 正文 SHALL 使用 `[file:file_id=<file_id>,file_name=<file_name>]`
- **AND** SHALL 不用笼统的 `[file:NOT SUPPORTED]` 覆盖已有字段

#### Scenario: forward placeholder labels its identifier

- **WHEN** 消息包含 forward segment
- **THEN** 正文 SHALL 使用 `[forward:forward_id=<forward_id>]`

#### Scenario: market face placeholder keeps summary

- **WHEN** market_face segment 提供 summary
- **THEN** 正文 SHALL 使用 `[market_face:summary=<summary>]`

### Requirement: 提及和回复信号必须可区分

规范化 SHALL 区分 mention self、mention all、mention here 和 none，并保留 reply 目标 ID；是否
提及 Bot 和是否引用 Bot SHALL 可独立判断。直接提及只有在 `mention.user_id` 等于当前消息的
`self_id` 时才是 self mention；遍历 `message.segments` 中的 `reply` segment 时，只有该
segment 的 `reply.data.sender_id` 等于当前消息的 `self_id` 时才是 self quote。当前消息的
`message.sender_id` 只表示引用者，不参与 self quote 判断。引用存在但 `reply.data.sender_id`
缺失、非法或不是 Bot 时，reply 存在性和 self quote SHALL 保持可区分，且不得把普通引用标记为
引用 Bot；`reply.data.segments` 中的 mention 不参与引用 Bot 判断。Milky v1.3 只有 `mention` 和 `mention_all`
segment，没有独立的 `mention_here` segment；对普通 v1.3 输入，normalizer MUST NOT 从普通文本
或 `mention` 的名称臆造 here 信号，只有未来被明确识别的协议扩展才可产生 here 信号。多个
提及信号 SHALL 保留为独立信号，不得因使用单一优先值而丢失 all 或 self。

#### Scenario: 提及 Bot 与全体提及

- **WHEN** 消息分别包含直接提及 Bot、`mention_all` 或 here 提及
- **THEN** 结果 SHALL 产生对应的 self、all 或 here mention kind
- **AND** routing SHALL 能按不同信号选择不同策略

#### Scenario: 提及其他用户不标记为 self mention

- **WHEN** `mention.user_id` 与当前消息的 `self_id` 不一致
- **THEN** 结果 SHALL 保留该 mention segment
- **AND** SHALL 不产生 self mention 信号或使用 Bot 的 mention routing

#### Scenario: 引用 Bot 的消息产生 self quote

- **WHEN** reply segment 提供目标 ID，且 `reply.data.sender_id` 等于当前消息的 `self_id`
- **THEN** 结果 SHALL 同时保留 reply 目标 ID 和 self quote 信号
- **AND** routing SHALL 可据此命中 `quote` 规则

#### Scenario: 引用他人的消息不标记为 self quote

- **WHEN** reply segment 的 `reply.data.sender_id` 与当前消息的 `self_id` 不一致
- **THEN** 结果 SHALL 保留 reply 目标 ID和 reply 存在性
- **AND** SHALL 不产生 self quote 信号或使用 Bot 的 quote routing

#### Scenario: reply.data.sender_id 未知时不猜测 Bot 目标

- **WHEN** reply segment 缺少、非法或无法确认 `reply.data.sender_id`
- **THEN** 结果 SHALL 保留可确认的引用目标和安全诊断
- **AND** SHALL 不产生 self quote 信号，不从正文、显示名称或嵌套内容推断引用 Bot

#### Scenario: 引用目标不可补全

- **WHEN** reply segment 只有目标 ID而远端原文尚未查询
- **THEN** 结果 SHALL 保留目标 ID
- **AND** SHALL 不将缺失的原文伪造成正文

#### Scenario: 引用目标正文尚未补全

- **WHEN** reply segment 提供协议要求的目标 ID，但远端原文尚未查询
- **THEN** 结果 SHALL 保留目标 ID
- **AND** SHALL 不将缺失的原文伪造成正文

#### Scenario: reply 缺少协议必填字段

- **WHEN** reply segment 的 `reply.data` 缺少 `message_seq`、`sender_id`、`time` 或 `segments`
- **THEN** 该 segment SHALL 保持 malformed 诊断
- **AND** SHALL 不伪造引用目标或把缺失字段当作普通文本

#### Scenario: reply 已经携带原文

- **WHEN** reply segment 的 `reply.data` 已提供 `message_seq`、`sender_id`、时间和嵌套 `segments`
- **THEN** 规范化 SHALL 保留这些内嵌信息
- **AND** trigger SHALL NOT 为同一 reply 强制重复调用 `get_message`

### Requirement: 资源只生成分类的延迟引用

normalization MUST 不执行网络 I/O、文件系统访问、时钟读取或随机抽样。`image`、`record`、`video` 只保存 `media_resource_references`（`temp_url`、`resource_id`、名称、MIME/大小提示和原始 segment）；`file` 只保存 `file_attachment_references`（`file_id`、`file_name`、`file_size`、可选 `file_hash` 和原始 segment）。`forward_id` 与 reply 目标也只能作为延迟引用保存，供 trigger 阶段使用。`media_resource_references` 的协议查询使用已确认的 `get_resource_temp_url`；group file 使用 `get_group_file_download_url(group_id, file_id)`，private file 使用 `get_private_file_download_url(user_id, file_id, file_hash, ...)`，不得把 file 套用到 resource Action。

#### Scenario: wait 阶段遇到图片

- **WHEN** 消息包含图片且 Will 决策为 wait
- **THEN** 缓冲记录 SHALL 只包含可校验的 `media_resource_references`
- **AND** SHALL 不调用资源接口或下载文件

#### Scenario: 媒体引用字段不完整

- **WHEN** 媒体缺少可用 URL、file_id 或 file 提示
- **THEN** 结果 SHALL 保留 raw 并生成可解释的不可用媒体占位
- **AND** SHALL 不把未知字段转换为普通 Agent 指令

#### Scenario: forward 只保存延迟引用

- **WHEN** 消息包含只有 `forward_id` 和预览信息的 forward segment
- **THEN** wait 记录 SHALL 保存该引用而不是展开内容
- **AND** trigger 才 MAY 调用 `get_forwarded_messages`，且失败时 SHALL 保留可解释占位

#### Scenario: 分类引用字段不完整

- **WHEN** 媒体资源缺少可用 URL/resource_id，或 file 缺少可用 file_id/file 提示
- **THEN** 结果 SHALL 保留 raw 并生成可解释的不可用资源/文件占位
- **AND** SHALL 不把未知字段转换为普通 Agent 指令

### Requirement: 未知内容和空消息必须安全降级

未知 segment（包括扩展协议字段）SHALL 保留安全 raw 与诊断；未知 segment MUST NOT 使用 Milky schema 的 `[unknown]` 默认文本值；消息没有任何受支持正文、媒体资源或文件附件内容时 MUST 明确记录丢弃原因并停止。合法的 face、reply、媒体资源、文件附件、forward、market_face、light_app、xml 和 markdown 属于受支持结构化内容，即使其正文文本为空。

#### Scenario: 未知 segment 与文本并存

- **WHEN** 消息包含未知 segment 以及合法文本
- **THEN** 文本 SHALL 保持可处理
- **AND** 未知 segment SHALL 只进入 metadata/raw，不得静默变成可执行文本

#### Scenario: 消息没有受支持内容

- **WHEN** 消息只包含无法解释的 segment 或为空
- **THEN** 系统 SHALL 记录明确的丢弃原因
- **AND** SHALL NOT 创建空的 Hermes MessageEvent

### Requirement: 规范化结果必须提供稳定策略特征

规范化 SHALL 在不重新读取 raw payload 的情况下提供稳定的有序正文和策略特征：至少包括事件
类型、场景、时间、正文/策略文本、独立的 self/all/here/none mention 信号、reply 存在性与
目标 ID、是否引用 Bot 的独立信号、image 存在性、typed segments、分类后的延迟引用
（`media_resource_references`、`file_attachment_references`、forward/reply references）和
安全诊断。text 与 markdown 内容 SHALL 按原顺序保留；合法的结构化 segment SHALL 使用可解释
占位；unknown segment SHALL 不进入正文或关键词内容。reply/forward 的嵌套内容 SHALL 保留为
引用数据，不得隐式并入当前消息正文。

#### Scenario: 结构化 segment 生成稳定正文

- **WHEN** friend 或 group 消息按顺序包含 text、mention、reply、image、file、forward、light_app
  和 xml
- **THEN** 规范化正文 SHALL 保持受支持内容的顺序和对应 placeholder
- **AND** 策略特征 SHALL 独立报告 mention、reply 和 image
- **AND** light_app SHALL 只展示完整 `meta` 根对象

#### Scenario: 未知 segment 不进入正文

- **WHEN** 消息包含未知 segment 以及合法文本
- **THEN** 文本和已支持 placeholder SHALL 保持可处理
- **AND** 未知 segment SHALL 只进入安全诊断和 raw

#### Scenario: 只有未知内容

- **WHEN** 消息只包含未知 segment 或空 segments
- **THEN** 规范化 SHALL 记录明确丢弃原因
- **AND** SHALL NOT 创建空的 Hermes MessageEvent

#### Scenario: 复合 segment 生成策略特征

- **WHEN** friend 或 group 消息按顺序包含 text、mention、mention_all、reply、image 和 unknown
- **THEN** 规范化正文 SHALL 保持受支持内容顺序和可解释占位
- **AND** 策略特征 SHALL 独立报告 self/all mention、reply、self quote 和 image
- **AND** unknown SHALL 只进入安全诊断，不得进入正文或关键词匹配文本

#### Scenario: self quote 与普通 quote 可独立判断

- **WHEN** 一条消息的 reply segment 满足 `reply.data.sender_id == self_id`，另一条消息的 reply segment 指向其他用户
- **THEN** 两条结果 SHALL 都保留 reply 存在性和目标 ID
- **AND** 只有第一条结果 SHALL 报告 self quote

#### Scenario: 只有结构化内容

- **WHEN** 消息只包含合法 face、reply、image、record、video、file、forward、market_face、light_app、xml 或 markdown segment
- **THEN** 规范化结果 SHALL 保持为可处理的结构化消息
- **AND** SHALL 不因正文没有普通 text 而丢弃

#### Scenario: v1.3 不推断 mention here

- **WHEN** v1.3 消息只包含普通 text、mention 或 mention_all
- **THEN** mention 特征 SHALL 只报告 self、all 或 none
- **AND** SHALL 不从文本内容或 mention 名称生成 here 信号
