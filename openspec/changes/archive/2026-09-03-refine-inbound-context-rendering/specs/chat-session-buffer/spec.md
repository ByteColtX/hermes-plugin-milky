## MODIFIED Requirements

### Requirement: 历史上下文使用稳定紧凑文本格式

detached batch 转换为 `channel_context` 时 MUST 按 ingress sequence 保留其中的普通历史消息
和已登记的 context-only 系统事件。普通消息每条 MUST 使用单行格式：

~~~text
<sender uid <sender_id> msg_id <message_id> reply_to <reply_id>> <body>
~~~

`msg_id` 和 `reply_to` 没有值时 MUST 省略，并保持字段顺序；普通消息 header 和 body 之间
使用一个空格。系统事件 MUST 使用 `<event <event_type>> <body>` 格式，不得伪装成普通消息
或 segment placeholder。普通消息的 `body` MUST 来自规范化消息内容和本 change 定义的
结构化占位符；系统事件的 body MUST 来自事件字段的可读渲染。普通消息和系统事件之间
MUST 使用一个换行拼接；不得添加额外历史标题。

当前 trigger 消息 MUST 只进入本次 `MessageEvent.text`，不得进入 `channel_context`；没有
历史消息和待注入系统事件时，`channel_context` MUST 为 `None`，而不是空字符串。

header 中的非可信值 MUST 将尖括号、反斜杠、回车和换行编码为不会改变记录边界的字面量；
body 中的回车和换行也 MUST 编码为字面量 `\\n`。上下文 MUST NOT 包含 timestamp、dedup key、
认证信息或插件本地媒体路径。

#### Scenario: 普通历史和当前消息分离

- **WHEN** detached batch 包含两条 wait 普通消息，当前 trigger 另有一条消息
- **THEN** `channel_context` SHALL 只包含两条历史的单行记录
- **AND** 每条记录 SHALL 使用 `<sender uid ... msg_id ... reply_to ...> body` 格式
- **AND** 当前 trigger 消息 SHALL 只出现在 `MessageEvent.text`

#### Scenario: 多条历史消息按 FIFO 拼接

- **WHEN** detached batch 依次包含两条历史普通消息
- **THEN** `channel_context` SHALL 按最早到最新的 ingress sequence 形成单行记录
- **AND** 每条记录 SHALL 包含可用的 sender、uid、msg_id 和 reply_to 字段
- **AND** SHALL 不包含当前 trigger 消息或额外群 ID

#### Scenario: 系统事件与普通历史按顺序合并

- **WHEN** 一个 chat 先后产生普通 wait 消息、`group_nudge` 和 `group_member_increase`
- **THEN** 下次 trigger 的 `channel_context` SHALL 按 ingress sequence 混合排列这些记录
- **AND** 系统事件 SHALL 使用 `<event group_nudge> ...` 或 `<event group_member_increase> ...` 格式
- **AND** 系统事件 SHALL NOT 形成独立 Hermes turn

#### Scenario: 没有上下文

- **WHEN** trigger 发生时没有历史 wait 消息和待注入系统事件
- **THEN** `channel_context` SHALL 为 `None`
- **AND** 当前消息 SHALL 仍使用单行 header 和正文格式交给 Hermes

#### Scenario: 上下文包含边界字符

- **WHEN** sender name 或 body 含有尖括号、反斜杠或换行
- **THEN** 这些字符 SHALL 被编码而不伪造新的 context record
- **AND** 原始 payload SHALL NOT 被直接拼接到上下文

#### Scenario: 上下文为空或包含非可信文本

- **WHEN** detached batch 为空，或 sender name/body 含有右方括号、反斜杠、尖括号或换行
- **THEN** 空 batch 的 `channel_context` SHALL 为 `None`
- **AND** 非可信字符 SHALL 按规定编码而不改变记录边界
- **AND** 原始 payload、认证信息和插件本地媒体路径 SHALL NOT 被直接拼接

## ADDED Requirements

### Requirement: context-only 系统事件使用独立有界缓冲

系统 MUST 为每个可识别 chat 维护独立、有界、可丢失的 context-only 事件缓冲。该缓冲与
普通 wait buffer 分离，不得进入普通 canonical、Will 或 reply cost 状态。登记的系统事件
只有在后续同 chat trigger 时作为 `channel_context` 注入一次；注入后 MUST 原子清除，溢出时
MUST 丢弃最早事件并记录安全诊断。系统事件无可确认 chat key 时 MUST 只观察，不得创建
全局或默认 chat 的上下文。

#### Scenario: 系统事件等待下一次 trigger

- **WHEN** `group_nudge` 或群成员变更事件在没有 trigger 的时期到达
- **THEN** 事件 SHALL 进入对应 group chat 的 context-only 缓冲
- **AND** SHALL 不调用 Hermes、Will 或普通 wait buffer
- **AND** 下一次该 chat trigger SHALL 消费这些事件一次

#### Scenario: 系统事件缓冲溢出

- **WHEN** context-only 缓冲达到上限后又收到新事件
- **THEN** 系统 SHALL 保留最新上限数量的事件
- **AND** SHALL 丢弃最早事件并记录不含正文的溢出诊断

#### Scenario: 无法建立 chat key

- **WHEN** 系统事件缺少或包含非法群号/好友号
- **THEN** 系统 SHALL 保持 observe-only
- **AND** SHALL NOT 写入任何 chat context、普通 buffer 或 Hermes transcript
