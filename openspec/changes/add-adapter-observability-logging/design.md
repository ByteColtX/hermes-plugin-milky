## Context

See `proposal.md` for the motivation. 当前实现已经在 adapter、HTTP client、SSE、inbound、
resource、outbound 和 MuteTracker 使用共享日志 helper，但全量审计发现三类一致性问题：
调用方把动态 `key=value` 预格式化进人类消息后又传入同一结构化字段；自定义消息可以绕过
统一 ID 脱敏；少数错误路径复用了不匹配的 event name。`../hermes-agent` 的日志文件路由、
轮转和 handler 仍由 Hermes 宿主负责，本 change 不接管这些能力。

本设计还必须保持既有 Milky 契约：冷启动日志继续提供脱敏 UID、nickname、确认禁言群的
member/whole 状态和汇总计数；SSE 继续区分连接断开、重连和取消；未知系统事件继续
observe-only；日志不能改变 Gate/Will、Hermes media ownership、SendResult 或生命周期语义。

## Goals / Non-Goals

**Goals:**

- 为所有运行时日志建立可审计的调用点清单、唯一事件归属和一致的字段 schema。
- 让固定人类消息、结构化字段和脱敏策略各自只有一个来源，消除重复、双前缀和动态消息绕过。
- 修正错误事件名、错误分类和日志级别，使日志能准确描述实际状态转移。
- 通过 fake transport、fake Hermes、MuteTracker、SSE 和 caplog 测试验证安全、顺序和非阻塞。

**Non-Goals:**

- 不新增日志后端、日志配置、远程 telemetry、持久化审计或第三方依赖。
- 不记录正文、关键词、raw segment、媒体 URL、文件名、本地路径、Authorization、token 或未脱敏 ID。
- 不把 `scripts/milky_smoke.py` 的机器可读 stdout 当作运行时日志；只验证其输出不含凭证和敏感输入。
- 不改变 Milky 协议、SSE 重连策略、Gate/Will 决策、Hermes session/media ownership 或出站协议。

## Decisions

### 统一日志入口和状态所有权

运行时模块只通过标准模块 logger 和共享安全边界发出日志；源码审计必须确认不存在直接
`logger.*`、`logging.*` 或调试 `print`。smoke 脚本的 `print` 是明确的 CLI 输出例外。

日志所有权按状态转移划分：adapter 负责生命周期，Milky client 负责单次 Action，event
stream 负责连接/帧/handler，inbound 负责消息编排和 Will 调用结果，resource 负责资源
批次，outbound 负责发送操作，MuteTracker 负责禁言状态。Will 和 session 保持纯策略/状态
组件，不另起一套日志；它们的决策和 buffer 交接由 inbound 在边界处记录。

底层 Action 成功/失败与上层发送或 handoff 最终结果可以同时存在，因为它们代表不同边界；
同一边界只允许一个终态事件。资源批次的 `completed` 是总结果，存在降级时额外的
`degraded` 是附加告警，不得再次伪造一个不同的完成终态。MuteTracker 保留“只记录确认
禁言群的逐群明细 + 一条扫描汇总”的既有契约。

### 固定标签和动态字段分离

共享日志边界只使用 event name registry 提供的固定英文标签，并统一生成 `[Milky] ` 前缀。
调用方不得传入包含动态 ID、计数、状态或 nickname 的预格式化消息；若保留内部 message
参数，它只能引用 registry 中的静态标签。helper 不做字符串字段去重，因为去重会依赖
格式、可能误隐藏合法文本，也会掩盖调用方重复传值的问题。

动态值只通过显式白名单字段进入 helper。helper 先完成字段校验和脱敏，再把同一份结果写入
`LogRecord` 的结构化属性；人类消息只保留固定事件标签，不渲染动态字段。这样可以避免宿主
formatter 再次渲染 extra 时产生重复字段，也不存在“消息已脱敏、extra 未脱敏”的分叉。

