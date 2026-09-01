# hermes-plugin-milky 架构

## 1. 项目概览

`hermes-plugin-milky` 是 Hermes 的 Milky QQ directory plugin。它负责把 Milky
事件和 Action 接入 Hermes Gateway，不修改 Hermes core。

本文件只描述稳定的目录结构、组件职责、数据流、所有权和安全边界：

- 本文件：架构和模块边界；
- `openspec/`：可观察行为、边界条件、测试要求和实施进度；
- `README.md`：安装和开发入口。

当前仓库仍处于骨架阶段。目标能力尚未全部实现，不能把本文描述的运行时行为视为已交付。

## 2. 项目结构

```text
hermes-plugin-milky/
├── plugin.yaml                 # Hermes directory plugin manifest
├── __init__.py                 # 唯一公开入口：register(ctx)
├── adapter.py                  # BasePlatformAdapter 薄层
├── tools.py                    # 显式 Agent 工具发现入口
├── config/                     # 启动配置和默认值
├── milky/                      # Milky DTO、HTTP Action、SSE 和资源引用
├── inbound/                    # canonical、normalizer、mapper 和流水线
├── gates/                      # 确定性入站门禁
├── will/                       # routing 和 willingness 决策
├── session/                    # chat key、admission、wait buffer 和 system context
│   └── context.py              # 按 chat 隔离的 context-only 系统事件缓冲
├── state/                      # Bot 群禁言状态
├── outbound/                   # segment 格式化、路由和拆分
│   └── standalone.py           # 独立 cron 的一次性文本投递
├── tests/
│   ├── fixtures/               # 脱敏协议 fixture
│   ├── unit/
│   └── integration/
├── openspec/                   # 行为规范和 change artifacts
├── ARCHITECTURE.md
└── README.md
```

根目录是有意设计的：Hermes 直接从插件目录加载 `plugin.yaml` 和 `__init__.py`，不依赖
Python package entry point。`pyproject.toml` 只用于 uv 开发环境和质量检查，不作为插件
发布包入口。

## 3. 系统拓扑

```text
                         +----------------------+
                         |    Hermes Gateway    |
                         +----------+-----------+
                                    |
                         PluginContext / Adapter
                                    |
          +-------------------------+-------------------------+
          |                                                   |
          v                                                   v
   +--------------+                                  +---------------+
   | Inbound      |                                  | Outbound      |
   | pipeline     |                                  | sender        |
   +------+-------+                                  +-------+-------+
          |                                                  |
          v                                                  v
   MessageEvent                                      Milky HTTP Action
          ^                                                  ^
          |                                                  |
   Milky SSE /event  <-------------------------->  milky/client
          ^
          |
   Hermes core / cron 受信系统消息
```

Milky 的 HTTP Action 和 SSE 事件流是两个独立的传输边界：Action 使用 HTTP `POST`，事件
流使用 SSE `GET /event`。不使用 OneBot 的 echo、pending response map 或 WebSocket RPC
模型。Hermes core/cron 的受信系统消息只进入 outbound sender，不会反向进入 SSE 入站
pipeline。

## 4. 入口和生命周期

### 4.1 插件入口

`__init__.py::register(ctx)` 是唯一公开注册入口，只负责：

1. 读取 Hermes 上下文；
2. 解析启动配置；
3. 组装 Milky client、事件流、状态、策略和 adapter；
4. 调用 Hermes 的平台注册接口。

导入和注册阶段不得建立网络连接或创建长期后台任务。`adapter.py` 只负责 Hermes
生命周期和少量委托，不承载协议解析、Will 公式或大量 Action 编排。

`tools.py` 只注册显式设计的 Agent 工具。v0.1 不暴露任意 Milky Action catalog；未实现
的工具不得出现在 manifest 中。注册时还会声明 MILKY_HOME_CHANNEL 的 cron delivery
变量、无网络的 env_enablement_fn 和一次性 standalone_sender_fn。home metadata 使用
启动时解析的完整 group:/dm: chat key，显示名固定为 Milky Home；这些 hook 不启动
HTTP/SSE，也不改变普通消息的初始化就绪门槛。

