## MODIFIED Requirements

### Requirement: 日志消息遵循 Hermes-agent 的平台风格和级别语义

Milky 运行时日志 MUST 使用标准 logger，并通过 `hermes_plugins.milky.*` 命名空间传播到 Hermes
宿主。关键日志消息 SHALL 使用可检索的 `event=milky.*` 标签和固定的低敏 `key=value` 字段；
该标签和字段是运维诊断词汇，不是插件安全 API 或 Tool 数据 schema。生命周期终态、外部
Action/Tool/出站结果和关键入站结果 SHALL 使用 `info` 或 `warning`，不可恢复的插件本地
边界错误 SHALL 使用 `error`，高频细节 SHALL 使用 `debug`。插件 SHALL 不创建私有 handler、
文件、脱敏器、异步队列或 fallback 日志后端。

#### Scenario: 生命周期成功日志

- **WHEN** Milky 完成初始同步并开放普通消息入口
- **THEN** 日志 SHALL 以 `event=milky.lifecycle` 或其稳定子事件标签记录 ready 状态
- **AND** 日志 SHALL 至少保留安全的阶段、结果和必要关联字段，并不得包含 token、Authorization 或完整 URL

#### Scenario: 可恢复 Action 失败

- **WHEN** 一个 HTTP Action 被拒绝、超时或返回可安全分类的协议错误
- **THEN** 日志 SHALL 使用 `warning` 和固定错误分类
- **AND** 日志 SHALL 尽可能包含 Action 名称、HTTP 状态码、传输阶段和 `duration_ms`
- **AND** SHALL 不直接输出底层异常文本或响应正文

#### Scenario: 高频细节

- **WHEN** 普通帧、策略数值、常规丢弃或逐项资源细节只对调试有价值
- **THEN** 日志 SHALL 使用 `debug` 或省略该诊断
- **AND** SHALL 不因等待日志 handler 完成而阻塞事件接收或 Hermes 提交

### Requirement: 关键阶段和终态使用稳定事件名可检索

适配器 MUST 在关键状态转移处提供固定的低基数 `event=milky.*` 标签或等价的可检索消息，
覆盖 lifecycle、Action、SSE、inbound、Gate、Will、buffer、resource、Hermes handoff、
outbound、mute 和 Tool 状态。事件标签至少 SHALL 覆盖 `milky.lifecycle`、`milky.action`、
`milky.sse`、`milky.inbound`、`milky.resource`、`milky.outbound`、`milky.mute` 和
`milky.tool`；同一状态不得由多个层重复伪造为不同终态。Action、Tool 和出站完成事件
SHALL 提供操作名、结果分类、已知的 HTTP 状态码和 `duration_ms`。

#### Scenario: 消息从 wait 到 trigger

- **WHEN** 一条消息通过 canonical、dedup、Gate 和 Will，并先 wait 后由另一条消息 trigger
- **THEN** 日志 SHALL 能区分 wait、trigger、历史 drain、resource/handoff 成功或失败
- **AND** SHALL 能使用 scene、chat、ingress sequence 或计数关联同一处理链
- **AND** SHALL 不把 wait 消息记录为 Hermes Agent turn

#### Scenario: Gate 或 dedup 短路

- **WHEN** 消息被识别为重复、temp、非法或被某个 Gate 拒绝
- **THEN** 日志 SHALL 记录安全的终止阶段和固定 reason，routine 高频情况可使用 DEBUG
- **AND** SHALL 不记录资源调用、Will 评分或 Hermes handoff 已发生

#### Scenario: Hermes handoff 失败

- **WHEN** resource resolver、mapper 或 `handle_message()` 提交失败
- **THEN** 日志 SHALL 记录 `event=milky.inbound`、handoff 阶段和安全错误分类
- **AND** SHALL 与已在 trigger 决策阶段记录的 reply cost 保持边界分离

### Requirement: 人类消息和结构化字段必须由单一来源渲染