字段 schema 至少包括 `stage`、`event_name`、`scene`、`action`、`reason`、`classification`、
`decision`、`attempt`、`delay_seconds`、`status_code`、`duration_ms`、计数、
`ingress_sequence`、`chat_key`、`uid`、`self_id`、`sender_id`、`peer_id`、`group_id`、
`user_id`、`message_id`、`reference_id`、`file_id`、`component`、`nickname`、
`member_mute` 和 `whole_mute`。`uid` 只用于既有冷启动身份日志，其他生命周期关联使用
`self_id`；同一条记录不得同时出现两者。数字身份统一保留首尾三位；chat key 保留
`group:`/`dm:` 命名空间；不透明 ID 必须截断且禁止 URL、路径或正文字符。每个枚举字段都
必须有显式允许集合。

### 错误事件和安全异常

事件名必须描述实际边界：fatal error report 失败不能复用 component close 事件；已接受帧的
handler 失败不能复用 frame ignored 事件。新增事件名必须同时加入 registry、对应 spec、
caplog fixture 和调用点清单。

远端 Action、SSE、资源和出站异常先转换为固定 classification/reason；不直接使用异常
字符串、请求参数、响应正文或 URL。组件关闭失败继续采用可恢复的 warning，无法恢复的本地
边界错误使用 error。traceback 只允许用于经过递归异常链、notes 和路径安全检查的本地异常；
如果 traceback 无法证明安全，则只记录不带 traceback 的固定分类。

### 非阻塞和限噪

日志提交不得等待宿主 handler、网络、Agent、admission lock 或状态锁。高频 frame ignored、
重复、普通策略细节使用 debug；生命周期、wait/trigger、重连恢复、最终发送和扫描汇总才
使用 info；可恢复失败和降级使用 warning。

异步日志分发采用有界、best-effort 的后台提交：debug 在容量不足时可丢弃，info/warning/error
不得让业务阻塞；容量耗尽时记录内部受控丢弃计数而不把日志内容写回日志。测试必须证明
慢 handler 不阻塞 receive loop、detached handoff 或后续状态转移，并明确日志丢弃不改变业务结果。

### 验证策略

测试不冻结宿主 formatter 的完整句子，而是断言 event name、level、固定字段、脱敏结果、
消息前缀和事件顺序。测试矩阵包括：所有运行时调用点静态审计；MuteTracker 冷启动真实汇总
路径；动态消息和重复字段拒绝；raw numeric ID、nickname、异常链、路径、URL、token 和
正文扫描；SSE frame/handler 错误区分；Action、resource、outbound、inbound 终态归属；慢
日志 handler 和高频 debug 限噪。

## Risks / Trade-offs

- [固定标签减少了个别旧日志的自然语言细节] -> 将必要细节转为规范化字段，并保留冷启动
  契约要求的 nickname、member/whole 状态和扫描计数。
- [严格禁止动态 message 可能影响旧的文本检索] -> 保留稳定 event name，并为标签和字段
  提供明确的迁移映射；不保留不安全的自由文本兼容层。
- [后台分发在突发 debug 时丢日志] -> 只允许丢弃高频 debug，保留受控丢弃计数，并测试
  info/warning/error 不阻塞业务。
- [异常链检查增加实现复杂度] -> 远端错误默认不带 traceback；只有安全本地边界显式加入
  traceback 测试。
- [新增字段扩大 schema] -> 所有字段采用显式 serializer 和枚举白名单，不接受任意 `extra`。

## Migration Plan

1. 先更新脱敏 fixture、事件 registry、字段 schema 和全量调用点审计清单。
2. 移除 helper 的动态消息去重与自由文本路径，先修 adapter/MuteTracker，再修 SSE、client、
   inbound、resource 和 outbound 的事件命名、字段和级别。
3. 增加真实 MuteTracker 扫描、handler failure、fatal report failure、异常链和静态审计回归，
   再运行定向测试、全量 pytest、ruff、format、build、diff check 和 OpenSpec strict validation。
4. 不执行未经授权的真实 Milky 写入 Action；发布无需配置或数据迁移，回滚只恢复日志调用，
   不转换 Milky 协议和进程内状态。

## Open Questions

无。日志标签、字段 schema、事件所有权和异常安全边界均在本设计中确定；Hermes 宿主继续
负责日志路由和生命周期，不能由实现阶段自行放宽。
