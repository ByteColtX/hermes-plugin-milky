# Spec Delta

## MODIFIED Requirements

### Requirement: 支持的 segment 必须保留类型和语义

消息 SHALL 容错识别 Milky v1.3 的 incoming segment：text、mention、mention_all、face、reply、
image、record、video、file、forward、market_face、light_app、xml 和 markdown，并保留每种
segment 的 typed 内容与必要 raw 字段。`image`、`record`、`video` SHALL 生成
`media_resource_references`，保留 `resource_id`、可选 `temp_url` 和 MIME/大小提示；`file`
SHALL 生成独立的 `file_attachment_references`，保留 `file_id`、`file_name`、`file_size`、
可选 `file_hash`，不得将其放入前一集合。

规范化正文 MUST 按原顺序使用以下可解释展示：`face` 为 `[face:<face_name>]`；其中当
`face_id` 匹配 `milky/face_catalog.json` 中非 `emoji 表情` pack 的非空 `qSid`，且对应
`qDes` 为非空字符串时，`face_name` SHALL 使用该 `qDes` 原值；`emoji 表情` pack 的条目
不得参与映射，`face_id` 本身 SHALL 作为 `face_name`。未匹配、目录不可用、目录结构无效、
条目字段缺失或对应名称不可用时，`face_name` SHALL 回退为原 `face_id`；`face_id` 缺失或
不可用时仍使用 `NOT SUPPORTED`。`packName` 不得作为 placeholder 的名称，也不得触发
除跳过 `emoji 表情` pack 外的名称转换。其他 placeholder SHALL 按原有规则生成：mention_all
为 `@全体成员`；`image` 为 `[img:file_name=<summary>]`，没有 summary 时回退为
`[img:file_name=<resource_id>]`；`record` 为 `[record:NOT SUPPORTED]`；`video` 为
`[video:resource_id=<resource_id>,duration=<duration>]`；`file` 为
`[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]`；`forward` 为
`[forward:forward_id=<forward_id>]`；`market_face` 为 `[market_face:summary=<summary>]`；
`xml` 为 `[xml:NOT SUPPORTED]`。视频 placeholder 的 `resource_id` 和 `duration` SHALL
分别使用协议字段值；字段缺失、`null` 或不可用时，该字段值 MUST 使用 `NOT SUPPORTED`。
所有其他 placeholder 缺少对应字段、字段为 `null` 或字段不可用时，也 MUST 使用
`NOT SUPPORTED`，不得补造 ID、文件名或哈希。视频 placeholder SHALL NOT 展示 `temp_url`。

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
`message_seq` 缺失并进入 `no_stable_message_seq` 降级外，规范化 SHALL 不补造 OpenAPI 必填
字段；reply 的 `message_seq`、`sender_id`、`time` 和 `segments` 缺失时 SHALL 保持 malformed
诊断。

#### Scenario: 已知数字 face 使用中文名称

- **WHEN** 入站 `face` 的 `face_id` 为 `14`，且 catalog 中非 `emoji 表情` pack 的该条目为 `qDes=/微笑`
- **THEN** 正文 SHALL 使用 `[face:/微笑]`
- **AND** `face` segment 的类型、`face_id` 和其他 typed 字段 SHALL 保持不变

#### Scenario: emoji 表情 pack 保留原始 emoji

- **WHEN** 入站 `face` 的 `face_id` 为 catalog `emoji 表情` pack 中的 `😊`
- **THEN** 正文 SHALL 使用 `[face:😊]`
- **AND** 系统 SHALL 不使用该 pack 条目的 `qDes` 或 `packName` 替换原始 emoji

#### Scenario: 未知 face ID 回退为原始 ID

- **WHEN** 入站 `face` 的 `face_id` 不存在于可用的非 `emoji 表情` pack 映射中
- **THEN** 正文 SHALL 使用 `[face:<face_id>]`
- **AND** 系统 SHALL 不丢弃该 `face` segment 或把未知 ID 转换为其他文本

#### Scenario: face catalog 不可用时保持安全回退

- **WHEN** catalog 文件缺失、无法解析、顶层结构无效，或条目的 `qSid`/`qDes` 缺失、为空或不是可用字符串
- **THEN** 受影响的 `face` placeholder SHALL 回退为原始 `face_id`
- **AND** normalizer SHALL 不执行网络请求、不把异常正文或完整路径写入消息正文、诊断或日志

#### Scenario: 冲突 catalog 条目不进行猜测

- **WHEN** 多个非 `emoji 表情` 条目为同一 `qSid` 提供不同的非空 `qDes`
- **THEN** 该 `qSid` SHALL 被视为不可确定映射并回退为原始 `face_id`
- **AND** 其他无冲突的 catalog 条目 SHALL 继续按其 `qDes` 映射

#### Scenario: 复合消息占位符保持顺序

- **WHEN** 消息按顺序包含文本、face、image、record、video、file、forward、market_face 和 xml
- **THEN** 规范化正文 SHALL 按相同顺序包含各自 placeholder
- **AND** face placeholder 只替换其显示值
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

- **WHEN** trigger 阶段 image helper 成功返回本地落盘路径，且该 occurrence 在当前 batch 中可计算内容摘要
- **THEN** 最终正文 SHALL 使用当前 batch 选定的首次代表路径 basename
- **AND** 该 basename SHALL 与 Hermes `media_urls` 中对应路径的 basename 相同
- **AND** SHALL 不使用 image `summary`、`resource_id` 或 helper 的其他随机命名作为跨 occurrence 的 identity

#### Scenario: multiple image placeholders keep helper basename order

- **WHEN** 一条消息或其可见 reply 内容按顺序包含多个 image occurrence，且其中若干 helper 返回路径的文件内容完全相同
- **THEN** 内容相同的 occurrence 的 placeholder SHALL 全部使用首次 occurrence 的代表 basename
- **AND** 内容不同的 occurrence SHALL 按首次出现顺序使用各自代表 basename
- **AND** 正文中 occurrence 的数量和原始顺序 SHALL 保持不变

#### Scenario: image hash unavailable keeps conservative identity

- **WHEN** image helper 成功但本地文件不可安全读取、文件状态不符合限制或 SHA-256 计算失败
- **THEN** 系统 SHALL 不宣称该 occurrence 与其他图片内容相同
- **AND** SHALL 保留该 occurrence 的独立 helper basename（若其路径仍是可交给 Hermes 的本地路径）或现有失败占位

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

#### Scenario: 视频 placeholder 展示资源 ID 和时长

- **WHEN** video segment 提供 `resource_id` 和以秒表示的 `duration`
- **THEN** 正文 SHALL 使用 `[video:resource_id=<resource_id>,duration=<duration>]`
- **AND** SHALL 不显示 `temp_url`、宽度、高度或未确认的媒体内容

#### Scenario: 视频 placeholder 字段缺失

- **WHEN** video segment 的 `resource_id` 或 `duration` 缺失、为 null 或不符合其协议类型
- **THEN** 对应 placeholder 字段 SHALL 使用 `NOT SUPPORTED`
- **AND** SHALL 不补造资源 ID 或时长
