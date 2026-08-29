# chat-session-buffer Specification

## Purpose

为每个聊天提供有界、顺序稳定且不污染 Hermes transcript 的 wait 上下文，使 Will
可以积累待触发消息，并在 trigger 时一次性、安全地交接历史与当前消息。由于 Hermes
公开的平台适配器入口是触发型 turn，wait 消息不能逐条写入 Agent 或 transcript；批量
注入有界历史可以保留触发前的语义上下文，同时不为每条 wait 消息创建独立 Agent turn。

## Requirements

### Requirement: 每个 chat 使用独立 admission 和 ordered handoff

canonical、Gate、wait buffer、Will 和 trigger batch 交接 MUST 在同一 chat 的短暂 admission 串行边界中按 ingress sequence 完成。trigger batch 后续 MUST 进入同 chat 的有界 ordered handoff，按相同顺序完成资源补全、mapper 和 Hermes `handle_message()` 提交；不同 chat MAY 并行处理。该边界 MUST NOT 包含 Agent turn 执行。

#### Scenario: 同 chat 并发消息

- **WHEN** 同一 chat 的两条消息并发到达
- **THEN** 它们 SHALL 按该 chat 的到达顺序完成 canonical、Gate、buffer 和 Will 处理
- **AND** SHALL 不产生交叉的 trigger drain

#### Scenario: 不同 chat 并行

- **WHEN** group A 和 dm B 同时处理慢速业务
- **THEN** 一个 chat 的等待 SHALL 不改变另一个 chat 的顺序或状态

### Requirement: wait buffer 有界且可配置

系统 MUST 为每个 chat 使用独立的有界 wait buffer，默认上限为 20；配置为 0 时 SHALL 不保存历史；超限时 SHALL 丢弃最早消息并提供诊断。

#### Scenario: 缓冲区溢出

- **WHEN** 已有 maxlen 条历史消息又收到一条 wait 消息
- **THEN** buffer SHALL 保留最新 maxlen 条消息
- **AND** SHALL 记录最早消息被丢弃的安全 reason

#### Scenario: 禁用历史

- **WHEN** session buffer size 为 0 且 Will 返回 wait
- **THEN** 当前消息 SHALL 不写入历史 buffer
- **AND** 后续 trigger SHALL 不获得虚假的历史上下文

### Requirement: trigger 先原子 drain 再交接 detached batch

trigger MUST 在同 chat admission 边界中原子清空历史 wait buffer，并将历史构建为 detached batch；当前 trigger 消息 SHALL 只作为本次正文，不得重复放入 channel_context。交接给 Hermes 后必须立即释放该边界。

#### Scenario: 历史与当前消息交接

- **WHEN** buffer 中有两条历史消息且当前消息触发
- **THEN** 两条历史消息 SHALL 只进入一次 channel_context
- **AND** 当前消息 SHALL 只作为本次 MessageEvent 正文
- **AND** buffer SHALL 在交接开始前被清空

#### Scenario: detached 交接失败

- **WHEN** detached batch 交给后续处理失败
- **THEN** 系统 SHALL 只重试同一 batch 或记录不可恢复失败
- **AND** SHALL NOT 无条件把同一批消息重新追加到 buffer

### Requirement: 历史上下文使用稳定紧凑文本格式

detached batch 转换为 `channel_context` 时 MUST 只包含按最早到最新顺序排列的规范化历史
消息记录。每条记录 MUST 使用以下紧凑纯文本格式，尖括号表示字段值而不是输出字符：

~~~text
[<sender_name> uid <sender_id> msg_id <message_id> reply_id <reply_id>]
<body>
~~~

`msg_id` 和 `reply_id` 字段在没有值时 MUST 省略，并保持上述字段顺序；多条记录之间 MUST
使用一个换行拼接，不能增加 JSON、额外历史标题或重复群号。`body` MUST 来自规范化消息
内容和可解释的媒体/回复降级标记，不得来自 raw payload。没有历史记录时
`channel_context` MUST 为 `None`，而不是空字符串。

header 中的非可信值 MUST 将反斜杠编码为 `\\`、右方括号编码为 `\]`、回车和换行编码
为字面量 `\n`；body 中的回车和换行也 MUST 编码为字面量 `\n`，以免伪造新的历史记录。
历史上下文 MUST NOT 包含 timestamp、dedup key、认证信息或插件本地媒体路径。

#### Scenario: 多条历史消息按 FIFO 拼接

- **WHEN** detached batch 依次包含 sender `Alice` 的消息 `7` 和 sender `Bob` 回复消息 `8`
- **THEN** `channel_context` SHALL 形成为：
  ~~~text
  [Alice uid 101 msg_id 7]
  第一条
  [Bob uid 202 msg_id 8 reply_id 7]
  第二条
  ~~~
- **AND** SHALL 保持历史的最早到最新顺序
- **AND** SHALL 不包含当前 trigger 消息或额外群 ID

#### Scenario: 上下文为空或包含非可信文本

- **WHEN** detached batch 为空，或 sender name/body 含有右方括号、反斜杠或换行
- **THEN** 空 batch 的 `channel_context` SHALL 为 `None`
- **AND** 非可信字符 SHALL 按规定编码而不改变记录边界
- **AND** 原始 payload、认证信息和本地媒体路径 SHALL 不进入该字符串

### Requirement: wait 不写入 Hermes transcript

Will 返回 wait 的消息 MUST 只保存在插件拥有的有界 buffer 中，直到被丢弃、drain 或明确失败；wait 阶段 SHALL NOT 调用 Hermes Agent 或写入 Hermes transcript。

#### Scenario: wait 消息

- **WHEN** 一条通过 Gate 的消息得到 wait 决策
- **THEN** Hermes SHALL 不收到该消息的 turn
- **AND** 插件 buffer SHALL 按配置保存或明确丢弃它

#### Scenario: Hermes 忙碌不扩大插件锁

- **WHEN** 当前 trigger 交给 Hermes 后 Agent 仍在执行
- **THEN** 插件 SHALL 释放该 chat 的 admission 边界
- **AND** 后续消息 SHALL 由 Hermes 的 busy/follow-up/interrupt 及单槽 pending 语义处理，而不是在插件中等待 Agent 完成或复制 Agent 队列