每条运维日志 SHALL 使用一条普通消息表达一个事件标签和必要的低敏 `key=value` 字段；插件
不得依赖额外的结构化投影、同义字段重复渲染或第二个平台前缀。动态字段仅限固定枚举、
非负数、计数、状态码、耗时、规范化异常类型名和必要的业务关联 ID。日志消息不得包含原始
异常、URL、路径、正文、请求/响应 body、媒体引用或 Tool 原始值。

#### Scenario: Mute 扫描汇总不重复

- **WHEN** MuteTracker 完成一次包含 scope、total、succeeded、failed、muted、unmuted 和 unknown 的扫描
- **THEN** 日志 SHALL 使用一个 `event=milky.mute` 事件并使每个统计字段最多出现一次
- **AND** SHALL 不同时输出预格式化统计文本和同一字段的第二份投影

#### Scenario: 动态身份不能绕过字段约束

- **WHEN** 日志调用尝试把未确认的动态字段、错误文本或第二个前缀放入消息
- **THEN** 调用方 SHALL 删除该值或改用固定分类，不得把原值交给 logger
- **AND** 已确认的 chat key、message ID、群 ID或关联序号 MAY 原样用于诊断
- **AND** 凭证、路径、URL 和正文 SHALL 不得通过普通日志字段输出

#### Scenario: 冷启动细节使用规范字段

- **WHEN** 冷启动日志需要记录身份或群禁言扫描状态
- **THEN** 日志 SHALL 只记录必要的 ID、状态和汇总计数，不得把昵称作为常规运维字段
- **AND** 同一 ID 或状态 SHALL 不得同时以别名字段和消息字段重复输出

### Requirement: 状态转移事件必须准确归属且终态不重复

每条运行时日志 MUST 属于唯一的状态边界和事件标签。底层 Action 结果与上层出站或 Hermes
handoff 结果可以同时记录，但 SHALL 明确表示不同边界；已接收 SSE 帧的 handler 失败、fatal
error report 失败和组件关闭失败 SHALL 使用各自事件，不得复用其他阶段的终态事件。资源
完成日志可以附带一次降级告警，但不得生成互相矛盾的完成结果。

#### Scenario: SSE handler 失败

- **WHEN** 合法 SSE 帧已经被接收但其 handler 抛出异常
- **THEN** 日志 SHALL 使用 `event=milky.sse`、handler 失败分类和必要关联字段
- **AND** SHALL 不把该帧记录为 frame ignored
- **AND** 后续帧 SHALL 继续接收

#### Scenario: fatal error report 失败

- **WHEN** adapter 已记录连接或初始同步失败，但向 Hermes 报告 fatal error 的本地调用再次失败
- **THEN** 日志 SHALL 使用独立的 `event=milky.lifecycle` fatal-report 分类
- **AND** SHALL 不伪造第二条 connect failure 或 component close 终态

#### Scenario: 日志调用点全量审计

- **WHEN** 对所有运行时 Python 模块和 smoke CLI 输出进行日志审计
- **THEN** runtime logger 调用 SHALL 全部属于已定义的事件类别或明确省略
- **AND** SHALL 不使用插件私有日志 handler、未知自由文本异常或敏感输入
- **AND** smoke CLI 的机器可读 stdout SHALL 保持独立且不得包含凭证或敏感内容

### Requirement: Action、资源和出站结果在拥有边界处可观察

HTTP Action 的成功、协议拒绝、传输未知、malformed 和 unsupported 结果 MUST 在 Action 或其
直接编排边界被记录；每条 Action 完成日志 SHALL 包含 Action 名称、结果分类、已知的 HTTP
状态码、传输阶段和 `duration_ms`。资源补全 MUST 记录完成数量和降级分类；出站文本、媒体
和文件上传 MUST 记录路由、分块/附件计数和最终结果。日志 SHALL NOT 记录 Action body、媒体
URL、本地文件路径、文件名、文件内容或远端完整响应。

#### Scenario: Action 成功

- **WHEN** Milky Action 返回成功 envelope，发送 Action 还提供稳定 `message_seq`
- **THEN** 日志 SHALL 记录 Action 名称、成功分类、已知 HTTP 状态码和耗时
- **AND** SHALL 不把完整请求 URL、Bearer header 或请求 body 写入日志

