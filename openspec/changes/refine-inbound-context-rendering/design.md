## Context

当前入站规范化已经能识别 Milky v1.3.0 的 14 类 incoming segment，并把普通消息历史保存到
按 chat 隔离的 wait buffer。现有 renderer 输出多行方括号记录，`light_app` 只拥有固定 DTO
字段视图，系统事件也没有可供下一次 Agent turn 使用的短期上下文入口。详见
`proposal.md` 的 Why；行为边界以本 change 的四份 delta spec 为准。

## Goals / Non-Goals

**Goals:**

- 让普通消息在 `channel_context` 和当前 `MessageEvent.text` 中使用一致的单行尖括号格式。
- 让每个已支持的结构化 segment 产生稳定且可解释的正文占位，并让未知 segment 保持 raw-only。
- 让 `light_app` 以 `{"meta": ...}` 为展示根，递归保留 `meta` 的实际结构，不预设字段集合。
- 让 nudge 和群成员进出事件以 context-only 记录提供给下一次同 chat trigger。
- 保持普通消息的 canonical、dedup、Gate、Will、wait 和 Hermes 提交顺序不变。
- 让 forward 只提供引用 ID，不因普通 trigger 自动产生额外远端查询。

**Non-Goals:**

- 不增加 Milky v1.3.0 未确认的 `rps`、`share`、`contact` 或其他 incoming segment 类型；contact
  只作为 `light_app` payload 的一种业务内容处理。
- 不把 poke、群成员变更或其他系统事件转换为普通 `message_receive`、Hermes turn 或 Will 输入。
- 不解析 XML 语义，不执行 light app，不展开未知 segment，也不自动查看 forward 内容。
- 不改变 Milky OpenAPI、SSE 传输、Gate 授权、Hermes Agent busy/follow-up 语义或出站能力。

## Decisions

### 1. 将渲染格式作为领域输出，而不是修改 canonical 身份

canonical 继续保存 typed segments、引用和规范化正文；格式变化集中在 context/message
renderer，使 dedup、Will 和资源 resolver 不依赖展示字符串。普通记录按
`<sender uid id msg_id id reply_to id> body` 拼成单行，当前消息继续只进入正文，历史只进入
`channel_context`。

备选方案是把新格式直接写入 canonical body。该方案会把 Agent 展示约定污染策略文本和资源
占位逻辑，因此不采用。

### 2. 为系统事件增加独立的短期 context buffer

系统事件不具备普通消息的完整 sender/message identity，不能复用普通 canonical 或 wait
buffer。每个 chat 维护一个独立的有界队列；事件到达时分配与事件流共享的 ingress sequence，
trigger 时在同一短暂 admission 保护下取出，并与普通 wait 历史按序合并。取出后不再回填；
没有可确认 chat key 的事件只观察。

备选方案是把事件转成伪造的 canonical message，或直接追加到全局上下文。前者会破坏
`message_receive` 唯一入口和 dedup 语义，后者会造成 chat 串扰，因此不采用。

### 3. `light_app` 只投影 meta 根对象

解析 `json_payload` 后只选取顶层 `meta` 这一根字段，随后以通用 JSON 值递归序列化其全部
内容。这样 contact card、QQ 小程序及未来 light app 都能保留各自真实的 meta 结构，同时
不会把不属于 meta 的顶层 envelope 字段误当作消息正文。缺少合法 meta 时使用
`[light_app:NOT SUPPORTED]`。

备选方案是维护 app/view/contact 等字段白名单，或展示整个 payload。白名单会随协议扩展
丢失字段，展示整个 payload 会混入不属于 meta 的控制信息，均不符合本 change 的展示契约。

### 4. Forward 采用引用展示与后续显式查询分离

normalizer 保留 `forward_id` 和既有 raw/reference 信息；普通 resolver 不调用
`get_forwarded_messages`，正文仅渲染 `[forward:<forward_id>]`。未来 QQ Tool 如需查看详情，
应在独立工具契约中定义授权、参数校验、查询结果和上下文注入方式。

### 5. 图片占位符以后端实际落盘 basename 为准

normalizer 阶段只能使用临时的 image placeholder，因为 Hermes image helper 尚未执行。trigger
阶段成功调用 helper 后，resolver 读取其返回本地路径的 basename，并按 image segment 顺序替换
对应 placeholder。这样最终交给 Hermes 的正文与 `media_urls` 使用同一个实际文件名；helper 失败或
不可用时保留 `[img:NOT SUPPORTED]`。不修改 Hermes core，也不尝试让 helper 接受原始文件名。

### 6. 系统事件使用事件字段生成固定自然语言

`group_nudge` 仅输出发送者和接收者 UID；成员增加/减少输出稳定动作文本和协议字段 JSON
Details。display action、动作图片 URL 以及未登记扩展字段不进入该事件的 body。事件只进入
下一次同 chat 的 `channel_context`，不改变普通消息的 will 输入和 reply cost。

## Risks / Trade-offs

- [新格式可能被正文中的换行或尖括号破坏记录边界] → 复用现有 header/body 转义规则，并增加
  单行、恶意边界字符和顺序回归测试。
- [light_app.meta 结构未来很大或层级未知] → 不做字段数量假设；使用结构化 JSON 序列化和
  已有上下文边界测试，避免递归解释业务语义。
- [系统事件在下一次 trigger 前积压] → 使用独立有界 FIFO，溢出丢弃最早事件并保留安全诊断。
- [系统事件没有稳定消息 ID] → 不进入普通 dedup；使用事件流 ingress sequence 只保证本进程
  内上下文顺序，不宣称跨重连无损恢复。
- [移除自动 forward 查询会减少当前 turn 的展开内容] → 明确保留 forward ID，并将主动查看
  推迟到后续显式 QQ Tool。

## Migration Plan

1. 先补充脱敏 fixture，覆盖新单行普通消息、所有 placeholder、可变 meta、forward 不查询和
   poke/成员事件字段组合。
2. 实现 renderer、meta 投影和独立 system context buffer，同时保留现有普通 wait buffer。
3. 将事件观察分支接入 context-only 记录，并在 trigger mapper 中一次性合并和清空上下文。
4. 运行入站、资源、事件流、会话和完整质量门禁；失败时按格式、协议、资源、并发或安全分类。
5. 在自动化证据覆盖前，不将本 change 的目标行为同步到主 `openspec/specs/`，避免把规划描述
   成已交付能力。回滚时恢复旧 renderer 并丢弃新增的 context-only 运行时状态即可，不涉及
   Milky 远端状态迁移。

## Open Questions

无。`light_app` 缺失 meta、forward 查询边界、系统事件文本和可选 Details 字段的行为已在
delta spec 中固定。