根入口还通过 Hermes `ctx.register_command()` 登记唯一首批插件命令 `/milky`。该阶段只
登记 handler 和静态元数据，不建立网络连接或后台任务；adapter factory 将同一个
`SlashCommandService` 注入每个 adapter，只有 connect 完成后才绑定其生命周期拥有的
Milky client。插件不修改 Hermes 内置命令 registry、不注册任意 Action catalog。

出站媒体的本地附件由 plugin 在 Milky Action 边界执行受限 materialization：接受当前
Hermes `BasePlatformAdapter` 传入的本地路径、`Path` 和 `file://localhost`，只读取一次
常规、非空且不超过 8 MiB 的文件并生成 `base64://` URI。显式 `http(s)://` 和
`base64://` URI 原样保留，不下载或解码；plugin 不创建缓存、不复制 Hermes 入站资源的
SSRF/权限规则，也不把路径作为消息文本发送。Hermes core 仍拥有入站资源解析、下载和
Agent turn 生命周期，当前 host 不需要额外的 outbound materialization seam。

### 4.2 生命周期

```text
register
   |
   v
组装依赖（不联网）
   |
   v
connect
   |
   +--> get_login_info
   +--> get_group_list
   +--> get_group_member_info（每个群，查询 Bot 自身）
   +--> 初始状态完成
   +--> 启动 SSE /event 消费
   |
   v
message_receive 才能进入 inbound pipeline
   |
   v
disconnect：取消任务并释放 HTTP/SSE、定时器和状态刷新资源
```

初始登录身份和群禁言状态同步完成前，普通消息不得进入入站流水线。重连只继续消费
可见事件，不假设服务端补发丢失事件，也不恢复 wait buffer 或 Will 分数。

## 5. 核心组件

| 组件 | 职责 | 不负责 |
|---|---|---|
| `config/` | 解析环境变量、URL 和嵌套 Will policy | 建立连接、保存运行时状态 |
| `milky/models.py` | 校验 Milky DTO，保留安全扩展 | 业务决策、Hermes transcript |
| `milky/client.py` | HTTP Action、认证、envelope 和错误分类 | 入站排序、Agent 调度 |
| `milky/event_stream.py` | SSE 收帧、重连、取消和资源释放 | 业务 handler 的同步执行 |
| `milky/events.py` | 事件类型和系统事件解析 | 把系统事件伪装成普通消息 |
| `milky/resources.py` | 管理待补全的远端资源引用 | 自建下载、缓存或权限系统 |
| `inbound/` | 规范化消息、去重、映射和流水线 | 出站 Action |
| `gates/` | 按固定顺序执行硬性门禁 | 网络、概率、发送和 Will 评分 |
| `will/` | 决定 `wait` 或 `trigger` | 授权、网络和 Hermes Agent 调用 |
| `session/` | 管理 chat key、短暂 admission、有界 wait buffer 和 system context | Hermes session store、Agent 队列 |
| `state/mute_tracker.py` | 维护 Bot 的群禁言快照 | 消息正文、Will 和 Agent 状态 |
| `outbound/` | 目标路由、segment 格式化、文件上传和结果 | 入站白名单、Will 分数 |
| `adapter.py` | 连接 Hermes 生命周期和各组件 | 散落协议细节或业务策略 |

## 6. 依赖方向

```text
config  --->  __init__.py  --->  adapter.py
                              |
                              +--> inbound ---> gates ---> state
                              |       |
                              |       +------> will
                              |       |
                              |       +------> session
                              |
                              +--> milky/client <--- outbound
                              +--> milky/event_stream ---> milky/events
```

约束如下：

- `milky/` 不依赖 Gate、Will 或 Hermes transcript；
- `gates/` 不做网络 I/O，不使用随机数，不修改 Will 或 buffer；
- `will/` 是纯内存决策，不做授权、网络或文件系统操作；
- `session/` 不复制 Hermes session store 或 Agent 执行队列；
- `state/` 可以调用 Milky client，但不读取消息正文或调用 Agent；
- `outbound/` 不读取入站白名单和 Will 分数；
- 只有 `inbound/hermes_mapper.py` 及 adapter 的必要边界依赖 Hermes 消息类型。

## 7. 入站数据流

