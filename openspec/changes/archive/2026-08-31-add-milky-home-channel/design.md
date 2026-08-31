## Context

See `proposal.md` for the motivation. 当前 Milky plugin 的 `load_config()` 尚未支持
`MILKY_HOME_CHANNEL`，根入口只注册普通 platform adapter，也没有向
Hermes platform registry 声明 cron delivery 或 standalone sender 能力。

Hermes 宿主已经提供与本 change 对应的只读扩展点：`PlatformEntry` 可以声明
`cron_deliver_env_var`，`env_enablement_fn` 可以在 adapter 构造前提供
`PlatformConfig.home_channel`，`standalone_sender_fn` 可以处理与网关分离的 cron 进程。
宿主 cron 会在 `deliver=milky` 且没有显式目标时解析 home channel；网关生命周期通知也
会读取 `PlatformConfig.home_channel`。Milky 自身的出站边界仍要求完整的 `group:`/`dm:`
chat key，并负责 Milky Action、分块、文件上传、稳定 message ID 和错误分类。

## Goals / Non-Goals

**Goals:**

- 让 `MILKY_HOME_CHANNEL` 成为一个可选、启动时验证、只保存规范化 chat key 的配置。
- 通过宿主已有 registry hook 同时接通网关内系统通知、live cron 和独立 cron 投递。
- 让 home channel 消息复用现有 outbound sender 的目标、格式、附件和错误边界，并保持
  remote execution unknown 时不盲目重试。
- 用 fake Hermes/registry/transport 和脱敏 fixture 证明 home channel 不会污染入站
  canonical、Gate、Will、wait buffer 或 Agent turn。
- 在实现完成后同步更新架构和 README 中关于 home channel 与 standalone/cron 能力的状态。

**Non-Goals:**

- 不修改 Hermes core、cron scheduler、`Platform` enum 或宿主的 HomeChannel 数据模型。
- 不让 adapter 在收到空目标时自行选择 home channel；目标选择必须由 Hermes core/cron
  完成，再以完整 chat key 调用 adapter。
- 不新增 `MILKY_HOME_CHANNEL_NAME` 等额外配置。
- 不把 Milky SSE 的 recall/request/notice 等系统事件转发为 home channel 消息，不把
  home channel 变成任意 Action 的授权或 Agent 工具。
- 不创建插件自己的持久化 home store、媒体缓存、下载目录或 retry/dedup 系统。

## Decisions

### 使用一个规范化环境变量作为插件配置

在 `MilkyConfig` 中增加可选的 `home_channel: str | None`。解析时复用现有 chat key
规则，只接受 `group:<十进制群号>` 和 `dm:<十进制 QQ 号>`；空值代表未配置，其他形式在
启动配置阶段拒绝。`MILKY_HOME_CHANNEL` 不加入 `MILKY_ALLOWED_CHATS`，因为它是出站
系统消息目的地而不是入站授权名单；其摘要只暴露 `has_home_channel`，不输出目标 ID。

不引入单独的显示名称环境变量：env enablement 生成稳定的 `Milky Home` 显示名，避免把
展示元数据扩张为另一套配置契约。Hermes core 仍可使用自己的 HomeChannel 持久化能力，
但本 change 的插件配置来源和 manifest 只承诺 `MILKY_HOME_CHANNEL`。

### 用 registry hook 接入宿主，而不是改 Hermes core

根 `register(ctx)` 继续是唯一入口，并在同一个 `ctx.register_platform()` 注册调用中
声明：

1. `cron_deliver_env_var="MILKY_HOME_CHANNEL"`，让宿主识别 `deliver=milky`；
2. 一个无网络的 `env_enablement_fn`，把有效 home target 映射为宿主的
   `PlatformConfig.home_channel`，供状态显示和生命周期通知使用；
3. 一个 `standalone_sender_fn`，供没有 live adapter 的 cron 进程执行单次出站。

这三个 hook 都是宿主已确认的 plugin interface。它们不需要新增 manifest 入口，也不应
在 import/register 阶段连接 Milky、启动 SSE 或创建长期任务。live 发送仍由宿主把
HomeChannel 解析为具体 chat key 后调用 adapter；adapter 不再次读取环境变量，避免
运行中配置漂移和隐式目标回退。

### live 和 standalone 共享同一出站语义

live 路径直接使用已连接 adapter 的 `MilkyOutboundSender`。standalone 路径读取本次
进程的运行时配置，创建一个短生命周期的 Milky client 和 outbound sender，发送完毕后
在 `finally` 中关闭资源。两条路径都先解析目标和内容，再进入 HTTP；发送成功只接受
Milky 返回的 `data.message_seq`，超时或连接错误保持 `transport_unknown`，不调用宿主的
通用 retry 或纯文本 fallback。

