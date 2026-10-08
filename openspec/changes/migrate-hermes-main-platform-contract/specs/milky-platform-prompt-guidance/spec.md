# Spec Delta

## MODIFIED Requirements

### Requirement: Milky 操作指引通过 system prompt section 提供

Milky 插件 MUST 使用当前 Hermes system prompt section 注册能力注册一个稳定、只属于 Milky 的 section。该 section 的首行 MUST 使用 Your QQ uid is {self_id}, and your nickname is {nickname}. 的格式；首行之后 MUST 按既定顺序提供以下 Milky 操作指引，且 MUST 使用 [SILENT] 作为无需回复的标记、使用 [SPLIT] 作为可选的文本分段标记：

```text
You can send files natively: write MEDIA:/absolute/path/to/file in your response. If no reply is needed, return only [SILENT] with no extra content. Hermes core keeps [SILENT] quiet when reply_expected is false. For true or unknown replies, core creates a fixed visible fallback, which Milky filters before QQ delivery; the turn may produce no QQ message even if Hermes records a successful send. The plugin does not parse [SILENT] separately. To optionally simulate natural chat pacing, put [SPLIT] alone on its own line or inline between text sections; it is case-sensitive, unescaped markers are removed, and the text is delivered in order as at most three text messages. Empty sections are not sent. Use [[SPLIT]] when the visible text must contain the literal [SPLIT]; complete CQ-compatible codes are parsed as units, while malformed CQ-like text follows ordinary text rules. For Hermes send_message, put the same MEDIA: directive in its message argument; images, audio, video, and documents use Milky's native media/file upload. MEDIA: is separate from the fixed QQ ToolSpec list. When a response contains both split text and MEDIA: attachments, Hermes delivers all text sections first and then attachments in extraction order; text sections and attachments cannot currently be interleaved. Use [CQ:at,qq=<uid>] to mention users and [CQ:reply,id=<message_seq>] to quote to messages; use only real IDs from the current message or channel context. Never send a raw local path as chat text or report media as unsupported before the send entry point fails. Load hermes-plugin-milky:milky-qq-cq-reference for QQ details or hermes-plugin-milky:milky-qq-action-tools for QQ action tools.
```

#### Scenario: 注册完整的 Milky section

- **WHEN** Hermes 上下文支持当前 system prompt section 注册能力
- **THEN** Milky SHALL 注册一个可渲染的 Milky system prompt section
- **AND** section 内容 SHALL 以动态 QQ 身份首行开始
- **AND** 身份首行之后 SHALL 包含 [SILENT]、[SPLIT]、行中分段、字面量转义和文本先于附件的媒体顺序指引
- **AND** 静态 `platform_hint` 与 section SHALL 不重复承载同一段其余操作指引

#### Scenario: 指引中的 `[SILENT]` 交给 Hermes core

- **WHEN** section 文案描述无需回复的 `[SILENT]`
- **THEN** 文案 SHALL 明确该标记由 Hermes core 处理，Milky plugin 不单独解析
- **AND** SHALL 说明当前 human turn 已确认未预期 Bot 回复时标记可保持静默
- **AND** SHALL 说明 human turn 预期回复或回复预期 unknown 时 core 会生成固定可见 fallback
- **AND** SHALL 说明 Milky 在 QQ 发送前过滤该精确 fallback，因此可能没有 QQ 消息，即使 Hermes 记录了成功发送结果

#### Scenario: 指引中的 `[SPLIT]` 说明完整且严格

- **WHEN** Agent 阅读 Milky section 中的 `[SPLIT]` 说明
- **THEN** 文案 SHALL 说明标记可以单独成行或出现在普通正文行中、大小写严格匹配、未转义标记会被删除且最多生成三条文本消息
- **AND** 文案 SHALL 说明空段不发送、[[SPLIT]] 用于字面量输出、完整 CQ-compatible code 按整体解析且 malformed CQ-like 文本遵循普通正文规则

#### Scenario: 指引说明附件不能与文本交错

- **WHEN** Agent 阅读同时包含文本分段和 `MEDIA:` 的 Milky section
- **THEN** 文案 SHALL 指示文本段先发送、附件后发送
- **AND** 文案 SHALL 明确当前不支持文本段与附件交错投递

### Requirement: 注册和降级保持 Milky 边界

操作指引 section 和独立的 QQ 会话介绍 section MUST 只由 Milky 根插件注册入口登记，不得修改 Hermes core、全局平台提示逻辑或其他平台的注册结果。会话介绍 section 使用 `hermes-plugin-milky.qq-session-context` 稳定 ID，读取通过 trigger handoff 登记的本地 friend/group snapshot；section callback MUST 不执行网络、文件或阻塞 I/O。section 注册阶段 MUST 遵守既有无网络、无 SSE 和无长期任务约束。插件 MUST 依赖当前 Hermes section 注册能力；缺少该能力时 MUST 在副作用发生前明确停止注册并报告 unsupported，不得回退为只注册 `platform_hint`。

#### Scenario: 注册阶段不产生连接副作用

- **WHEN** Hermes 调用 Milky 当前注册入口并提供 section 注册 API
- **THEN** 插件 SHALL 登记 section 和 platform 工厂
- **AND** SHALL NOT 调用 `get_login_info`、其他 Milky Action、SSE 或创建长期后台任务
- **AND** SHALL NOT 修改 Hermes core 文件或运行时逻辑

#### Scenario: 旧宿主缺少 section API

- **WHEN** Hermes 上下文没有当前 system prompt section 注册能力
- **THEN** Milky SHALL 明确报告 unsupported 并停止注册
- **AND** SHALL 不只注册工具、命令或 skills 后继续伪装为完整平台插件
- **AND** SHALL 不发送网络请求、不启动 SSE 或创建长期任务

#### Scenario: 其他平台不受影响

- **WHEN** Hermes 同时加载 Milky 与其他 platform plugin
- **THEN** 只有 Milky 注册的 section SHALL 包含 QQ 操作指引和 QQ 身份首行
- **AND** 其他平台的 `platform_hint`、system prompt section 和身份信息 SHALL 保持原有行为
