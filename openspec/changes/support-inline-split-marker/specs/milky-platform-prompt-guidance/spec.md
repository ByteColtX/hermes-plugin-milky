## MODIFIED Requirements

### Requirement: Milky 操作指引通过 system prompt section 提供

当 Hermes 提供 system prompt section 注册能力时，Milky 插件 MUST 注册一个稳定、只属于 Milky 的 section。该 section 的首行 MUST 使用 Your QQ uid is {self_id}, and your nickname is {nickname}. 的格式；首行之后 MUST 按既定顺序提供以下 Milky 操作指引，且 MUST 使用 [SILENT] 作为无需回复的标记、使用 [SPLIT] 作为可选的文本分段标记：

~~~text
You can send files natively: write MEDIA:/absolute/path/to/file in your response. If no reply is needed, return only [SILENT] with no extra content. [SILENT] is handled by Hermes core and means no output; the plugin does not parse it separately. To optionally simulate natural chat pacing, put [SPLIT] alone on its own line or inline between text sections; it is case-sensitive, unescaped markers are removed, and the text is delivered in order as at most three text messages. Empty sections are not sent. Use [[SPLIT]] when the visible text must contain the literal [SPLIT]; complete CQ-compatible codes are parsed as units, while malformed CQ-like text follows ordinary text rules. For Hermes send_message, put the same MEDIA: directive in its message argument; images, audio, video, and documents use Milky's native media/file upload. MEDIA: is separate from the fixed QQ ToolSpec list. When a response contains both split text and MEDIA: attachments, Hermes delivers all text sections first and then attachments in extraction order; text sections and attachments cannot currently be interleaved. Use [CQ:at,qq=<uid>] to mention users and [CQ:reply,id=<msg_id>] to quote to messages; use only real IDs from the current message or channel context. Never send a raw local path as chat text or report media as unsupported before the send entry point fails. Load hermes-plugin-milky:milky-qq-cq-reference for CQ details or hermes-plugin-milky:milky-qq-action-tools for QQ action tools.
~~~

#### Scenario: 注册完整的 Milky section

- **WHEN** Hermes 上下文支持 register_system_prompt_section
- **THEN** Milky SHALL 注册一个可渲染的 Milky system prompt section
- **AND** section 内容 SHALL 以动态 QQ 身份首行开始
- **AND** 身份首行之后 SHALL 包含 [SILENT]、[SPLIT]、行中分段、字面量转义和文本先于附件的媒体顺序指引
- **AND** 静态 platform_hint 与 section SHALL 不重复承载同一段其余操作指引

#### Scenario: 指引中的 `[SILENT]` 交给 Hermes core

- **WHEN** section 文案描述无需回复的 [SILENT]
- **THEN** 文案 SHALL 明确该标记由 Hermes core 处理
- **AND** Milky plugin SHALL 不因该文案新增独立标记解析、出站 Action 或用户可见文本

#### Scenario: 指引中的 `[SPLIT]` 说明完整且严格

- **WHEN** Agent 阅读 Milky section 中的 [SPLIT] 说明
- **THEN** 文案 SHALL 说明标记可以单独成行或出现在普通正文行中、大小写严格匹配、未转义标记会被删除且最多生成三条文本消息
- **AND** 文案 SHALL 说明空段不发送、[[SPLIT]] 用于字面量输出、完整 CQ-compatible code 按整体解析且 malformed CQ-like 文本遵循普通正文规则

#### Scenario: 指引说明附件不能与文本交错

- **WHEN** Agent 阅读同时包含文本分段和 MEDIA: 的 Milky section
- **THEN** 文案 SHALL 指示文本段先发送、附件后发送
- **AND** 文案 SHALL 明确当前不支持文本段与附件交错投递