standalone sender 的文本、结构化媒体和 file upload 参数沿用宿主标准签名。可安全复用
的类型交给既有 formatter/chunking/file upload；无法获得受 Hermes 约束的附件输入时
返回 `unsupported`，不得直接把本地路径或未经确认的 URL 交给 Milky。系统通知默认是
非会话文本，不附带 reply target，也不等待 Agent 执行。

### 系统来源和入站来源保持两条单向边界

home channel 只接受 Hermes core/cron 已经产生的受信出站消息。Milky SSE 事件仍由现有
`message_receive` 普通 pipeline 和 observe-only 系统事件路径处理；配置 home channel
不会使 recall、request、notice、未知事件产生 Agent turn、出站转发或新的权限。

这一边界也意味着 home channel 不参与 Self/Allowlist/MutedGroup Gate 和 Will。Gate 是
入站 hard gate，outbound sender 仍必须执行自己的目标、内容和协议校验；群发送失败仍
可以按既有规则通知 MuteTracker，但不能把 home channel 配置当作已授权的群状态证明。

### 失败分类与日志最小化

配置错误使用现有安全配置错误；Milky envelope 拒绝、HTTP/连接未知、响应结构损坏和
不支持能力分别沿用既有 `rejected`、`transport_unknown`、`malformed` 和 `unsupported`
分类。系统消息投递失败不自动改投另一个 home、origin 或默认频道。

新增日志只记录稳定的 route/scene、错误分类和必要的消息结果字段；不记录 token、认证
header、完整目标 ID、正文、媒体 URL、本地路径或原始响应。fixture 只使用合成的
namespace 和消息序号，并将 standalone 资源释放、无网络前置拒绝和 live/standalone
目标一致性纳入回归测试。

### Alternatives considered

- **在 Hermes core 中硬编码 Milky**：拒绝。宿主已提供插件 registry hook，core 不应因单个
  directory plugin 增加平台专用分支。
- **让 adapter.send("") 自动读取 home channel**：拒绝。这样会把目标选择隐藏在出站层，
  可能把普通空目标、错误目标或临时目标误投递，并破坏“网络访问前失败”的边界。
- **只注册 `cron_deliver_env_var`，不实现 standalone sender**：拒绝。只能覆盖与网关同进程
  的 cron，独立 cron 会得到缺少 live adapter 的失败，不能满足 cron 投递目标。
- **通过 SSE 伪造系统消息事件**：拒绝。Action、SSE 和 Hermes 系统投递是独立边界，不能
  复制 OneBot echo 或用入站事件触发出站。

## Risks / Trade-offs

- **宿主版本缺少 registry hook** → 在 fake host contract 和最小兼容测试中明确所需的
  `cron_deliver_env_var`、`env_enablement_fn`、`standalone_sender_fn`；缺少 hook 时保持
  `unsupported`/不可用，不修改或 monkey patch Hermes core。
- **standalone 每次 cron 都创建 HTTP client** → 保持单次调用、明确关闭和既有请求超时，
  不把独立进程的短生命周期误扩展成插件全局连接池。
- **home channel 可能是群且群状态未知或已禁言** → 不改变既有出站失败和 MuteTracker
  规则；只返回真实安全结果，不把 home 配置当作可发送保证。
- **配置错误会在部署启动时暴露** → 错误只指出配置名和固定错误类别，不回显 token、目标
  ID 或原始环境值；未配置则保持无 home channel 的显式失败。
- **cron 内容可能携带附件** → 优先复用既有出站附件路径；没有经过 Hermes 安全边界的
  输入按 `unsupported` 降级，并记录 fixture 和实际失败分类，不自行下载或猜测路径。

## Migration Plan

1. 先新增脱敏配置、registry 和 cron fake fixture，再实现 `MilkyConfig` 字段与 manifest
   optional env；确认旧别名仍被拒绝、未配置普通收发不变。
2. 接入 `env_enablement_fn`、`cron_deliver_env_var` 和 standalone sender，补齐 live
   home、网关生命周期通知、`deliver=milky`、独立 cron、显式目标优先级和无目标失败的
   单元/集成测试。
3. 运行定向配置/registry/outbound 测试和 fake transport 质量门禁；只在用户明确授权且
   目标来自运行时环境时进行必要的本地 Milky smoke，不把真实凭证或响应写入 change。
4. 更新 `ARCHITECTURE.md`、`README.md` 和实现状态矩阵，运行全量 pytest、Ruff、format、
   build、diff check 以及 OpenSpec strict validation。
5. 若回滚，只移除 home channel registry/config 变更并恢复旧的未配置行为；不修改 Hermes
   core 的 persisted HomeChannel 数据，也不删除用户的外部配置。