#### Scenario: 资源部分失败

- **WHEN** trigger 阶段部分媒体、文件、reply 或 forward 补全失败
- **THEN** 日志 SHALL 记录 `event=milky.resource`、资源种类计数和 `unsupported`、`malformed` 或 `transport_unknown` 等分类
- **AND** SHALL 保留既有正文占位和 Hermes handoff 降级语义

#### Scenario: 出站文件上传

- **WHEN** 出站目标触发独立文件上传
- **THEN** 日志 SHALL 区分 upload 成功/失败、group/dm 路由、附件计数、分类和耗时
- **AND** SHALL 不记录本地路径、文件名、file URI、token、完整 file ID 或文件内容

### Requirement: 日志字段和异常内容必须保持边界约束

所有 Milky 日志 SHALL 只使用低敏字段，例如 `event`、`stage`、`scene`、`action`、`tool`、
`reason`、`classification`、`decision`、`attempt`、`delay_seconds`、`status_code`、
`duration_ms`、计数、`ingress_sequence`、`chat_key` 和必要的 message/group/user ID。普通日志
MUST NOT 包含 token、Authorization header、敏感正文、关键词、segment raw、完整 URL、媒体
URL、文件名、本地路径、文件内容、完整异常文本、异常参数、traceback 或响应正文。Tool
日志不得复制入参或成功/失败结果。

#### Scenario: 含凭证的传输错误

- **WHEN** fake transport 的异常或响应包含 token、Authorization、完整 URL 或服务端正文
- **THEN** 日志 SHALL 只保留安全分类、异常类型名和数值型状态/耗时字段
- **AND** 日志消息 SHALL 不包含这些输入或 traceback

#### Scenario: 含消息内容的入站失败

- **WHEN** canonical、Will、资源补全或 Hermes handoff 失败且消息包含敏感正文和媒体引用
- **THEN** 日志 SHALL 只保留 chat、稳定关联字段、阶段和错误分类
- **AND** SHALL 不输出正文、关键词、媒体 URL、路径或 raw segment

#### Scenario: Tool 返回敏感结果

- **WHEN** Tool 返回下载 URL、媒体 URL、自由文本或未知扩展字段
- **THEN** Tool 调用方 SHALL 继续收到既有 raw envelope
- **AND** 日志 SHALL 只记录 Tool 名称、分类、状态码和耗时，不复制结果内容

#### Scenario: 失败日志需要 traceback

- **WHEN** 本地未处理异常确实需要额外诊断信息
- **THEN** 系统 SHALL 只记录固定分类、规范化 `error_type`、状态码、耗时或关联字段
- **AND** SHALL 不使用 traceback，不记录异常正文、异常参数、远端 payload、凭证或路径
- **AND** 远端 Action、SSE、资源和出站异常 SHALL 先转换为安全分类后记录

### Requirement: 日志不得改变处理顺序并应限制高频噪声

日志调用 MUST 不持有跨阶段业务锁、不等待网络或 Agent、不改变重试/扣费/发送结果。关键
Action/Tool/出站完成结果 SHALL 可在 INFO/WARNING 下检索；未知事件、坏帧、重复 Gate 拒绝和
普通成功细节 SHALL 使用 DEBUG、省略或采用已有有界汇总，避免无界日志增长。日志不可用时
业务处理 SHALL 继续遵循原有 fail-closed 或降级规则。

#### Scenario: 日志 handler 缓慢

- **WHEN** 宿主日志 handler 比消息接收或 detached handoff 更慢
- **THEN** receive loop、admission 和 Hermes `handle_message()` SHALL 不等待日志完成
- **AND** 事件顺序、buffer、Will 状态和 reply cost SHALL 不改变

#### Scenario: 未知事件突发

- **WHEN** 短时间内收到大量未知事件或 malformed 帧
- **THEN** 系统 SHALL 使用固定安全分类在 DEBUG 下记录或进行有界汇总
- **AND** SHALL 不输出每个 raw event、正文或完整 payload