```text
SSE /event
  -> message_receive 进入普通入站；登记的系统事件进入 observe/context-only 分支
  -> tolerant parse / normalize
  -> canonical identity
  -> TTL dedup
  -> per-chat admission
  -> SelfMessageGate
  -> ChatAllowlistGate
  -> MutedGroupGate
  -> 纯文本斜杠命令？ -> Hermes gateway control / command mapper
  -> wait buffer
  -> WillEngine
  -> wait 或 trigger
  -> trigger 原子 drain 历史
  -> 资源和 reply 补全
  -> Hermes MessageEvent mapper
  -> adapter.handle_message()
  -> 提交成功后更新 reply cost
```

### 7.1 身份和去重

正常内部状态只接受以下 chat key：

- `group:<十进制群号>`；
- `dm:<十进制 QQ 号>`。

friend 使用 `dm:`，group 使用 `group:`。`temp` 在协议边界记录 `ignored_temp` 后丢弃，
不创建 canonical、buffer、Will、Hermes turn 或出站目标。

纯文本斜杠命令必须在 Gate 通过后、Will 运行前分流。命令正文去除允许的前导空白后仍
保留 `/command args`，专用 `MessageEvent` 使用 `MessageType.COMMAND` 和
`allow_gateway_control=True`，不添加 sender header 或 channel context。普通消息继续使用
既有正文映射和 `allow_gateway_control=False`。命令分支不补全资源、不写入 wait buffer、
不修改 Will，也不扣 reply cost；Hermes 负责内置、插件、未知命令以及 busy/follow-up/
interrupt 语义。

插件命令中当前只登记 `/milky`。无参数调用复用 adapter 生命周期绑定的唯一 Milky
client 请求 `get_impl_info`，成功正文是服务端完整原始 JSON envelope（包含未知扩展字段）；
带参数、未连接或存在多个无法由 source/profile 唯一选择的活动 client 时返回安全的
`invalid_input` 或 `unsupported` 分类。rejected、malformed、HTTP 和 transport unknown
结果不回显原始响应或异常文本。该命令不扩大 manifest 的 ToolSpec，也不提供任意 Milky
Action catalog。

canonical 至少包含平台、Bot 身份、场景、chat key、peer/sender、Milky message ID、时间、
typed segments、正文、mention/quote 信号、媒体引用、raw 和安全 metadata。

去重 key 至少为：

```text
milky:<self_id>:<chat_key>:<message_id>
```

去重必须在资源补全、Will 和 Hermes turn 之前完成，并使用有界 TTL 内存结构。缺少稳定
message ID 时不得伪造 ID，可以处理当前帧一次，但必须记录 `no_stable_message_id`。

### 7.2 Admission 和 Hermes 交接

同一 chat 的 canonical、Gate、buffer、Will 和 trigger drain 按 ingress sequence 串行；
不同 chat 可以并行。trigger batch 随后按相同顺序完成资源补全、mapper 和
`handle_message()` 提交。

这个顺序边界只保护插件状态和提交顺序，不等待 Agent 执行，也不复制 Hermes 的 busy、
follow-up、interrupt 或 pending 逻辑。交接失败只能重试同一 batch 或记录不可恢复失败，
不能无条件回填 buffer。

Hermes core/cron 产生的启动、重启、告警和 cron 结果走反向的受信出站路径：
Hermes 先解析 home channel 或显式目标，再调用同一个 outbound sender；该路径不创建
canonical、Gate、Will、wait buffer 或 Agent turn。

登记的 `group_nudge`、`friend_nudge`、`group_member_increase` 和
`group_member_decrease` 事件不创建 canonical、dedup、Gate、Will 或 Hermes turn。它们在同
chat admission 中获得 ingress sequence，写入独立有界的 system context FIFO，并只在下一次
该 chat 的 trigger 中与普通 wait 历史按顺序合并；注入后立即原子清除，溢出丢弃最早记录并
只保留安全诊断。其他系统事件继续 observe-only。

## 8. Gate、Will 和状态

### 8.1 Gate

Gate 是确定性的硬性门禁，顺序固定为：

