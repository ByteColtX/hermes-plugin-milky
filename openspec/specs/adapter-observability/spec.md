# adapter-observability Specification

## Purpose

为 Milky 适配器提供与 Hermes-agent 一致、可检索且不泄露敏感信息的跨模块运行时日志，
使消息处理和外部 Action 的关键状态转移可以被安全地关联与诊断。

## Requirements

### Requirement: 日志消息遵循 Hermes-agent 的平台风格和级别语义

Milky 运行时日志 MUST 使用标准模块 logger，并以 `[Milky] ` 开头的短、人类可读消息呈现；
需要实例化 tag 时 SHALL 使用 Hermes-agent 风格的 `[%s]` 参数化前缀。正常状态和成功结果
SHALL 使用 `info`，可恢复失败、协议拒绝和安全降级 SHALL 使用 `warning`，不可恢复的
本地边界错误 SHALL 使用 `error`，高频细节 SHALL 使用 `debug`。日志 SHALL 继续由 Hermes
宿主的日志 handler 和级别配置接收，不得创建插件私有日志后端或环境变量。

#### Scenario: 生命周期成功日志

- **WHEN** Milky 完成初始同步并开放普通消息入口
- **THEN** 日志 SHALL 以 `[Milky] ` 开头并以 `info` 记录 ready 状态
- **AND** 日志 SHALL 不包含 token、Authorization、完整 URL 或未脱敏身份

#### Scenario: 可恢复 Action 失败

- **WHEN** 一个 HTTP Action 被拒绝、超时或返回可安全分类的协议错误
- **THEN** 日志 SHALL 使用 `warning` 和固定错误分类
- **AND** SHALL 不直接输出底层异常文本或响应正文

#### Scenario: 高频细节

- **WHEN** 普通帧、策略数值或诊断细节只对调试有价值
- **THEN** 日志 SHALL 使用 `debug` 或保留在有界内存诊断中
- **AND** SHALL 不因等待日志调用而阻塞事件接收或 Hermes 提交

### Requirement: 关键阶段和终态使用稳定事件名可检索

适配器 MUST 在关键状态转移处提供固定的 `event_name` 结构化字段或等价的可检索标签，
并在不改变业务顺序的前提下覆盖 lifecycle、Action、inbound、Gate、Will、buffer、resource、
Hermes handoff、outbound 和 mute 状态。固定事件名至少 SHALL 包括：
`milky_adapter_ready`、`milky_adapter_connect_failed`、`milky_inbound_observe_only`、
`milky_inbound_duplicate`、`milky_inbound_gate_denied`、`milky_inbound_wait`、
`milky_inbound_trigger`、`milky_inbound_handoff_succeeded`、
`milky_inbound_handoff_failed`、`milky_action_succeeded`、`milky_action_failed`、
`milky_resource_resolution_completed`、`milky_resource_resolution_degraded`、
`milky_outbound_succeeded`、`milky_outbound_failed`、`milky_mute_refresh_succeeded` 和
`milky_mute_refresh_failed`；需要区分实际边界时还 SHALL 使用
`milky_adapter_fatal_error_report_failed`、`milky_event_stream_handler_failed` 和
`milky_inbound_observer_failed`。同一状态不得由多个层重复伪造为不同终态。

#### Scenario: 消息从 wait 到 trigger

- **WHEN** 一条消息通过 canonical、dedup、Gate 和 Will，并先 wait 后由另一条消息 trigger
- **THEN** 日志 SHALL 能区分 wait、trigger、历史 drain、resource/handoff 成功或失败
- **AND** SHALL 能使用 scene、脱敏 chat、ingress sequence 或计数关联同一处理链
- **AND** SHALL 不把 wait 消息记录为 Hermes Agent turn

#### Scenario: Gate 或 dedup 短路

- **WHEN** 消息被识别为重复、temp、非法或被某个 Gate 拒绝
- **THEN** 日志 SHALL 记录安全的终止阶段和固定 reason
- **AND** SHALL 不记录资源调用、Will 评分或 Hermes handoff 已发生

#### Scenario: Hermes handoff 失败

