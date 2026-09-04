## MODIFIED Requirements

### Requirement: Milky 操作指引通过 system prompt section 提供

当 Hermes 提供 system prompt section 注册能力时，Milky 插件 MUST 注册一个稳定、只属于 Milky 的 section。该 section 的首行 MUST 使用 `Your QQ uid is {self_id}, and your nickname is {nickname}.` 的格式；首行之后 MUST 按既定顺序提供以下 Milky 操作指引，且 MUST 使用 `[SILENT]` 作为无需回复的标记、使用 `[SPLIT]` 作为可选的文本分段标记：

```text
You can send files natively: write MEDIA:/absolute/path/to/file in your response. If no reply is needed, return only [SILENT] with no extra content. [SILENT] is handled by Hermes core and means no output; the plugin does not parse it separately. To optionally simulate natural chat pacing, put [SPLIT] alone on its own line between text sections; it is case-sensitive, the marker line is removed, and the text is delivered in order as at most three text messages. Empty sections are not sent. For Hermes `send_message`, put the same MEDIA: directive in its `message` argument; images, audio, video, and documents use Milky's native media/file upload. MEDIA: is separate from the fixed QQ ToolSpec list. When a response contains both split text and MEDIA: attachments, Hermes delivers all text sections first and then attachments in extraction order; text sections and attachments cannot currently be interleaved. Use [CQ:at,qq=<uid>] to mention users and [CQ:reply,id=<msg_id>] to quote to messages; use only real IDs from the current message or channel context. Never send a raw local path as chat text or report media as unsupported before the send entry point fails. Load `hermes-plugin-milky:qq-reference` for CQ details or `hermes-plugin-milky:qq-tools` for QQ tools.
```

#### Scenario: 注册完整的 Milky section

- **WHEN** Hermes 上下文支持 `register_system_prompt_section`
- **THEN** Milky SHALL 注册一个可渲染的 Milky system prompt section
- **AND** section 内容 SHALL 以动态 QQ 身份首行开始
- **AND** 身份首行之后 SHALL 包含 `[SILENT]`、`[SPLIT]` 和文本先于附件的媒体顺序指引
- **AND** 静态 `platform_hint` 与 section SHALL 不重复承载同一段其余操作指引

#### Scenario: 指引中的 `[SILENT]` 交给 Hermes core

- **WHEN** section 文案描述无需回复的 `[SILENT]`
- **THEN** 文案 SHALL 明确该标记由 Hermes core 处理
- **AND** Milky plugin SHALL 不因该文案新增独立标记解析、出站 Action 或用户可见文本

#### Scenario: 指引中的 `[SPLIT]` 说明完整且严格

- **WHEN** Agent 阅读 Milky section 中的 `[SPLIT]` 说明
- **THEN** 文案 SHALL 说明标记必须单独成行、大小写严格匹配、标记会被删除且最多生成三条文本消息
- **AND** 文案 SHALL 说明空段不发送

#### Scenario: 指引说明附件不能与文本交错

- **WHEN** Agent 阅读同时包含文本分段和 `MEDIA:` 的 Milky section
- **THEN** 文案 SHALL 指示文本段先发送、附件后发送
- **AND** 文案 SHALL 明确当前不支持文本段与附件交错投递

### Requirement: section 身份来自连接后的账号缓存

Milky system prompt section MUST 从同一插件注册实例创建的 adapter 在 `connect()` 完成登录和必要初始状态同步后缓存的账号信息读取 `self_id` 与 `nickname`。section 渲染 MUST 只读该缓存，MUST NOT 发起 Milky HTTP/SSE 请求、调用新的远端 Action 或从 session metadata、入站正文和配置猜测身份。

#### Scenario: 连接成功后渲染真实身份

- **WHEN** `connect()` 完成账号登录信息确认和既有初始状态同步，并缓存有效的 QQ UID 与昵称
- **THEN** 新 session 的 Milky section 首行 SHALL 使用该缓存值渲染
- **AND** 渲染结果 SHALL 形如 `Your QQ uid is <decimal uid>, and your nickname is <nickname>.`
- **AND** section SHALL 使用缓存值而不是再次查询 Milky

#### Scenario: 初始同步失败时不伪造身份

- **WHEN** `connect()` 未完成或账号信息未被成功确认
- **THEN** section SHALL 不注入未知、默认或猜测的 UID/昵称
- **AND** SHALL 不因渲染 section 打开网络连接
- **AND** `platform_hint` SHALL 仍只提供其首句

#### Scenario: 已连接身份在 prompt 渲染期间保持只读

- **WHEN** Hermes 在同一 session 内重复构建或恢复已冻结的 system prompt
- **THEN** section SHALL 使用已缓存且已渲染的身份和文案
- **AND** SHALL 不触发账号信息重新获取或改变 Milky 连接、pipeline、Will 和出站生命周期
