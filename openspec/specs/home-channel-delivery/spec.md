# home-channel-delivery Specification

## Purpose

为 Hermes 的网关生命周期通知、cron 结果和其他受信系统消息提供一个可选且可验证的 Milky 默认投递目的地，同时保持普通入站消息、出站目标命名空间和安全错误边界彼此隔离。

## Requirements

### Requirement: Home channel 使用规范化 Milky chat key

`MILKY_HOME_CHANNEL` MAY 配置一个默认系统消息目标，并 MUST 只接受完整的 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>` chat key。该值属于出站配置，不得要求命中 `MILKY_ALLOWED_CHATS`，也不得被解释为入站授权；未配置时 SHALL 不创建隐式目标。

#### Scenario: 配置群聊 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 为合法的 `group:<id>`
- **THEN** Hermes 的 Milky home channel SHALL 保存该完整 chat key
- **AND** 后续系统/cron 投递 SHALL 路由到该群而不是其他默认目标

#### Scenario: 配置私聊 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 为合法的 `dm:<id>`
- **THEN** Hermes 的 Milky home channel SHALL 保存该完整 chat key
- **AND** 系统 SHALL 使用私聊 Action，不得把它当成群目标

#### Scenario: home channel 目标非法

- **WHEN** `MILKY_HOME_CHANNEL` 为空格、负数、非数字、缺少命名空间或包含额外分隔符
- **THEN** 启动配置 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不发起任何系统消息或 cron 的 Milky HTTP 请求

#### Scenario: 未配置 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 未配置
- **THEN** 普通 friend/group 收发语义 SHALL 保持不变
- **AND** `deliver=milky` 或系统通知 SHALL 不回退到默认频道、origin、群聊或私聊

### Requirement: Hermes 系统消息和 cron 结果投递到 home channel

当 Hermes core 已解析出 Milky home channel 时，网关生命周期通知、系统告警、cron 成功/失败结果和其他受 Hermes 控制的非会话消息 MUST 使用该目标投递。该类消息 SHALL 走 Milky 出站边界，但 SHALL NOT 创建入站 canonical、普通 Hermes MessageEvent、Gate/Will 决策或 Agent turn。

#### Scenario: 网关生命周期通知

- **WHEN** Hermes 向已配置的 Milky home channel 发送启动、重启或系统状态通知
- **THEN** 消息 SHALL 发送到配置的 `group:` 或 `dm:` 目标
- **AND** SHALL 不进入 Milky SSE 入站 pipeline

#### Scenario: cron 使用 Milky home channel

- **WHEN** cron job 使用 `deliver=milky` 且未指定具体 chat target
- **THEN** scheduler SHALL 将 `MILKY_HOME_CHANNEL` 解析为发送目标
- **AND** SHALL 复用同一 Milky 出站格式化、分块和 SendResult 语义

#### Scenario: cron 已指定具体目标

- **WHEN** cron job 使用显式的 `milky:group:<id>` 或 `milky:dm:<id>` 目标
- **THEN** 显式目标 SHALL 优先于 home channel
- **AND** 系统 SHALL 不把消息改投到 home channel

#### Scenario: 无 home channel 的 cron 投递

- **WHEN** `deliver=milky` 没有显式目标且未配置 `MILKY_HOME_CHANNEL`
- **THEN** 投递 SHALL 返回可分类的无目标失败
- **AND** SHALL 不猜测目标或访问 Milky 网络

### Requirement: live 和 standalone cron 投递保持同一出站边界

Milky MUST 同时支持网关内已连接 adapter 的 home channel 投递和独立 cron 进程的 standalone 投递。两条路径 MUST 共享目标校验、文本/结构化内容格式化、文件上传边界、远端 `message_seq` 结果和 `rejected`、`transport_unknown`、`malformed`、`unsupported` 错误语义。

#### Scenario: live adapter 投递

- **WHEN** 网关进程内存在已连接的 Milky adapter 且系统消息解析到 home channel
- **THEN** 系统 SHALL 通过该 adapter 的统一出站 sender 完成投递
- **AND** SHALL 不创建额外的连接、Action catalog 或 Agent 队列

#### Scenario: standalone cron 投递

- **WHEN** cron 在没有 live gateway adapter 的独立进程中向 Milky home channel 投递
- **THEN** plugin SHALL 使用运行时注入的 Milky 连接配置建立一次受控的 standalone 投递
- **AND** 完成或失败后 SHALL 释放该次 standalone 所有的 HTTP 资源

#### Scenario: 投递内容超长或包含附件

- **WHEN** home channel 系统消息包含超长文本、结构化媒体或文件附件
- **THEN** SHALL 继续使用既有分块、Milky segment 和独立 file upload 规则
- **AND** SHALL 不把本地文件路径或 file upload 塞入普通消息 segment

### Requirement: Home channel 投递失败必须诚实且安全

home channel 投递 MUST 在目标和内容校验后才访问网络；远端拒绝、响应结构错误或执行结果未知 SHALL 原样保留既有安全分类，不得伪造成功或盲目重试可能产生副作用的请求。日志、错误和结果 MUST 不包含 token、Authorization header、完整媒体 URL、本地路径或未脱敏真实身份。

#### Scenario: home channel 发送成功

- **WHEN** Milky send Action 成功返回 `data.message_seq`
- **THEN** Hermes SHALL 获得该远端序号的稳定字符串消息 ID
- **AND** SHALL 不使用本地时间、随机值或固定假 ID

#### Scenario: home channel 远端拒绝

- **WHEN** Milky 返回 HTTP 200 但 envelope 表示失败
- **THEN** 投递 SHALL 返回 `rejected`
- **AND** SHALL 不把系统消息标记为成功或自动改投其他 chat

#### Scenario: home channel 传输结果未知

- **WHEN** standalone 或 live 投递发生超时、连接错误或其他无法确认执行结果的传输错误
- **THEN** 投递 SHALL 返回 `transport_unknown`
- **AND** 默认 SHALL 不自动重复发送同一系统消息