1. `SelfMessageGate`：拒绝 `sender_id == self_id`；
2. `ChatAllowlistGate`：空白名单放行，否则要求完整 chat key 命中；
3. `MutedGroupGate`：群成员禁言或已确认的全体禁言为 `muted` 时拒绝；初始化未完成时默认拒绝，
   Milky 无法查询到的全体禁言状态不作为已禁言处理。

Gate deny 不增长 wait buffer，也不修改 Will 状态。

### 8.2 Will

Will 只在 Gate allow 后运行，输出 `wait` 或 `trigger`。routing 处理 direct、self/all/here
mention、quote、image、poke 和普通 group；willingness 在每个 chat 独立维护分数和时间戳。

精确字段、默认值、衰减公式、增益、概率、force 顺序和 reply cost 以 OpenSpec 为准。只有
Hermes `handle_message()` 正常返回、确认 trigger 已提交后，才扣除一次 reply cost。

### 8.3 MuteTracker

`MuteTracker` 是 Bot 群禁言状态的唯一拥有者。初始同步顺序为登录信息、群列表、逐群查询
Bot 自身成员信息；成员禁言只读取 Milky 的 `member.shut_up_end_time`，且启动同步与主动刷新
必须在 `get_group_member_info` 请求中使用 `no_cache=true`，避免服务端成员缓存掩盖刚发生的禁言。
Milky v1.3 没有读取全体禁言状态的 Action 或群实体字段，因此完成成员查询后 whole mute 可以是
`unknown`，只有明确的 `group_whole_mute` 事件才能更新为 `muted` 或 `unmuted`。

member mute 使用 `muted` 和 `unmuted`，whole mute 另外允许 `unknown`，并包含观测时间和刷新
时间。初始化未完成或查询失败时 Gate 仍保持 fail-closed；成功完成成员查询后，unknown
whole mute 不阻塞群消息，实际发送失败仍原样返回。冷启动逐群日志只显示确认被禁言的群，
最终汇总使用 `total`、`succeeded`、`failed`、`muted`、`unmuted` 和 `unknown` 计数。
`group_mute` 和 `group_whole_mute` 事件
更新对应状态；正时长的个人禁言会按 `member_mute_until` 启动本地 TTL 到期任务，到期后
自动更新为 `unmuted`，Gate 查询也会惰性校正已到期状态。群发送失败可以触发受锁、冷却和
并发上限保护的刷新，私聊失败不得刷新群状态；停止时必须取消 TTL 任务。

## 9. Milky 协议边界

### 9.1 URL、认证和 HTTP Action

`MILKY_BASE_URL` 去除末尾斜杠但保留 path prefix：

```text
<base>/api/{action}
<base>/event
```

Action 统一使用 HTTP `POST` JSON；无参数 Action 也发送 `{}`。默认认证为
`Authorization: Bearer <token>`。HTTP 状态、非 JSON、连接/超时和 envelope 的
`status`/`retcode` 必须分别分类。

成功发送必须使用 `data.message_seq` 的稳定字符串作为 Hermes message ID。发送超时表示
远端执行未知，可能产生副作用的请求不得盲目重试。

### 9.2 SSE 事件流

v0.1 使用 SSE `GET /event`。实现必须处理 `event:`、多行 `data:`、空行边界、断线、
退避、取消和 handler 隔离。malformed/unknown 事件安全记录并继续；handler 不得阻塞
receive loop。

除 `message_receive` 外，recall、request、notice、nudge、lifecycle 和未知事件默认
observe-only。请求事件不自动批准或拒绝，文件上传事件不自动下载。

### 9.3 Segment 和资源

入站 tolerant parser 支持 text、mention、mention_all、face、reply、image、record、video、
file、forward、market_face、light_app、xml、markdown 及协议扩展，并保留 typed 数据和安全
raw。正文使用稳定 placeholder：`face`、`img`、`record`、`video`、`file`、`forward`、
`market_face`、`light_app` 和 `xml` 均带有明确类型；未知 segment 不得静默变成普通文本或
Agent 指令。`light_app` 只展示 JSON payload 顶层 `meta` 根对象并递归保留其结构；缺少或
无法解析 `meta` 时使用 `NOT SUPPORTED`。

