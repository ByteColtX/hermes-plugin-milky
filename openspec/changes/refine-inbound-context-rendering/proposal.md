## Why

当前入站消息的 `channel_context` 仍使用多行方括号 header，segment 也主要使用中文概括占位，导致不同消息段和系统事件的结构信息不够直观。现有 `light_app` 只按固定少量字段理解内容，无法保留 Milky 实际 payload 中 `meta` 的可变结构；forward 还会在 trigger 阶段自动查询，而需求希望先展示引用 ID，交由后续 QQ Tool 按需展开。

## What Changes

- 将普通消息和历史上下文统一渲染为单行尖括号 header：`<sender uid ... msg_id ... reply_to ...> body`。
- 完整 inline reply 只通过 `reply_to` header 表达，不在正文重复添加成功的引用占位符。
- 图片成功经 Hermes image helper 落盘后，正文占位符使用 helper 返回路径的 basename，保证占位文件名与实际落盘文件名一致；资源失败时使用 `NOT SUPPORTED`。
- 按 segment 类型提供稳定、可读的占位符；`market_face` 和 `xml` 使用 `NOT SUPPORTED`，未知 segment 继续不进入正文。
- 解析 `light_app.json_payload` 时忽略顶层业务字段，以 `[light_app:{"meta":...}]` 形式保留完整 `meta` 根对象及其递归内容，不预设 `meta` 下的字段数量或名称。
- 将 contact 视为 `light_app` payload 的内容，不新增独立 `contact` segment 或 placeholder 类型。
- forward 入站只展示 `[forward:<forward_id>]`，trigger 阶段不自动调用 `get_forwarded_messages`；后续由显式 QQ Tool 按需查询。
- 为 `group_nudge` 注入简洁的 context-only 事件文本：`<event group_nudge> uid <sender_id> 戳了 uid <receiver_id>`。
- 为 `group_member_increase` 和 `group_member_decrease` 注入 context-only 事件文本，并保留已确认的 Details 字段。
- 系统事件注入只影响后续 `channel_context`，不创建独立 Agent turn、不经过 Will、不扣 reply cost；其他系统事件继续 observe-only。
- 增加脱敏协议 fixture、上下文渲染和系统事件注入回归，覆盖 `light_app` 的可变 `meta` 形状、forward 不查询和事件字段缺失降级。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-session-buffer`: 修改上下文 header 为单行格式，并允许有界 system context 与普通历史按 ingress 顺序注入下一次 trigger。
- `message-segments`: 修改结构化 segment placeholder，并定义 `light_app` 的完整 `meta` 根对象展示边界。
- `media-and-reply-resolution`: 修改 forward 的 trigger 行为，禁止插件自动查询合并转发详情。
- `system-events-and-safety`: 为 poke 和群成员进出增加 context-only 注入，同时保持系统事件不创建独立 Agent turn。

## Impact

- 影响 `session/buffer.py`、`inbound/extractor.py`、`inbound/normalizer.py`、`inbound/pipeline.py`、`milky/resources.py` 和相关 mapper/fixture/test。
- 需要为 system context 增加与普通 wait buffer 分离且有界的进程内状态，不能把系统事件伪装成 canonical `message_receive`。
- 不改变 Milky OpenAPI、SSE 传输、Gate/Will 顺序、temp 忽略或普通消息的 Hermes 提交边界。
- 不新增 `rps`、`share` 等未在当前 Milky v1.3.0 schema 确认的类型。
