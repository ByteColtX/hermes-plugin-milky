## Context

See `proposal.md` for the motivation. 当前 Milky 入站流水线已经完成 canonical、TTL dedup、
per-chat admission、Gate、Will 和 Hermes mapper，但 mapper 将普通消息统一包装为紧凑
sender header，并固定关闭 `allow_gateway_control`。这对普通消息是安全默认值，却使 Hermes
无法从 Milky 消息识别 `/status` 等内置命令。

已检查的 Hermes 宿主边界提供 `MessageEvent.is_command()`、`get_command()`、
`get_command_args()`、内置 `COMMAND_REGISTRY`、`ctx.register_command()` 和插件命令分发。
宿主插件命令 handler 的公开签名只有 `fn(raw_args: str)`，不携带 source/profile；因此不能
从 handler 参数安全选择多个活动 Milky adapter。已确认的 Milky `get_impl_info` 成功响应
为 JSON envelope，`data` 包含 `impl_name`、`impl_version`、`milky_version`、
`qq_protocol_type` 和 `qq_protocol_version`。

本 change 只生成规划文档。当前运行时代码尚未实现以下斜杠命令能力，不能把本设计写成已
交付功能。

## Goals / Non-Goals

**Goals:**

- 在既有身份、去重和 Gate 之后建立命令分支，并在 Will 之前结束命令消息的普通消息路径。
- 让 Hermes 继续拥有内置命令、插件命令、busy/follow-up、权限和 unknown-command 语义。
- 通过一次显式插件命令注册提供 `/milky`，成功时直接交付 `get_impl_info` 的完整原始 JSON。
- 将命令 handler 绑定到 adapter 生命周期创建的 Milky client，确保注册阶段无网络和停止后 fail-closed。
- 用脱敏 event/Action fixture、fake Hermes 和 fake transport 验证命令识别、分发、原始 JSON
  保留、错误分类和普通消息回归。

**Non-Goals:**

- 不修改 Hermes core 的内置命令表、命令 dispatcher、busy guard 或插件 registry；如宿主未能
  让插件命令在忙碌会话中即时旁路，Milky 不复制该能力。
- 不把所有 Milky Action 暴露为命令、ToolSpec、动态 Action catalog 或用户可调用的任意 RPC。
- 不把斜杠命令写入 Will wait buffer、Hermes transcript 或普通 Agent prompt，也不为命令另建
  插件侧 Agent/command 执行队列。
- 不处理 temp、recall、request、notice、lifecycle 或未知事件为命令；这些仍是 observe-only
  或协议边界的既有行为。
- 不在失败场景把服务端错误 JSON 原样转发给用户；“原始 JSON”仅指成功的 `get_impl_info`
  响应正文，失败仍遵守错误和秘密脱敏契约。

## Decisions

### 1. 命令分支放在 canonical/dedup/Gate 之后、Will 之前

命令必须先经过 Milky 的身份命名空间、重复帧保护和 Self/allowlist/mute 门禁。这样命令
不会成为绕过聊天授权的旁路，同时重复事件不会重复执行本地 handler 或远端 Action。通过
Gate 后，仅对“纯文本命令正文”进入命令分支：正文去除允许的前导空白后以 `/` 开始，且
消息不携带媒体、reply、forward、未知 segment 或其他结构化内容。混合消息回到普通消息
语义，避免将 `/` 文本中的非命令内容误当控制指令。

替代方案是在 Will 后识别命令，会让 `/milky` 进入 wait buffer 或受到概率策略影响；在
Gate 前识别则会把命令变成授权旁路，均不采用。

### 2. 命令使用专用 MessageEvent 映射，不复用普通正文渲染

普通 Milky 消息继续使用现有紧凑 header、channel context 和 `allow_gateway_control=False`。
命令消息使用原始命令正文（包括命令名和参数），设置宿主可识别的 command message type
和 `allow_gateway_control=True`，source 仍携带 `milky`、`dm:`/`group:`、发送者和消息 ID。
命令不构造历史 context，也不 drain 已有 wait buffer；命令不会因此消耗或改变 Will 状态。

该分支只负责把输入交给 Hermes。内置命令是否 bypass 活动 Agent、是否 interrupt，以及
插件命令在 busy 时如何排队，全部由宿主现有 dispatcher 决定。Milky 不直接调用宿主内部
的 `_handle_*` 方法，也不复制 `CommandDef` 或 `COMMAND_REGISTRY`。

### 3. `/milky` 作为显式插件命令注册

根 `register(ctx)` 使用 `ctx.register_command("milky", ...)` 登记一个无参数命令。handler
本身只接收 raw args，因此不能从调用参数得知 source。实现采用一个 plugin-local
`SlashCommandService`：注册阶段创建 service 并把 handler 闭包交给 Hermes；adapter factory
把同一个 service 注入每个 Milky adapter；connect 成功后绑定其已组装的 client，disconnect
或连接失败时解除绑定。