image 的 normalizer placeholder 只作为资源解析前的临时展示。trigger 阶段成功调用 Hermes
image helper 后，最终正文使用 `[img:file_name=<basename>]`，其中 basename 来自 helper 返回
本地路径，并与交给 Hermes 的对应 `media_urls` basename 保持一致；helper 失败或返回无效路径
时使用 `[img:file_name=NOT SUPPORTED]`。全体提及使用 `@全体成员`；file、forward 和
market_face placeholder 分别保留 `file_id/file_name`、`forward_id` 和 `summary`。

wait 阶段只保留资源引用，不下载。trigger 阶段才允许查询图片、文件或 reply。远端引用
必须交给 Hermes 公共 media helper；插件不创建下载目录、media cache、SSRF 规则、权限
规则或 Hermes 本地路径。

`forward_id` 只保留为 `[forward:forward_id=<forward_id>]` placeholder；普通 trigger 不调用
`get_forwarded_messages`，详情查询必须由未来独立、授权的 QQ Tool 按需发起。
完整 inline `reply` 只通过 `reply_to` header 和 Hermes reply metadata 表达，不在正文追加
成功占位符；缺失或补全失败时使用类型化的 `[reply:NOT SUPPORTED]` 降级。

## 10. 出站边界

- `group:<id>` 使用 `send_group_message`；
- `dm:<id>` 使用 `send_private_message`；
- 非法或 temp 目标在网络访问前失败，不回退默认目标；
- 文本和结构化内容由 `outbound/formatter.py` 生成 Milky segments；
- 图片、动画、语音和视频的显式 URI 或 plugin materialize 后的本地附件进入对应的 native `image`、`record` 或 `video` segment；
- 显式 `http(s)://` 和 `base64://` URI 原样保留；当前主机本地路径、`Path` 和 `file://localhost` 由 plugin 受限读取并生成 `base64://`，其他 `file://` 主机和未知 scheme 在网络访问前失败；
- 空白消息在网络访问前拒绝，超长文本按明确边界拆分；
- file 不是 message segment，必须使用对应的 upload Action；
- Hermes 的文档附件使用 `upload_group_file` 或 `upload_private_file`，请求只接收 plugin 已 materialize 的 `file_uri` 和校验后的 `file_name`；
- 未实现的编辑、撤回、reaction 等能力返回 `unsupported`；
- 结果区分 `rejected`、`transport_unknown`、`malformed` 和 `unsupported`。

Agent 的普通文本可以使用受限的 CQ-compatible 语法表达模型选择的 `at` 和 `reply`。
这只是出站适配层的文本解析约定：确认有 Milky native segment 映射时才生成 native
segment，其他类型逐片段原样生成 text fallback；生成的请求仍严格使用 Milky wire
protocol。该约定不实现 OneBot CQ 入站、OneBot Action、echo 或 WebSocket RPC，也不改变
Milky 的能力声明。

v0.1 只允许显式设计的 Agent 工具。工具必须独立校验类型、范围和目标，再调用同一个
Milky client；当前固定注册 17 个 ToolSpec（既有的 9 个工具和本 change 新增的
`get_forwarded_messages`、`get_private_file_download_url`、`kick_group_member`、`quit_group`、
`delete_friend`、`get_friend_requests`、`accept_friend_request`、`reject_friend_request`），
不提供任意 Action catalog。入站正文、mention 或 Will 分数不能赋予工具权限。查询工具
返回已校验的完整 raw envelope；状态变更工具只由显式调用触发，结果未知时不自动重试。

网关内的系统消息复用已连接 adapter 的 MilkyOutboundSender。独立 cron 通过
outbound/standalone.py 为每次调用创建并关闭临时 client，支持同一文本、分块、目标路由、
SendResult 和错误分类；standalone 当前不接受附件/线程参数，统一返回 unsupported，不会
自行下载 URL 或把本地路径塞进消息 segment。两条路径都不自动 retry
未知执行结果，也不改投其他目标。

## 11. 数据存储和所有权

v0.1 不使用插件自有持久化数据库。插件内只有进程内、可丢失的运行时状态：

- canonical TTL dedup；
- 每 chat wait buffer；
- 每 chat system context buffer；
- 每 chat willingness 状态；
- MuteTracker 群状态。

