## Context

See `proposal.md` for the motivation. 当前 `milky/client.py` 以模块常量 `MAX_LOCAL_MEDIA_BYTES`
固定 `8 MiB`，本地 `Path` 和 `file://localhost` 经过一次普通文件读取后编码为 `base64://`；
`http(s)://` 和显式 `base64://` 则只做 URI 校验并原样传递。adapter、sender 和独立文件上传
都经过同一 materialization 语义，但当前配置对象没有携带该上限。

大小上限属于启动配置，而不是 Milky Action 参数。Hermes 负责入站资源下载和权限；本 change
只调整插件负责的出站本地读取边界，不在插件内下载远端 URL，也不复制入站资源规则。

## Goals / Non-Goals

**Goals:**

- 在 `MilkyConfig` 中保存一次解析后的本地出站资源上限，缺省为 `32 MiB`，并让 manifest、配置
  摘要、adapter、sender、standalone sender 和 materialization 使用同一个值。
- 允许部署者在 `8 MiB` 至 `32 MiB`（含边界）之间配置，以字节数表达，拒绝零值、负值、非整数
  和超出安全范围的值。
- 让图片、语音、视频、文档以及 CQ sticker 的本地路径在网络 Action 前按配置值拒绝超限，
  同时保持普通文件校验、单次读取、`base64://` 结果和安全错误分类。
- 用配置驱动的边界测试覆盖默认值、合法值、上下界、非法配置、恰好达到上限和超过上限。

**Non-Goals:**

- 不限制或下载 `http(s)://`，不解码或重新编码显式 `base64://`；它们继续由 Milky 端和其
  下游能力决定实际资源限制。
- 不增加单条消息或进程级附件总量限制，不改变并发、文本分块、附件顺序或 Action 重试语义。
- 不改变 Milky 协议、Action JSON、SSE、Hermes 入站资源所有权、SSRF/路径权限或文件名规则。
- 不把本地路径直接交给 Milky，也不通过放宽上限取消普通文件和非空校验。

## Decisions

### 由启动配置拥有上限，materialization 显式接收

在配置模块定义默认值、最小值和最大值，并把 `MILKY_MAX_LOCAL_MEDIA_BYTES` 解析为
`MilkyConfig.max_local_media_bytes`。解析在 `register(ctx)` 使用的启动配置阶段完成；配置对象
以显式参数向 adapter 的本地附件入口、`MilkyOutboundSender`、`FileUploader` 和公共
materialization helper 传递，不让这些模块自行读取环境变量。

这样可以保持“配置只在启动时解析一次”，也能让独立 cron sender 复用同一配置。直接调用
materialization helper 的测试和兼容调用保留 `32 MiB` 的安全默认，但运行时正式入口必须传入
已解析的配置值。

替代方案是让 helper 每次读取环境变量，或保留可变模块全局上限；前者违反启动配置边界，后者
会使同一进程内不同 sender 的行为不可预测，因此不采用。

### 值域以原始文件字节数表达

配置值表示本地文件原始字节数，而不是 Base64 字符数或 JSON 请求体大小。边界检查继续先用
文件 stat，再读取 `limit + 1` 字节，以处理 stat 后文件增长；恰好达到上限的文件允许，超过
上限、空文件、目录和不可读路径在网络前拒绝。错误继续使用 `invalid_input`，不回显路径、
文件名、Base64 或底层异常正文。

选择原始字节数是因为部署者能直接从文件大小理解限制；Base64 的约 `4/3` 放大属于实现和
请求体成本，在 README 中说明，不把编码长度暴露为另一套用户配置。

### 只修改本地 materialization，不扩大远端 URI 语义

`http(s)://` 仍只做格式校验并原样交给 Milky，插件不通过 HEAD、下载或读取响应来探测大小；
显式 `base64://` 也继续原样保留。只有插件实际读取的本地路径和 `file://localhost` 使用
`max_local_media_bytes`。这样不会引入新的 SSRF、远端可达性或资源所有权问题，也符合内网
Milky 部署仍可能存在服务端、代理和下游平台限制的事实边界。

### 以同一配置覆盖所有本地出站入口

普通 `MEDIA:` 图片/语音/视频、文档 upload 和 CQ sticker 必须最终走同一上限。adapter 入口
的预处理与 sender 的兼容路径都传递同一值；已经是 `base64://` 的中间结果只做既有 URI 校验，
不得再次读取或解码。这避免某一入口因调用层不同而意外恢复硬编码 `8 MiB` 或产生二次 I/O。

## Risks / Trade-offs

- [默认值从 8 MiB 增加到 32 MiB 后，Base64 和 JSON 请求会产生更高内存峰值] → 保留
  `8–32 MiB` 启动值域、单文件上限和 `limit + 1` 读取；文档明确 Base64 放大及内网不等于
  没有内存/服务端限制。
- [Milky 或下游平台对某类媒体的实际限制低于 32 MiB] → 插件只保证本地 materialization
  边界，不宣称远端必然接受；协议拒绝继续按既有 `rejected` 结果返回，不自动改投或重试。
- [配置与实际入口传递不一致] → 对 adapter、sender、文件 uploader、standalone 和 CQ
  路径增加同一边界值的 fake 集成测试，并断言超限时没有 Milky Action。
- [将入站图片 hash 的既有 8 MiB 限制误改为新配置] → 任务和文档只更新出站 materialization
  位置；Hermes 入站资源及其 hash 边界保持不变。

## Migration Plan

1. 在配置、manifest 和文档中加入 `MILKY_MAX_LOCAL_MEDIA_BYTES`，未配置时使用 `33554432`；
   现有部署无需修改环境即可获得新的默认上限。
2. 将解析后的值接入所有出站本地 materialization 入口，并把现有硬编码 `8 MiB` 测试改为
   默认 `32 MiB` 及可注入上限的测试。
3. 发布后若 Milky/下游对实际资源大小反馈拒绝，部署者可将配置降至 `16777216` 或
   `8388608`，修改配置后重启 Gateway 生效。
4. 回滚时移除配置接线并恢复默认 `8 MiB`；远端 URI、协议字段和历史消息不需要迁移。