首版 service 只接受一个明确活动的 Milky client。没有活动 client 或同时存在多个 client
时返回 `unsupported`，不临时创建 client、不使用不同 profile 的凭证，也不猜测调用来源。
这是由已确认宿主 handler 签名推导出的安全边界；若未来 Hermes 提供 source/profile-aware
命令 handler，可以在独立 change 中替换此选择机制。

替代方案是在 handler 内每次读取环境并新建 `MilkyClient`，会绕过 adapter 的生命周期、
连接状态和关闭边界；使用模块全局“最后连接 client”则会在多 profile 下串错凭证，均不采用。

### 4. 对 `get_impl_info` 做成功校验但保留原始响应正文

Milky client 增加一个专用的 `get_impl_info` 原始响应 seam。它复用统一 HTTP Action 的 URL、
POST、Bearer、timeout、响应释放和 envelope 校验；请求参数固定为空对象。响应先在内存中
解析，用于确认 `status=ok`、`retcode=0`、`data` 为对象且包含五个已确认的字符串字段，
然后将成功响应的原始 UTF-8 JSON 文本交给命令 handler 返回。未知顶层或 `data` 扩展字段不
参与业务解释，但保留在返回 JSON 中。

成功回复不增加 Markdown code fence、中文说明或字段摘要，避免改变用户要求的“直接返回原始
JSON”。网络、HTTP、envelope、字段和传输失败仍转换成固定安全分类；不把原始失败 body、
token、Authorization 或底层异常放入回复和日志。

替代方案是将响应解码为 `LoginInfo` 一类 DTO 后重新组装 JSON，会丢失未知字段且不能称为
原始响应；直接不校验 envelope 又会把 HTTP 200 的 rejected 响应伪装成功，均不采用。

### 5. 插件命令不扩大 Action catalog 或普通消息授权

`/milky` 是一个固定、显式、只读的命令 wrapper，不接受 Action 名称、JSON 参数或目标参数。
消息正文、mention、Will 分数和命令参数都不是额外授权来源。名称冲突由 Hermes 的
`ctx.register_command()` 处理，Milky 不覆盖同名内置命令，也不将 `/milky` 写进
`plugin.yaml` 的 `provides_tools`。

## Risks / Trade-offs

- **[宿主插件命令 handler 没有 source/profile]** -> 首版仅允许唯一活动 Milky client；多 client
  时返回 `unsupported`，并用测试固定 fail-closed，未来再由独立宿主扩展解决路由。
- **[当前 mapper 的普通消息结构不适合命令解析]** -> 命令使用独立映射分支；普通消息的
  header、channel context、媒体和 Gate/Will 行为保持回归测试覆盖。
- **[原始 JSON 可包含较长扩展字段]** -> 只对已确认的 `get_impl_info` 成功响应做原样交付，
  不记录日志或持久化；复用宿主普通响应发送的长度处理，超出平台限制时按既有发送错误返回，
  不把 JSON 改写成摘要或盲目重试未知副作用。
- **[插件命令的 busy 行为受宿主版本差异影响]** -> 不在插件复制 busy queue；集成测试分别
  验证空闲命令路径和宿主 busy 行为，未确认的即时执行能力保持 runtime-unknown/unsupported。
- **[HTTP 成功但 data 字段缺失]** -> 在命令回复前按 `malformed` 失败；fixture 覆盖缺字段、
  非 JSON、rejected 和 transport_unknown，避免 HTTP 200 被当作协议成功。

## Migration Plan

1. 先建立 synthetic command event、`get_impl_info` raw response、错误 envelope 和注册捕获
   fixture，确认不包含真实凭证、身份、路径或响应快照。
2. 实现命令分类和专用 Hermes mapper 分支，先验证 Gate/dedup/Will 顺序、内置 command
   parsing 以及普通消息无回归。
3. 实现 raw `get_impl_info` Action seam、`SlashCommandService` 注册与 connect/disconnect
   binding，再覆盖 `/milky` 的成功、参数错误、未连接、多 client 和各类失败。
4. 使用 fake Hermes/fake Milky transport 运行端到端测试，随后执行 pytest、ruff、format、
   build、diff 和 OpenSpec strict validation；必要时只做不写入真实环境的只读协议 smoke。
5. 更新 `ARCHITECTURE.md`、`README.md` 和能力矩阵后再将 change 交给 apply；回滚时移除
   command 分支和 `/milky` binding，不改变既有三项 Agent ToolSpec 与普通消息路径。

## Open Questions

无。多活动 adapter 的 source-aware 命令路由已明确作为当前首版的 `unsupported` 边界，
不会阻止本 change 的单 client 实现。