- **WHEN** resource resolver、mapper 或 `handle_message()` 提交失败
- **THEN** 日志 SHALL 记录 `milky_inbound_handoff_failed` 和安全错误分类
- **AND** SHALL 不记录已成功提交或 reply cost 已扣除

### Requirement: 人类消息和结构化字段必须由单一来源渲染

日志的人类可读部分 MUST 只使用固定事件标签和统一的 `[Milky] ` 前缀；动态 ID、计数、状态、
nickname、错误分类和关联值 MUST 只通过经过白名单校验和脱敏的结构化字段提供。调用方
不得把动态 `key=value`、原始异常、URL、路径、正文或第二个平台前缀预先拼入消息。每个
结构化字段在同一条人类可读消息中最多 SHALL 出现一次，同时 `LogRecord` 的结构化值 SHALL
与人类消息使用同一份已脱敏结果。

#### Scenario: Mute 扫描汇总不重复

- **WHEN** MuteTracker 完成一次包含 `scope`、`total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 的扫描
- **THEN** 人类可读日志 SHALL 以单个 `[Milky]` 前缀开头，且每个统计字段 SHALL 只出现一次
- **AND** 结构化记录 SHALL 保留同名统计字段及对应的原始数值语义
- **AND** 日志 SHALL 不再同时出现调用方预格式化统计文本和 helper 追加的同一字段

#### Scenario: 动态身份不能绕过字段脱敏

- **WHEN** 日志调用尝试把未脱敏数字 ID、nickname、错误文本或动态字段放入人类可读消息
- **THEN** 系统 SHALL 拒绝该动态消息或只使用安全字段渲染
- **AND** 人类消息和结构化记录 SHALL 均不得包含未脱敏 ID、凭证、路径、URL 或正文

#### Scenario: 冷启动细节使用规范字段

- **WHEN** 冷启动日志需要记录 UID、nickname 或确认禁言群的 member/whole 状态
- **THEN** 日志 SHALL 使用固定标签和各自的安全字段逐项输出
- **AND** 同一 UID、群 ID 或状态 SHALL 不得同时以别名字段和结构化字段重复输出

### Requirement: 状态转移事件必须准确归属且终态不重复

每条运行时日志 MUST 属于唯一的状态边界和固定 event name。底层 Action 结果与上层出站或
Hermes handoff 结果可以同时记录，但它们 SHALL 明确表示不同边界；已接收 SSE 帧的 handler
失败、fatal error report 失败和组件关闭失败 SHALL 使用各自事件，不得复用表示其他阶段的
终态事件。资源完成日志可以附带一次降级告警，但不得生成第二个互相矛盾的完成结果。

#### Scenario: SSE handler 失败

- **WHEN** 合法 SSE 帧已经被接收但其 handler 抛出异常
- **THEN** 日志 SHALL 使用 `milky_event_stream_handler_failed`
- **AND** SHALL 不把该帧记录为 `milky_event_stream_frame_ignored`
- **AND** 后续帧 SHALL 继续接收

#### Scenario: fatal error report 失败

- **WHEN** adapter 已记录连接或初始同步失败，但向 Hermes 报告 fatal error 的本地调用再次失败
- **THEN** 日志 SHALL 使用 `milky_adapter_fatal_error_report_failed`
- **AND** SHALL 不伪造第二条 `milky_adapter_connect_failed` 或 component close 终态

#### Scenario: 日志调用点全量审计

- **WHEN** 对所有运行时 Python 模块和 smoke CLI 输出进行日志审计
- **THEN** runtime logger 调用 SHALL 全部出现在固定事件和调用点清单中
- **AND** 直接的非结构化 logger 输出 SHALL 被拒绝
- **AND** smoke CLI 的机器可读 stdout SHALL 保持独立且不得包含凭证或敏感内容

### Requirement: Action、资源和出站结果在拥有边界处可观察

HTTP Action 的成功、协议拒绝、传输未知、malformed 和 unsupported 结果 MUST 在 Action 或
其直接编排边界被安全记录；资源补全 MUST 记录完成数量和降级分类；出站文本、媒体和文件
上传 MUST 记录路由、分块/附件计数和最终安全结果。日志 SHALL NOT 记录 Action body、媒体
URL、本地文件路径、文件名或远端完整响应。

#### Scenario: Action 成功

- **WHEN** Milky Action 返回成功 envelope，发送 Action 还提供稳定 `message_seq`
- **THEN** 日志 SHALL 记录 Action 名称、成功结果、必要的 scene 或计数
- **AND** SHALL 不把完整请求 URL、Bearer header 或请求 body 写入日志

#### Scenario: 资源部分失败

- **WHEN** trigger 阶段部分媒体、文件、reply 或 forward 补全失败
- **THEN** 日志 SHALL 记录 `resource` 阶段、资源种类计数和 `unsupported`、`malformed` 或
  `transport_unknown` 等安全分类
- **AND** SHALL 保留既有正文占位和 Hermes handoff 降级语义

#### Scenario: 出站文件上传

- **WHEN** 出站目标触发独立文件上传
- **THEN** 日志 SHALL 区分 upload 成功/失败和 group/dm 路由
- **AND** SHALL 不记录本地路径、文件名、file URI、token 或完整 file ID

### Requirement: 日志字段和异常内容必须保持脱敏

所有 Milky 日志及其结构化字段 MUST 只使用白名单字段，例如 `stage`、`event_name`、
`scene`、`action`、`reason`、`classification`、`decision`、`attempt`、`delay_seconds`、
`status_code`、`duration_ms`、计数和 `ingress_sequence`。QQ/群 ID SHALL 统一保留前后三位并
隐藏中间部分；chat key SHALL 保持 `group:`/`dm:` 命名空间但使用脱敏 ID。日志 MUST NOT
包含 token、Authorization header、个人 QQ/群 ID 原文、敏感正文、关键词、segment raw、
媒体 URL、文件名、本地路径、完整异常文本或响应正文。

#### Scenario: 含凭证的传输错误

- **WHEN** fake transport 的异常或响应包含 token、Authorization、完整 URL 或服务端正文
- **THEN** 日志 SHALL 只保留安全分类和数值型状态字段
- **AND** `LogRecord` 消息与结构化字段 SHALL 均不包含这些输入

#### Scenario: 含消息内容的入站失败

- **WHEN** canonical、Will、资源补全或 Hermes handoff 失败且消息包含敏感正文和媒体引用
- **THEN** 日志 SHALL 只保留脱敏 chat、稳定关联字段、阶段和错误分类
- **AND** SHALL 不默认输出正文、关键词、媒体 URL、路径或 raw segment

#### Scenario: 失败日志需要 traceback

- **WHEN** 本地未处理异常确实需要 traceback 才能诊断
- **THEN** 系统 SHALL 只在异常对象和 traceback 已确认不含远端 payload、凭证和路径时使用
  Hermes-agent 风格的 `error`/`exc_info`
- **AND** 远端 Action、SSE、资源和出站异常 SHALL 先转换为安全分类后记录

### Requirement: 日志不得改变处理顺序并应限制高频噪声

日志调用 MUST 不持有跨阶段业务锁、不等待网络或 Agent、不改变重试/扣费/发送结果，并且
未知事件、坏帧、重复 Gate 拒绝和普通成功细节 SHALL 使用 debug、限速或聚合方式避免无界
日志增长。日志不可用时业务处理 SHALL 继续遵循原有 fail-closed 或降级规则。

#### Scenario: 日志 handler 缓慢

- **WHEN** 宿主日志 handler 比消息接收或 detached handoff 更慢
- **THEN** receive loop、admission 和 Hermes `handle_message()` SHALL 不等待日志完成
- **AND** 事件顺序、buffer、Will 状态和 reply cost SHALL 不改变

#### Scenario: 未知事件突发

- **WHEN** 短时间内收到大量未知事件或 malformed 帧
- **THEN** 系统 SHALL 使用安全分类进行限速/聚合记录
- **AND** SHALL 不输出每个 raw event、正文或完整 payload