Hermes 拥有 Agent turn、session/transcript、入站媒体下载、缓存、路径权限和资源
materialization。Milky client 拥有 URL、认证和 HTTP envelope；event stream 拥有 SSE 生命周期；
outbound 拥有 Milky segment、文件 upload 和受限的本地附件 materialization：本地文件只在
单次发送前读取并转换为 `base64://`，不建立持久化缓存或第二套 SSRF/权限规则。standalone
sender 只拥有一次调用的临时 client 生命周期，当前仍只承诺文本投递，不继承 adapter 的
本地附件入口。

`61d99fc` 移除了当前 Hermes host 仍需要的 plugin 本地 materialization 路径；本 change
通过重构恢复该兼容边界，不修改 Hermes core，不依赖不存在的 outbound seam，也不把完整
文件内容、路径、URI 或凭证写入日志、异常和结果。

## 12. 配置与安全

配置入口只有：

- 必需：`MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN`；
- 可选：`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、
  `MILKY_HOME_CHANNEL`。

配置只在启动时解析一次，并输出只包含 has_home_channel 的脱敏摘要。
MILKY_HOME_CHANNEL 是出站系统/cron 默认目标，不加入入站 allowlist；未配置时
deliver=milky 不回退到默认频道、origin、群聊或私聊。仍不使用旧的 allowed
groups/users、muted groups、require mention 或扁平 dm policy。

所有日志、异常、SendResult、fixture、快照和执行记录不得包含 token、Authorization
header、真实媒体路径或敏感正文；经过登记的业务 ID、chat key 和 message ID 可以原样用于
关联。普通诊断优先使用 chat key、message ID、reason 和错误类别；已注册 Tool 的专用日志
只记录安全业务入参和远端结果结构投影，不记录完整响应、下载/媒体 URL、本地路径、文件内容、
凭证或自由文本 `reason`。Tool 调用方仍取得完整成功 raw envelope。

## 13. 开发与验证

Python 运行时为 3.13+，使用 uv 管理环境和依赖。常用检查：

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
git diff --check
npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict
```

测试优先使用 fake Hermes、fake Milky transport、SSE fixture 和脱敏协议数据；真实 Milky
smoke 只能从运行时环境读取凭证。新增行为先补 OpenSpec 对应契约或 fixture，再实现和测试。

当前 `refine-inbound-context-rendering` 已有自动化证据覆盖单行上下文、结构化 placeholder、
`light_app.meta` 投影、context-only 系统事件和 forward 不自动查询；其他未被当前 change
覆盖的 Milky Action、WebHook、WebSocket fallback、自动 forward 展开和持久化状态仍未实现。

在宣布能力可用前，必须有自动化证据证明：唯一入口、canonical/dedup 顺序、Gate/Will 分离、
正确禁言字段、入站 Hermes 媒体所有权与出站 plugin materialization、文件 upload、temp/unknown/unsupported 降级、SendResult
和秘密脱敏边界均成立。

## 14. 非目标和扩展边界

v0.1 不复制 OneBot v11 的 Action、CQ 入站协议、echo 或 WebSocket 回包模型；仅允许
第 10 节所述 Agent 出站层的 CQ-compatible 文本解析例外。该例外不改变 Milky wire
protocol 或 OneBot 能力声明。不实现 WebHook，不注册任意 Action catalog，不管理插件自己的
媒体缓存，也不处理 temp 会话。standalone cron 目前只承诺无 thread 的文本/已格式化内容
投递，不继承 adapter 的本地附件入口。

WebSocket fallback 和更多 Agent 工具必须先通过独立 OpenSpec 契约、Hermes 扩展点确认和
测试，再加入本架构。

## 15. 术语

| 术语 | 含义 |
|---|---|
| directory plugin | Hermes 从插件目录直接发现并加载的插件形式 |
| canonical | 经过身份、场景、时间和 segment 规范化的领域消息记录 |
| Gate | 进入 Will 和 Hermes 前的确定性硬性门禁 |
| Will | 决定消息等待或触发 Agent 的策略层 |
| wait buffer | 插件进程内按 chat 隔离的有界待触发消息缓存 |
| trigger batch | 触发时从 wait buffer 原子取出的历史消息批次 |
| Milky Action | Milky HTTP API 的单次 POST 操作 |
