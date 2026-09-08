## Context

当前 `MilkyOutboundSender` 对普通字符串先解析 `[SPLIT]`，再按默认 `4096` 个 Python Unicode 字符分块，并逐条调用目标场景对应的消息 Action。普通 `[SPLIT]` 路径最多允许三条顶层文本消息；`outbound/formatter.py` 已能校验 outgoing `forward` segment，但 sender 尚未把文本分块和 native media 转换为 forward 节点。Milky v1.3 的 `send_group_message`/`send_private_message` 接收 `OutgoingSegment[]`，其中 `forward.data.messages[]` 的节点必填 `user_id`、`sender_name`、`segments`；`file` 不在 outgoing segment 集合中。配置目前只在启动阶段解析。live adapter 的初始同步已经确认 Bot 的 `self_id` 和昵称，但 sender 尚未设计连接完成后的身份绑定；standalone sender 也没有定义 `get_login_info({})` 的失败和不安全昵称语义。

本 change 的行为契约见 proposal.md 及三个 delta spec。重点约束是：一旦阈值判断选择合并转发，所有文本发送单元都必须进入一个 `forward.messages` 数组，不能先发送部分普通消息再发送 forward。

## Goals / Non-Goals

**Goals:**

- 增加默认值为 `0`、范围为 `0..4096` 的 `MILKY_LONG_TEXT_FORWARD_THRESHOLD`，并保持未配置部署的行为不变。
- 在现有文本解析和长度边界基础上生成有序 forward nodes，使普通长文本、任意数量的 `[SPLIT]` 非空逻辑段和同一出站批次中的 native 图片/语音/视频都能由一次消息 Action 发送，并为节点提供真实身份或固定安全 fallback 身份。
- 复用已确认的 Milky outgoing forward schema、目标路由、CQ-compatible segment 转换和现有安全失败分类。
- 在网络访问前完成身份、节点 schema、空内容和本地资源物化前置条件的整体预检，避免产生部分发送。
- 让 live adapter 复用连接后确认的 Bot `user_id`/昵称，让 standalone 在需要时读取 `get_login_info({})`；身份缺失、读取失败或昵称不安全时统一使用固定 `user_id=10001`、`sender_name=QQ用户`。

**Non-Goals:**

- 不改变默认的普通分块、普通 `[SPLIT]` 三条顶层消息限制、目标 namespace 或附件先后顺序。
- 不把文档/文件 upload 结果或未知入站 `forward_id` 展开内容嵌入自动生成的 forward；文档/文件不在本 change 范围内，继续走现有独立 upload。
- 不新增 forward 的任意 Action、ToolSpec、跨消息缓存或重试机制。
- 不为未确认的 Milky 服务端 request-body 总大小、forward 节点数或客户端展示能力猜测协议上限；这些限制在实机验证前保持为风险边界。

## Decisions

### 1. 使用阈值配置而不是新的消息控制标记

`MILKY_LONG_TEXT_FORWARD_THRESHOLD` 以一次出站文本的可见规范化长度作为触发条件。`0` 明确关闭，正数表示严格“大于”阈值才触发。这样部署者可以统一控制行为，不需要让 Agent 学习新的正文控制语法，也不会与 `[SPLIT]` 的显式节奏控制混淆。

备选方案是新增 `[FORWARD]` 标记或把普通长文本默认改为 forward。前者会扩展 Agent-facing 语法，后者会改变所有现有部署的消息外观；两者都不符合默认关闭和启动配置的要求。

### 2. 在普通三条预检之前建立 forward 节点列表

文本处理分为两条明确路径：

```text
parse outbound text
        |
        v
calculate visible normalized length
        |
  +-----+-----+
  |           |
 <= threshold  > threshold and threshold > 0
  |           |
  v           v
existing      preserve every non-empty [SPLIT]
top-level     section, then chunk each section
delivery      into one forward.messages list
```

forward 路径必须使用解析器提供的全部非空 sections，不调用普通路径把尾部合并到第三段的逻辑；每个 section 再沿用现有安全切点和 `4096` 字符边界。最终 sender 只看到一个包含单一 `forward` segment 的顶层消息，因此普通路径的三条顶层限制不适用于 forward 节点数量。

普通路径仍保持原流程：超过三条的有效 `[SPLIT]` 物理消息在首个 Action 前整体失败，普通长文本按原顺序逐条发送并保留部分成功结果。

### 3. 使用一个 forward segment 和一次消息 Action

每个节点使用既有 `forward_segment` schema 所需的 `user_id`、`sender_name` 和 `segments`。节点中的文本 chunk 经过与普通消息相同的 CQ-compatible 转换；`image`、`record`、`video` 等 native media 作为节点内的 outgoing segments 参与同一 forward，再由 forward formatter 做嵌套 schema 校验。不设置没有来源的 `time`、`title`、`preview` 或其他展示字段。群聊和私聊仍分别调用 `send_group_message` 与 `send_private_message`。

请求体的具体形状是：群聊为 `{"group_id": <id>, "message": [{"type": "forward", "data": {"messages": [...]}}]}`，私聊将目标字段替换为 `user_id`；每个节点必须有 `user_id`、`sender_name` 和 `segments`。成功响应是标准 envelope 的 `data.message_seq`/`data.time`，插件只返回一个 `message_id`，不生成 `forward_id`。standalone 需要身份时使用 `get_login_info` 的 `{}` 请求和 `data.uin`/`data.nickname` 响应。

