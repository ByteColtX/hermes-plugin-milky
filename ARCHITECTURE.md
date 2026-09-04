# hermes-plugin-milky 架构基线

> 本文记录 v0.1 的稳定模块边界、数据流、所有权和限制。安装与当前能力见 `README.md`；可观察行为和测试要求见 `openspec/`。

## 1. 项目识别

| 项目 | 内容 |
|---|---|
| 名称 | `hermes-plugin-milky` |
| 类型 | Hermes directory plugin，由插件目录直接发现 |
| 用途 | 将 Milky QQ 事件、Action 和出站能力适配到 Hermes Gateway |
| 运行时 | Python 3.13+ |
| 协议 | Milky v1.3；HTTP Action + SSE `GET /event` |
| 公开入口 | 根目录 `__init__.py::register(ctx)` |
| 仓库 | [ByteColtX/hermes-plugin-milky](https://github.com/ByteColtX/hermes-plugin-milky) |
| 更新日期 | 2026-09-04 |

边界以本文和 `AGENTS.md` 为准；可观察行为、测试要求和 change 进度以 `openspec/` 为准，安装与配置以 `README.md` 为准，代码与测试提供当前实现证据。单次本地测试、fake host、OpenAPI 文档清单或 fixture 不能证明真实 Hermes 宿主和 Milky 服务已经支持某项能力。

## 2. 项目结构

```text
hermes-plugin-milky/
├── plugin.yaml                 # Hermes manifest；声明插件、依赖、环境和 ToolSpec
├── __init__.py                 # 唯一公开入口：register(ctx)
├── adapter.py                  # BasePlatformAdapter 生命周期和边界委托
├── slash_commands.py           # /milky 命令
├── config/                     # 启动配置、URL、Will policy
├── milky/                      # DTO、解析、HTTP Action、SSE、资源和日志
├── inbound/                    # normalizer、canonical、pipeline、mapper、系统事件
├── gates/ / will/              # Gate、routing、willingness 和 reply cost
├── session/ / state/           # identity、dedup、buffer、MuteTracker
├── outbound/                   # formatter、sender、附件、上传和 ToolSpec handler
├── skills/                     # qq-reference、qq-tools 只读 bundled skill
├── scripts/                    # milky_smoke.py；受控本地 smoke
├── tests/                      # 脱敏 fixture、fake transport 和模块测试
├── openspec/                   # 主 specs、active changes 和 evidence ledger
├── ARCHITECTURE.md
├── README.md
└── CONTRIBUTING.md
```

Hermes 读取 `plugin.yaml` 后调用根 `__init__.py`。`pyproject.toml` 和 `uv.lock` 只负责开发环境、质量检查和构建，不是第二个插件入口。

## 3. 系统模型与数据流

```text
                         +----------------------+
                         |    Hermes Gateway    |
                         | registry / Agent     |
                         +----------+-----------+
                                    |
                       register(ctx) / adapter
                                    |
             +----------------------+----------------------+
             |                                             |
             v                                             v
      +-------------+                               +-------------+
      | Inbound     |                               | Outbound    |
      | pipeline    |                               | sender      |
      +------+------+                               +------+------+
             |                                             |
             v                                             v
      Hermes MessageEvent                         Milky HTTP Action
             ^                                             ^
             |                                             |
      Milky SSE GET /event  <------>  milky/client + auth
             ^
             |
      session / Will / MuteTracker state
```

HTTP Action 与 SSE 是独立边界：Action 使用 `POST` JSON，事件流使用 `GET /event`；不使用 WebSocket echo、pending response map、WebHook 或 WebSocket fallback。

普通入站顺序固定为：

```text
SSE /event
  -> 只接受 message_receive
  -> parse / normalize / canonical
  -> TTL dedup
  -> per-chat admission
  -> SelfMessageGate -> ChatAllowlistGate -> MutedGroupGate
  -> /milky 命令分流，或写入 wait buffer
  -> Will.decide
  -> wait；或 trigger 时原子 drain 当前 chat
  -> trigger 阶段补全资源和 reply
  -> 映射 Hermes MessageEvent
  -> adapter.handle_message()
  -> 提交成功后扣一次 reply cost
```

同一 chat 按 ingress sequence 串行，不复制 Hermes 的 busy、follow-up、interrupt 或 Agent 队列；不同 chat 可以并行。系统消息和 cron 可复用已连接 sender，或使用一次性 client 投递。

## 4. 组件职责与依赖

| 组件 | 主要职责 |
|---|---|
| `__init__.py` / `adapter.py` | 读取 context、解析配置、注册插件、管理连接和 Hermes 委托 |
| `milky/` | DTO、容错解析、HTTP/SSE、资源引用和错误分类 |
| `inbound/` | canonical、dedup 后的管线、segment 和 Hermes 映射 |
| `gates/` / `will/` | 固定 Gate 顺序、`wait`/`trigger`、willingness 和 reply cost |
| `session/` / `state/` | chat 状态、buffer、去重和 MuteTracker |
| `outbound/` | 目标、segment、拆分、附件、上传和固定工具 |

依赖方向：

```text
config -> register -> adapter
                         ├── inbound -> gates -> state
                         │          ├── will
                         │          └── session
                         ├── milky/client <- outbound
                         └── milky/event_stream -> parser/models
```

Gate 不做网络 I/O，Will 不做授权，session 不复制 Hermes 队列；只有 mapper 和必要的 adapter 边界依赖 Hermes 消息类型。

## 5. 生命周期与运行边界

### 注册与连接

`register(ctx)` 是唯一公开入口：读取 context、一次性解析配置，注册 `qq-reference`、`qq-tools`、`/milky` 和显式 ToolSpec，登记 `MILKY_HOME_CHANNEL`，组装 client/SSE/MuteTracker/Will/session/pipeline/sender，并调用 Hermes 平台注册接口。`platform_hint` 只包含 `You are communicating via Hermes's Milky QQ platform.`；宿主提供 `register_system_prompt_section` 时，入口另外登记 `hermes-plugin-milky.qq-platform-guidance` 的 `after_memory` section。

该 section 使用注册实例共享的进程内身份快照。adapter 在登录、群列表和每个群的 Bot 成员状态同步成功、普通消息入口完成组装后发布已确认的 `self_id` 和 `nickname`；section renderer 只读快照，不访问 Milky client，不读取 session metadata，也不从消息或配置推断身份。未连接、同步失败或 nickname 无法安全规范化时，section 返回空内容，由 Hermes 跳过该 section；缺少宿主 section API 时仍完成只含首句的平台注册。

导入和注册阶段不得联网、建立 SSE、创建长期任务或写入用户全局 skills 目录。配置错误必须在启动时安全失败，不能回显凭证。

连接就绪顺序是：

```text
connect
  -> get_login_info
  -> get_group_list
  -> 对每个群 get_group_member_info(..., user_id=self_id, no_cache=true)
  -> MuteTracker 初始同步完成
  -> 启动 SSE /event
  -> 开放 message_receive pipeline
```

身份和禁言初始状态同步完成前，普通消息不得进入 pipeline。重连不假定服务端补发断线期间丢失的消息，也不恢复 wait buffer、system context 或 Will 分数。

### 停止与命令

`disconnect()` 必须幂等地取消 SSE consumer、detached pipeline、定时器和状态刷新，关闭 HTTP/SSE 资源，并解除 sender/command 生命周期绑定。

插件只有 `/milky` 命令，在 Gate 通过后、Will 之前分流，不进入 wait buffer、资源补全或普通 Agent 正文；无参数时通过已连接 client 调用 `get_impl_info`。未连接、参数错误、rejected、malformed、HTTP 错误和 transport unknown 只返回安全分类，不临时创建 client。

## 6. 入站消息契约

### 身份、canonical 与 dedup

普通状态只接受 `dm:<十进制 QQ 号>`（friend）和 `group:<十进制群号>`（group）。

空值、负数、非数字和额外分隔符均非法。`message_scene=temp` 记录 `ignored_temp` 后丢弃，不创建 chat key、canonical、dedup、buffer、Will、Hermes turn 或出站目标。

canonical 至少包含 `platform`、`self_id`、scene、chat key、peer/sender ID、Milky message ID、Unix 秒时间戳、typed segments、正文、mention/quote、媒体引用、raw 和安全 metadata。

稳定去重 key 为：

```text
milky:<self_id>:<chat_key>:<message_id>
```

TTL map 的检查和插入必须原子完成，且早于资源补全、Will 和 Hermes turn。缺少 `message_id` 时不得伪造稳定 key；当前帧可以处理一次，但记录 `no_stable_message_id`。

### Admission、buffer 与 Hermes 交接

同一 chat 的 canonical、Gate、buffer、Will 和 trigger drain 在 admission 边界内按 ingress sequence 串行；Gate deny 不增长 buffer 或修改 Will。`wait` 不调用 Hermes、不写 transcript；`trigger` 先原子 drain 当前 chat，再按序完成资源解析、mapper 和 `handle_message()` 提交。历史 wait 只进 `channel_context`，当前消息只进本次正文；handoff 失败只能重试同一批次或记录不可恢复失败，不得无条件回填。提交正常返回后才扣一次 reply cost，不等待 Agent 完成。

### 系统事件

只有 `message_receive` 进入普通消息路径。Milky SSE `GET /event` 收到的
`message_recall`、request、notice、lifecycle 和未知事件默认 observe-only，不伪装成普通消息。

`message_recall` 只有在 `message_scene` 为 `friend` 或 `group`，且 `peer_id`、`message_seq`、
`sender_id` 是已确认的非负整数时，才写入对应 chat 的 system context FIFO：friend 使用
`dm:<peer_id>`，group 使用 `group:<peer_id>`。`operator_id` 缺失或为 null 时，body 为
`uid <sender_id> 撤回了消息 msg_seq <message_seq>`；群聊存在操作人时为
`管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`；好友存在操作人时
使用 `uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`，不推断管理员角色。
事件类型前缀由 renderer 统一添加为 `<event message_recall>`。

`group_nudge`、`friend_nudge`、`group_member_increase`、`group_member_decrease` 和合法
`message_recall` 可写入每 chat 独立、有界、可丢失的 system context FIFO；不创建 canonical、
dedup、Gate、Will、reply cost 或独立 Hermes turn。group nudge 只有 `receiver_id == self_id` 才产生
self-poke，friend nudge 只有明确的自身接收方向且无自身发送冲突才产生 self-poke；该特征仍不改变
nudge 的 observe-only 边界。它们与普通 wait 消息共享 ingress sequence，在下一次同 chat trigger
中按序合并并原子清除。缺少 chat key、撤回必要字段或撤回场景非法时记录 `malformed`/`unsupported`，
不创建上下文；其他事件不自动发送或批准。

正文使用固定格式：`group_nudge` 为 `uid <sender_id> 戳了 uid <receiver_id>`，`friend_nudge` 为
`uid <user_id> 戳了一下`；成员加入/退出使用“加入了群聊”或“退出了群聊”，并附已确认的 JSON
Details。缺少 `operator_id` 或 `invitor_id` 时省略，不补空字符串；撤回事件只展示撤回元数据，
不调用 `get_message`，不恢复被撤回消息正文，也不把 `display_suffix`、动作图片 URL、timestamp、
raw payload 或未确认扩展字段放入上下文。

## 7. Segment、资源与 Hermes 映射

### Segment 解析与正文

normalizer 不做网络 I/O。支持并保留 `text`、`mention`、`mention_all`、`face`、`reply`、
`image`、`record`、`video`、`file`、`forward`、`market_face`、`light_app`、`xml`、`markdown`；
未知 segment 只保留安全 raw 和诊断，不变成正文或 Agent 指令。

| segment | 正文展示 |
|---|---|
| `face` | `[face:<face_id>]` |
| `mention_all` | `@全体成员` |
| `image` | 临时 `[img:file_name=<summary/resource_id>]`；成功 materialize 后替换为 helper basename |
| `record` / `video` | `[record:NOT SUPPORTED]` / `[video:NOT SUPPORTED]` |
| `file` | `[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]` |
| `forward` | `[forward:forward_id=<forward_id>]`；普通 trigger 不自动展开 |
| `market_face` | `[market_face:summary=<summary>]` |
| `light_app` | `[light_app:{"meta":...}]` 的完整递归 `meta` 根对象 |
| `xml` | `[xml:NOT SUPPORTED]` |
| `markdown` | 原样进入正文 |

缺失字段使用 `NOT SUPPORTED`，不得补造 ID、文件名或路径。mention 区分 self、all、here、none；直接提及只有 `mention.user_id == self_id` 才是 self，reply 只有 `reply.data.sender_id == self_id` 才是 self quote；Milky v1.3 不从普通文本或 mention 名称推断 here。

inline `reply` 通过单行 header 的 `reply_to` 和 Hermes reply metadata 表达；补全失败才使用 `[reply:NOT SUPPORTED]`。普通 `forward` 只保留 `forward_id`。

### Context、资源和媒体

普通历史消息使用单行格式：

```text
<sender uid <sender_id> msg_id <message_id> reply_to <reply_id>> <body>
```

缺失字段省略；系统事件使用 `<event <event_type>> <body>`。header/body 中的回车、换行、尖括号及反斜杠必须编码为不改变记录边界的字面量。无历史记录时 `channel_context` 为 `None`，不是空字符串；当前 trigger 不进入其中。

wait 阶段只保存 URL、resource/file ID、文件名、MIME/大小提示和原始 segment，不下载文件；trigger 阶段才可调用已确认的 Milky resource Action、`get_message` 或 Hermes helper。group file 使用 `get_group_file_download_url(group_id, file_id)`；private file 只有 `file_hash` 可用时才使用 `get_private_file_download_url(user_id, file_id, file_hash, ...)`。

Hermes 拥有入站资源的下载、缓存、SSRF、权限和本地路径规则；plugin 不创建第二套 media cache、下载目录或权限规则。只有 Hermes helper 返回且通过本地路径校验的结果才能进入 `MessageEvent.media_urls` / `media_types`。

同一 trigger 的媒体按“历史 context 中成功 materialize 的直接图片，再到当前消息和实际展示的 reply 图片”顺序合并；成功图片先在本批次内以受限流式 SHA-256 按 bytes 选择首次代表，hash 失败时仅按有效本地路径去重，并同步维护等长 `media_types`。正文 occurrence、代表 basename、MIME、`channel_context`、`media_urls` 和 `media_types` 必须来自同一份 batch finalization；不得从 context 文本反解析路径，也不得提升历史音频、视频、文件、未知引用或未展示的嵌套 reply 图片。hash 只读取 Hermes helper 已返回的非空常规本地文件，大小上限为 8 MiB，不建立跨 batch/session 的缓存。

### Hermes MessageEvent

friend 映射为 private message，group 映射为 group message；`source` 固定为 `milky`，`message_id` 使用 Milky ID 字符串，并保留 sender、raw、timestamp、reply metadata、正文、安全 metadata、`channel_context` 和已确认附件。没有受支持正文、媒体或结构化内容时记录丢弃原因，不创建空 `MessageEvent`。

## 8. Gate、Will 与禁言状态

### Gate

Gate 是进入 Will 和 Hermes 前的确定性硬性门禁，顺序不可变：

1. `SelfMessageGate`：`sender_id == self_id` 时拒绝；
2. `ChatAllowlistGate`：`MILKY_ALLOWED_CHATS` 为空则放行，否则要求完整 chat key 命中；
3. `MutedGroupGate`：member 或 whole 为 `muted` 时拒绝，未成功维护为 `unmuted` 前拒绝。

Gate 不包含概率、关键词、回复发送、网络查询或 Will 分数修改。

### Will

Will 只在 Gate allow 后运行，输出 `wait` 或 `trigger`。`WillInput` 至少包含 self/chat/channel、segments、正文、独立的 self mention/self quote/self-poke 特征、reply 存在性与目标序号、image、event type 和时间。routing 的 `mention`、`quote`、`poke` 分别只匹配明确涉及 Bot 自身的目标；nudge 即使形成 self-poke routing 信号仍保持 observe-only。

配置使用嵌套 `engine`、`routing`、`willingness`、`priority` schema。routing 按 direct、mention、mentionAll、quote、poke、allMessage、keywords 顺序处理；willingness 按 chat 隔离维护 `score`、`lastMessageAt`、`lastDecayAt`。公式、半衰期、ratio、概率 clamp、force、关键词、direct/image/reply/poke 和时钟回拨以 OpenSpec 为准，clock/random 依赖注入。

只有 Hermes 提交成功后才扣一次 reply cost；wait、Gate deny、system context 和命令不扣费。
旧的扁平 dm policy、allowed groups/users、muted groups、require mention 及旧 routing 字段
不得静默迁移。

### MuteTracker

`MuteTracker` 是 Bot 群禁言状态的唯一拥有者。初始同步依次调用：

```text
get_login_info
-> get_group_list
-> get_group_member_info(group_id, user_id=self_id, no_cache=true)
```

member 禁言只读取 `member.shut_up_end_time`；member 和 whole 分开维护。初始化或维护失败时 fail-closed，刷新失败保留上次二态状态。Milky v1.3 没有可读取 whole mute 的 Action 或群实体字段时，whole 为 `unknown`；只有明确的 `group_whole_mute` 事件才能改为 `muted`/`unmuted`。

`group_mute` 的 `duration=0` 表示取消，`group_whole_mute` 按 `is_mute` 更新。群消息出站失败可触发有锁、冷却和并发上限的刷新；私聊失败不得查询群状态。成员禁言可由本地 TTL 任务转为 `unmuted`，停止时取消任务。

## 9. Milky HTTP 与 SSE

`MILKY_BASE_URL` 去除末尾斜杠但保留 path prefix：

```text
<base>/api/{action}
<base>/event
```

Action 一律使用 HTTP `POST` JSON；无参数 Action 也发送 `{}`。认证为 `Authorization: Bearer <token>`，凭证不得进入日志、异常、结果、fixture 或快照。

client 必须区分 HTTP 错误、非 JSON、协议 `status`/`retcode` 拒绝、malformed data、unsupported、transport unknown 和 timeout。HTTP 200 不等于协议成功；成功发送用远端 `data.message_seq` 生成稳定字符串形式的 `SendResult.message_id`。超时代表远端是否执行未知；可能有副作用的 Action 不盲目重试。

SSE receive loop 必须处理 `event:`、多行 `data:`、空行边界、断线重连、退避、取消、未知或损坏事件和资源释放。malformed/unknown 事件安全记录并继续；handler 不得阻塞接收循环。

## 10. 出站消息与固定工具

### 目标、segment 和附件

- `group:<id>` 只能调用 `send_group_message`；`dm:<id>` 只能调用 `send_private_message`；非法和 temp
  目标在网络访问前失败，不回退默认频道或另一种场景；
- formatter 生成 Milky segment，空白消息在网络访问前拒绝，未使用 `[SPLIT]` 的长文本由
  `chunking.py` 拆分；
- 图片、语音、视频分别进入 `image`、`record`、`video` native segment；文档使用独立的
  `upload_group_file` / `upload_private_file`，不塞入 message segment；未实现的编辑、撤回、reaction
  等能力返回 `unsupported`，不报告假成功。

普通出站文本只有在整行严格等于 `[SPLIT]`（区分大小写、无前后空白）时才启用分段。插件删除
标记行及其分隔边界，过滤空段，最多形成三个逻辑文本单元；超过三段时把尾部按原顺序合并
到第三段。随后每个逻辑单元仍使用既有长度边界分块；如果物理文本消息因此超过三条，插件
在首个消息 Action 前整体返回本地边界错误，不截断、不部分发送。没有有效标记的普通长文本
不受三条上限影响。

Agent 的本地附件通过 Hermes 的 `MEDIA:<local_path>` 指令进入上述入口：普通回复把指令放在
最终回复中，显式调用通用 `send_message` 时把指令放在 `message` 参数中。Hermes 按扩展名调用
`send_image_file`、`send_voice`、`send_video` 或 `send_document`。该指令是平台发送约定，不是
25 个显式 QQ ToolSpec；Agent 不应因为 ToolSpec 列表没有 `send_video` 而判断 Milky 没有媒体发送能力。

Hermes 从同一 Agent 回复提取的 `MEDIA:` 附件不属于插件文本分段批次。插件先按顺序完成所有
文本单元，再由 Hermes 按提取顺序调用图片、语音、视频 native 入口或独立文件 upload；当前
不支持文本段与附件交错，插件不从原始正文中的 `MEDIA:` 位置推断顺序。需要交错投递时必须
由 Hermes core 提供有序文本/附件交接契约。

出站收到本地路径、`Path` 或 `file://localhost` 时，只读取一次常规、非空且不超过 8 MiB 的文件并
生成 `base64://`；合法 `http(s)://` 和显式 `base64://` 原样保留，不下载或解码。文件上传携带
安全文件名，不能假定 Milky 能访问 plugin 的本地路径。每个可能有副作用的 Action 最多提交一次；
部分失败保留已成功结果和首个失败分类，不发送纯文本 fallback。

### 受限 CQ-compatible 语法

普通 Agent 文本可使用：

- `[CQ:at,qq=<uid>]` -> native `mention`；
- `[CQ:reply,id=<msg_id>]` -> native `reply`；
- `[CQ:image,file=file:///path/to/sticker.ext,type=sticker]` -> native `image`（仅 sticker）。

CQ 图片的 formatter 只负责解析，不做文件 I/O；sender 在消息 Action 前复用统一
materialization。CQ sticker 的 `file://localhost`、`file:///...` 和本地路径只读取一次合规文件并
转换为 `base64://`。普通图片不使用 CQ image，使用 `MEDIA:<local_path>` 入口。失败时在网络访问
前返回分类错误，不发送原始 CQ 或纯文本 fallback。

未确认映射、未知类型或参数错误按 text fallback 原样发送，但 fallback 不代表 native 语义
执行。`uid` 和 `msg_id` 只能来自当前消息或 `channel_context` 的真实 header；不实现 CQ 入站、
OneBot Action、OneBot echo 或 WebSocket RPC。

`[SILENT]` 是 Hermes core 的无需回复控制标记。Milky plugin 不解析、删除或根据它调用 Action；
仅接收 Hermes core 已决定交付的文本或独立附件。

### ToolSpec

工具是显式、固定、可审计的能力边界，不是任意 Milky Action catalog。工具独立校验类型、
范围、额外字段和目标；入站正文、mention、allowlist 或 Will 分数不能授予工具权限。状态
变更只能由显式调用触发，不能由 friend request、群通知、关键词或普通消息自动触发。

当前 manifest 公开 25 个固定 ToolSpec：

```text
send_profile_like, send_friend_nudge, send_group_nudge, recall_group_message,
get_group_info, get_group_member_list, get_group_member_info, set_group_member_mute,
set_group_whole_mute, get_forwarded_messages, get_private_file_download_url,
kick_group_member, quit_group, delete_friend, get_friend_requests,
accept_friend_request, reject_friend_request,
get_group_file_download_url, accept_group_request, reject_group_request,
accept_group_invitation, reject_group_invitation, get_group_files,
get_friend_info, set_group_member_special_title
```

名称与 Milky operationId 一一对应；参数、最小响应结构和错误分类由 `__init__.py`、`outbound/tools.py`、
`milky/client.py` 和相关 OpenSpec 约束。成功可返回协议要求的 raw envelope，但日志只用安全投影；
结果未知返回 `transport_unknown`，不自动重试。新增工具必须先有独立 OpenSpec、参数边界和安全回归。

群文件工具使用 `get_group_file_download_url(group_id, file_id)` 查询下载链接，或使用
`get_group_files(group_id, parent_folder_id?)` 查询文件和文件夹数组；查询结果保留完整 envelope，
不下载、不缓存、不解码。群请求工具使用 `notification_seq`、`notification_type` 和 `group_id`，
群邀请工具使用独立的 `invitation_seq`；接受/拒绝 Action 只由完整的显式 Tool 调用触发，事件、
正文、关键词和 Will 不会自动提交。四个群管理 Action 的未知结果为 `transport_unknown`，不重试、
不换目标、不更新本地状态。

`get_friend_info` 只接受 `user_id`，成功时保留完整 envelope 和非空 object `data`；当前公开
Milky v1.3 文档未声明该 operation，因此不把好友资料字段写入 `FriendEntity` 或其他本地 DTO，
目标服务不支持时按远端错误边界返回。`set_group_member_special_title` 只接受
`group_id`、`user_id`、`special_title`，空字符串原样传递，成功只接受空 object；超时、连接或
读写失败返回 `transport_unknown`，只提交一次且不更新本地群成员状态。

## 11. 所有权、安全与配置

### 状态与所有权

插件不使用自有持久化数据库。进程内状态只有 TTL dedup、每 chat wait buffer、system
context buffer、willingness 状态，以及 MuteTracker 群状态和 TTL 任务；停止或重连时可以丢失。

| 所有者 | 负责内容 |
|---|---|
| Hermes | Agent turn、session/transcript、入站媒体下载与缓存、路径权限和资源 materialization |
| `milky/client` | 认证、URL、HTTP transport 和 raw envelope |
| `inbound` | canonical、segment 解析、chat pipeline 和 Hermes MessageEvent |
| `outbound` | Milky segment、文件 upload 和受限出站本地 materialization |
| `MuteTracker` | Bot 群 member/whole 禁言观测状态 |

### 安全边界

- 秘密只从运行时环境或安全凭证存储注入；日志、异常、`SendResult`、fixture、快照和 OpenSpec
  artifact 不包含凭证、完整敏感正文、Base64、媒体 URL、本地路径或完整 HTTP body；
- 业务 ID、chat key 和 message ID 可用于安全关联，但 inbound 不是工具授权来源；Action 的
  类型、范围和目标须在进入 HTTP client 前校验；
- unknown segment/event、未确认资源、malformed、unsupported 和未知执行结果必须显式分类，
  不补默认值、不静默改名、不伪造成功、不跨场景回退。

### 启动配置

配置只在启动时解析一次：

| 环境变量 | 必需 | 作用 |
|---|---:|---|
| `MILKY_BASE_URL` | 是 | HTTP(S) 基址；保留 path prefix |
| `MILKY_ACCESS_TOKEN` | 是 | Bearer token；只在认证层使用 |
| `MILKY_ALLOWED_CHATS` | 否 | 完整 `group:<id>` / `dm:<id>` 入站白名单；为空放行 |
| `MILKY_WILL_POLICY` | 否 | 嵌套 `engine`、`routing`、`willingness`、`priority` 策略 |
| `MILKY_SESSION_BUFFER_SIZE` | 否 | wait buffer 上限；默认 20，0 表示禁用历史缓冲 |
| `MILKY_HOME_CHANNEL` | 否 | 系统/cron 默认目标；完整 `group:<id>` 或 `dm:<id>` |

`MILKY_HOME_CHANNEL` 不参与入站 allowlist；未配置时不猜测 origin、默认频道或私聊目标。已
连接 adapter 的 live 投递复用普通 sender；standalone cron 每次创建并关闭临时 client，
目前只支持文本和已格式化文本，不支持媒体、文件或线程参数。

## 12. 测试、状态与非目标

### 验证入口

本地 Python 环境只使用 `uv`：

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
git diff --check
npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict
```

测试优先使用 fake Hermes、fake Milky transport、SSE fixture 和脱敏合成数据，覆盖协议与错误分类、
SSE 边界/重连/取消、friend/group/temp、canonical/dedup、Admission/Gate/Will/buffer、全部
segment 与 reply/forward、Hermes media helper、group/dm 出站与文件上传、MuteTracker 生命周期、
ToolSpec schema/显式调用/最小响应校验及日志脱敏。

真实 Milky 写入、上传、踢人、退群、删好友及好友请求操作必须获得用户明确授权。

### 当前状态与未决边界

当前未归档 change 有三项：`migrate-platform-hint-to-system-prompt`、
`add-split-outbound-delivery` 和 `deduplicate-inbound-image-media` 的实现与自动化证据已完成，
但尚未归档。
已有主规范继续覆盖入站 context/图片合并、出站附件/native media/文件上传、固定 QQ ToolSpec
和安全日志边界；当前工具清单为 25 项，完成项以各 change 的 `tasks.md` 和 evidence ledger
为准。未归档 delta 不代表其规划目标已经成为当前能力。
Hermes 扩展点、Milky Action 支持/错误 envelope，以及 25 个 ToolSpec 的 operationId、参数和
最小 response 结构，仍需与真实宿主、manifest、OpenSpec 和 Milky OpenAPI 持续对齐。

v0.1 不做：OneBot v11 入站协议/Action/echo/CQ 入站兼容、WebHook、WebSocket fallback、自动
forward 展开、任意 Action catalog、temp 会话、未经确认的跨场景回退，以及插件自有媒体缓存、
下载目录和 SSRF 规则副本。未知 segment、系统事件或失败 Action 不得伪装成普通消息、成功回复
或 Agent 指令；高风险状态变更不得由事件、正文、关键词或 Will 隐式触发；未确认 Hermes 扩展
点前不接管 Agent 队列、session store、媒体缓存或最终 turn 生命周期，也不把 fixture/OpenAPI
清单当作真实 Milky 生产能力证明。

## 13. 术语表

| 术语 | 含义 |
|---|---|
| directory plugin | Hermes 从插件目录发现并加载的插件 |
| Milky Action | `POST /api/{action}` 操作 |
| canonical / chat key | 规范化消息记录；`group:<id>` 或 `dm:<id>` 会话标识 |
| Gate / Will | 进入 Hermes 前的硬性门禁；决定 `wait` 或 `trigger` 的策略层 |
| wait/context buffer | 按 chat 隔离、有界、可丢失的待触发消息/系统事件缓存 |
| materialization | 将已确认资源变为 Hermes 或 Milky 可访问引用 |
| native segment | Milky wire protocol 的 typed segment，如 `image`、`record`、`video` |
| transport unknown / raw envelope | 无法确认远端结果；保留 `status`、`retcode`、`data` 和扩展字段的响应 |
| ToolSpec | Hermes Agent 可发现的固定工具 schema、handler 和调用边界 |
