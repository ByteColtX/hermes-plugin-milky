## MODIFIED Requirements

### Requirement: 支持的 segment 必须保留类型和语义

消息 SHALL 容错识别 Milky v1.3 的 incoming segment：text、mention、mention_all、face、reply、
image、record、video、file、forward、market_face、light_app、xml 和 markdown，并保留每种
segment 的 typed 内容与必要 raw 字段。`image`、`record`、`video` SHALL 生成
`media_resource_references`，保留 `resource_id`、可选 `temp_url` 和 MIME/大小提示；`file`
SHALL 生成独立的 `file_attachment_references`，保留 `file_id`、`file_name`、`file_size`、
可选 `file_hash`，不得将其放入前一集合。

规范化正文 MUST 按原顺序使用以下可解释展示：`face` 为 `[face:<face_id>]`；`image` 为
`[img:<summary>]`，没有 summary 时回退为 `[img:<resource_id>]`；`record` 为
`[record:NOT SUPPORTED]`；`video` 为 `[video:NOT SUPPORTED]`；`file` 为
`[file:<file_id>]`；`forward` 为 `[forward:<forward_id>]`；`market_face` 为
`[market_face:NOT SUPPORTED]`；`xml` 为 `[xml:NOT SUPPORTED]`。缺少对应标识时，相关
placeholder MUST 使用 `NOT SUPPORTED`，不得补造 ID。

`light_app` SHALL 解析 `json_payload`。当 payload 是 JSON object 且存在 `meta` 字段时，
正文 MUST 以 `[light_app:{"meta":...}]` 开始，并完整递归保留 `meta` 字段下的所有 key、
value、数组和 null；不得假设 `meta` 下的字段数量、名称或层级。payload 顶层除 `meta` 外
的字段 MUST 忽略。`contact` 等具体卡片类型仍统一展示为 `light_app`，不得增加独立
segment 类型。payload 无法解析或没有 `meta` 字段时，正文 MUST 为
`[light_app:NOT SUPPORTED]`。Markdown 内容 SHALL 原样进入正文。

完整 inline `reply` SHALL 只保留 reply 目标供 `reply_to` header 和 Hermes reply metadata 使用，
不得在正文中额外追加 `[引用]` 或其他成功占位符。reply 缺少协议必填字段或 trigger 查询失败
时，正文 MAY 使用 `[reply:NOT SUPPORTED]`，并保留 malformed 或安全资源诊断。

`file` 只属于入站消息，不属于 outgoing message segment。除架构明确允许主消息
`message_seq` 缺失并进入 `no_stable_message_id` 降级外，规范化 SHALL 不补造 OpenAPI 必填
字段；reply 的 `message_seq`、`sender_id`、`time` 和 `segments` 缺失时 SHALL 保持 malformed
诊断。

#### Scenario: 复合消息占位符保持顺序

- **WHEN** 消息按顺序包含文本、face、image、record、video、file、forward、market_face 和 xml
- **THEN** 规范化正文 SHALL 按相同顺序包含各自 placeholder
- **AND** SHALL 不把未支持的 record、video、market_face 或 xml 静默变成普通文本

#### Scenario: 复合消息

- **WHEN** 消息同时包含文本、提及、回复和图片
- **THEN** 规范化结果 SHALL 保留各 segment 的顺序和类型
- **AND** SHALL 生成对应的正文、mention、quote 和 image 信号

#### Scenario: 文件入站

- **WHEN** 消息包含 file segment
- **THEN** 规范化结果 SHALL 保留 file ID、名称和大小提示的独立文件引用
- **AND** SHALL NOT 将其当成出站文件 segment 或本地路径

#### Scenario: Milky v1.3 真实字段形状

- **WHEN** 消息包含 image、reply 或 forward
- **THEN** 规范化 SHALL 保留 resource、reply 和 forward 的协议字段及原始类型
- **AND** SHALL NOT 将这些字段改名为 OneBot 字段或把 forward 误当成已展开消息

#### Scenario: 文件字段只有协议引用

- **WHEN** file segment 提供 file_id、file_name、file_size 和可空 file_hash
- **THEN** 结果 SHALL 将这些字段保留为独立文件引用
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

### Requirement: 规范化结果必须提供稳定策略特征

规范化 SHALL 在不重新读取 raw payload 的情况下提供稳定的有序正文和策略特征：至少包括
事件类型、场景、时间、正文/策略文本、独立的 self/all/here/none mention 信号、reply
存在性与目标 ID、image 存在性、typed segments、分类后的延迟引用
（`media_resource_references`、`file_attachment_references`、forward/reply references）
和安全诊断。text 与 markdown 内容 SHALL 按原顺序保留；face、image、record、video、file、
forward、market_face、light_app 和 xml SHALL 使用本 requirement 定义的可解释 placeholder；
unknown segment SHALL 不进入正文或关键词内容。reply/forward 的嵌套内容 SHALL 保留为引用
数据，不得隐式并入当前消息正文。

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
- **THEN** 规范化正文 SHALL 保持受支持内容顺序和对应 placeholder
- **AND** 策略特征 SHALL 独立报告 mention、reply 和 image
- **AND** unknown SHALL 只进入安全诊断，不得进入正文或关键词匹配文本

#### Scenario: 只有结构化内容

- **WHEN** 消息只包含合法 face、reply、image、record、video、file、forward、market_face、light_app、xml 或 markdown
- **THEN** 规范化结果 SHALL 保持为可处理的结构化消息
- **AND** SHALL 不因正文没有普通 text 而丢弃

#### Scenario: v1.3 不推断 mention here

- **WHEN** v1.3 消息只包含普通 text、mention 或 mention_all
- **THEN** mention 特征 SHALL 只报告 self、all 或 none
- **AND** SHALL 不从文本内容或 mention 名称生成 here 信号