一次 forward 发送成功只产生一个远端 `message_seq`，不生成 continuation IDs。协议拒绝、timeout 或 transport unknown 不触发普通分块 fallback 或重试，因为远端可能已经产生副作用。

### 4. 身份来源和 fallback 按生命周期分层处理

- live adapter 在连接初始同步完成后，将已确认的 Bot `self_id` 和经安全规范化的昵称绑定到 sender；forward 发送不重复调用 `get_login_info`。若连接身份缺失、昵称为空或包含控制字符，则 forward 使用固定 fallback `user_id=10001`、`sender_name=QQ用户`。
- standalone sender 在普通分块路径不增加身份请求；只有阈值触发 forward 时才调用一次 `get_login_info({})`。成功且 `uin` 与昵称通过相同安全校验时使用真实身份；Action 被拒绝、transport unknown、timeout、malformed，或昵称为空/包含控制字符时，使用固定 fallback。
- fallback 是明确的协议合法值，不从当前正文、历史消息、`forward_id` 或异常正文推断；仍必须经过 forward formatter 的 ID/非空文本校验。若固定 fallback 自身无法通过 schema 校验，则在任何消息 Action 前返回 `malformed`。

该选择避免 live adapter 因每次发送重复联网，也让 standalone 不依赖一个不存在的长期 session；身份读取属于只读前置条件。fallback 会让用户侧看到合成身份而非假装是真实 Bot，日志只记录 `identity_source=confirmed|fallback`，不记录昵称原文或响应正文。

### 5. Native media 进入同一个 forward，文件排除在本 change 外

Milky 的 `OutgoingSegment` 明确允许 `image`、`record`、`video` 作为 `OutgoingForwardedMessage.segments`，因此同一出站批次中的 native media 必须和文本节点一起进入同一个 `forward`。文档/文件没有 outgoing `file` segment，因此它们明确排除在本 change 外：不构造成 forward segment，也不改变现有独立 file upload 行为。

当前 Hermes 对独立 `MEDIA:` 指令可能向 adapter 分开调用文本和附件入口；插件不能在两个已经独立的调用之间安全推断一个批次或回收已经发送的文本。实现必须验证实际 handoff 是否提供带顺序的文本/native media 批次；若没有，该交接能力是 Hermes core 的前置契约，不能通过延迟、猜测或额外发送伪造出同一 forward。

### 6. 失败、日志和安全边界保持现有模型

节点构建、嵌套格式化、身份读取和目标检查在第一个消息 Action 前完成。日志只记录 `delivery=forward`、路由、节点计数、阈值和固定错误分类等低敏字段，不输出正文、forward payload、token、昵称原文或媒体引用。forward 失败沿用现有 Action outcome 分类，不报告假成功。

## Risks / Trade-offs

- [Risk] 一个 forward request 会把多个原本独立的文本 chunk 合并进同一个 HTTP body，Milky/LLBot 或客户端可能存在未确认的总 payload 或节点数量限制。→ 每个节点继续遵守现有文本边界；实现和测试必须在首个 Action 前完成结构校验；交付前使用脱敏 fixture 和受控 smoke 验证真实服务端，未确认边界不得宣称支持无限大小。
- [Risk] 合并转发的客户端展示方式不同于连续普通消息，用户可能不展开内容。→ 默认值保持 `0`，由部署者显式开启；README 必须说明这是可展开 forward，而非普通消息序列。
- [Risk] standalone 为 forward 额外读取登录身份会增加一次只读网络请求，且 fallback 可能让转发节点显示为合成用户。→ 仅在阈值触发时执行；失败或不安全身份使用固定 `10001`/`QQ用户`，不阻断合并发送；普通发送和关闭配置不增加请求。
- [Risk] 文本或 native media 中包含本地 URI 时，嵌套 segment 物化比顶层消息更复杂。→ 复用现有 materialization 安全边界并对 nested image/record/video 做完整预检；任何无法安全物化的节点整体失败，不发送原始本地路径或部分消息。
- [Risk] 当前 Hermes 可能把 `MEDIA:` 作为独立 adapter 调用，无法和已提交文本合并。→ 只接受明确的有序文本/native media 批次；若 core 没有该契约，记录为前置阻塞，不发送分离附件来宣称满足同一 forward。
- [Risk] 阈值基于 Unicode 字符长度，而服务端可能按 bytes 或其他规则限制。→ 明确配置语义只控制插件选路；每节点仍沿用当前字符边界，并把服务端更低限制留在受控实机验证范围。

## Migration Plan

1. 发布代码和文档后，未设置 `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 的部署继续使用当前普通出站路径。
2. 需要启用的部署设置 `MILKY_LONG_TEXT_FORWARD_THRESHOLD=300` 等范围内整数并重启，使配置在启动阶段生效。
3. 观察 forward Action 的安全分类、节点计数和实机展示结果；不需要时改回 `0` 或移除配置并重启即可回到普通分块。
4. 不修改已有消息历史、入站 forward 查询或 Hermes core 数据；回滚只需恢复配置为 `0` 或回退插件版本。
