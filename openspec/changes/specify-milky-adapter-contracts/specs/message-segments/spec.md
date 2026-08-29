## Purpose

定义 Milky 消息 segment 的容错解析和可解释降级，让文本、提及、引用、媒体与未知
扩展既能形成稳定策略信号，又不会把协议未知内容悄悄伪装成普通文本或执行指令。

## ADDED Requirements

### Requirement: 支持的 segment 必须保留类型和语义

消息 SHALL 容错识别 Milky v1.3 的 incoming segment：text、mention、mention_all、face、reply、image、record、video、file、forward、market_face、light_app、xml 和 markdown，并保留每种 segment 的 typed 内容与必要 raw 字段。资源段 SHALL 保留 Milky 的 `resource_id`、`temp_url`、`file_id`、`file_name`、`file_size` 等协议字段；`file` 只属于入站消息，不属于 outgoing message segment。

#### Scenario: 复合消息

- **WHEN** 消息同时包含文本、提及、回复和图片
- **THEN** 规范化结果 SHALL 保留各 segment 的顺序和类型
- **AND** SHALL 生成对应的正文、mention、quote 和 image 信号

#### Scenario: Milky v1.3 真实字段形状

- **WHEN** 收到包含 `image`、`reply` 或 `forward` 的 Milky 消息
- **THEN** image SHALL 识别 `resource_id`、`temp_url`、尺寸、摘要和 `sub_type`，reply SHALL 保留 `message_seq`、sender、time 和嵌套 segments，forward SHALL 保留 `forward_id`、`title`、`preview` 和 `summary`
- **AND** SHALL 不把这些字段改名为 OneBot 字段或把 forward 误当作已经展开的嵌套消息

#### Scenario: 文件入站

- **WHEN** 消息包含文件 segment
- **THEN** 规范化结果 SHALL 保留 file ID、名称和远端引用提示
- **AND** SHALL NOT 将其当成出站文件 segment 或本地路径

#### Scenario: 文件字段只有协议引用

- **WHEN** 入站 file segment 提供 `file_id`、`file_name`、`file_size` 和可空的 `file_hash`
- **THEN** 结果 SHALL 保留这些字段作为远端文件引用
- **AND** SHALL 不要求 file segment 提供 `temp_url`，也 SHALL 不把文件名解释成本地可读路径

### Requirement: 提及和回复信号必须可区分

规范化 SHALL 区分 mention self、mention all、mention here 和 none，并保留 reply 目标 ID；是否提及 Bot 和是否引用 Bot SHALL 可独立判断。Milky v1.3 只有 `mention` 和 `mention_all` segment，没有独立的 `mention_here` segment；normalizer MUST NOT 从普通文本或 `mention` 的名称臆造 here 信号，除非未来协议扩展被明确识别。

#### Scenario: 提及 Bot 与全体提及

- **WHEN** 消息分别包含直接提及 Bot、`mention_all` 或 here 提及
- **THEN** 结果 SHALL 产生对应的 self、all 或 here mention kind
- **AND** routing SHALL 能按不同信号选择不同策略

#### Scenario: 引用目标不可补全

- **WHEN** reply segment 只有目标 ID而远端原文尚未查询
- **THEN** 结果 SHALL 保留目标 ID
- **AND** SHALL 不将缺失的原文伪造成正文

#### Scenario: reply 已经携带原文

- **WHEN** reply segment 已提供目标 `message_seq`、作者、时间和嵌套 segments
- **THEN** 规范化 SHALL 保留这些内嵌信息
- **AND** trigger SHALL NOT 为同一 reply 强制重复调用 `get_message`

### Requirement: 媒体只生成延迟资源引用

normalization MUST 不执行网络 I/O 或下载，并 SHALL 只保存 Milky 的 `temp_url`、`resource_id`、`file_id`、`file_name`、`file_size`、名称、MIME/大小提示和原始 segment，供 trigger 阶段使用。`forward_id` 也只能作为延迟引用保存。

#### Scenario: wait 阶段遇到图片

- **WHEN** 消息包含图片且 Will 决策为 wait
- **THEN** 缓冲记录 SHALL 只包含可校验的图片引用
- **AND** SHALL 不调用资源接口或下载文件

#### Scenario: forward 只保存延迟引用

- **WHEN** 消息包含只有 `forward_id` 和预览信息的 forward segment
- **THEN** wait 记录 SHALL 保存该引用而不是展开内容
- **AND** trigger 才 MAY 调用 `get_forwarded_messages`，且失败时 SHALL 保留可解释占位

#### Scenario: 媒体引用字段不完整

- **WHEN** 媒体缺少可用 URL、file_id 或 file 提示
- **THEN** 结果 SHALL 保留 raw 并生成可解释的不可用媒体占位
- **AND** SHALL 不把未知字段转换为普通 Agent 指令

### Requirement: 未知内容和空消息必须安全降级

未知 segment（包括扩展协议字段）SHALL 保留安全 raw 与诊断；未知 segment MUST NOT 使用 Milky schema 的 `[unknown]` 默认文本值；消息没有任何受支持正文或媒体内容时 MUST 明确记录丢弃原因并停止。合法的 face、reply、媒体、forward、market_face、light_app、xml 和 markdown 属于受支持结构化内容，即使其正文文本为空。

#### Scenario: 未知 segment 与文本并存

- **WHEN** 消息包含未知 segment 以及合法文本
- **THEN** 文本 SHALL 保持可处理
- **AND** 未知 segment SHALL 只进入 metadata/raw，不得静默变成可执行文本

#### Scenario: 消息没有受支持内容

- **WHEN** 消息只包含无法解释的 segment 或为空
- **THEN** 系统 SHALL 记录明确的丢弃原因
- **AND** SHALL NOT 创建空的 Hermes MessageEvent
