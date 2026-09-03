## MODIFIED Requirements

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
成功落盘后，最终正文 MUST 将对应 image placeholder 替换为
`[img:file_name=<basename>]`，其中 `<basename>` MUST 与交给 Hermes `media_urls` 的对应路径
basename 一致。helper 不可用、下载失败或返回无效本地路径时，正文 MUST 使用
`[img:file_name=NOT SUPPORTED]`；不得继续使用 `summary` 作为成功占位文件名。

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
