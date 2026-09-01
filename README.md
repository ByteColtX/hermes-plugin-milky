# hermes-plugin-milky

Hermes 的 Milky QQ platform directory plugin。Hermes 通过 GitHub 仓库目录发现插件，
不依赖 Python package entry point。

## 安装

```bash
hermes plugins install ByteColtX/hermes-plugin-milky
```

安装器读取仓库根目录的 `plugin.yaml`，并加载根目录
`__init__.py::register(ctx)`。`tools.py::register_tools(ctx)` 是显式 Agent 工具的发现
边界；Milky 适配器的协议、入站、出站和生命周期能力按 active OpenSpec change 的任务
顺序交付。当前 change 同时覆盖 home channel 的配置、Hermes registry、live 和 standalone
cron 出站边界。

## 入口布局

```text
plugin.yaml       # Hermes directory plugin manifest
__init__.py       # 唯一公开注册入口
tools.py          # 显式工具发现入口
adapter.py        # Milky platform adapter 生命周期薄层
```

本项目不使用 `hermes_plugin_milky/__init__.py`，也不声明 Hermes Python entry point；
`pyproject.toml` 仅用于 uv 开发环境和质量检查。

当前 manifest 声明九个与 Milky operationId 对齐的显式 ToolSpec：
`send_profile_like`、`send_friend_nudge`、`send_group_nudge`、`recall_group_message`、
`get_group_info`、`get_group_member_list`、`get_group_member_info`、
`set_group_member_mute` 和 `set_group_whole_mute`。它们的参数校验、目标校验和错误分类
由出站边界统一处理；`tools.py` 继续保持安全的发现边界。

### Hermes 斜杠命令

Milky 的纯文本斜杠命令在 canonical、TTL dedup 和 Gate 之后、Will 之前进入 Hermes
gateway control 通道。friend 使用 `dm:<QQ号>`，group 使用 `group:<群号>`；命令不进入
Will、wait buffer、资源补全或 Agent 普通正文。Hermes 继续拥有内置命令、未知命令、权限
和 Agent 忙碌时的分发语义，插件不复制命令队列。

当前唯一注册的插件命令是 `/milky`。无参数时，它通过已连接 adapter 所拥有的唯一
Milky client 调用 `get_impl_info`，成功回复直接使用完整原始 JSON envelope（包括未知扩展
字段），不添加说明或 Markdown 围栏。带参数、未连接、多个活动 client、rejected、
malformed、HTTP 或 transport unknown 结果均安全返回分类；不会临时创建 client，也不会
注册任意 Milky Action catalog。注册阶段不建立网络连接。

### 能力矩阵

| 能力 | 当前边界 | 失败或降级 |
| --- | --- | --- |
| Hermes 内置斜杠命令 | 交由 Hermes registry/dispatcher | 沿用 Hermes 既有结果 |
| `/milky` | 单一活动 adapter client 的只读 `get_impl_info` | `unsupported`、`rejected`、`malformed`、`http_error` 或 `transport_unknown` |
| 未知斜杠命令 | 交由 Hermes unknown-command 路径 | 不进入 Agent 普通正文 |
| 混合 segment、普通正文 | 继续普通 Will/Agent 路径 | 不扩大 gateway control |
| temp、系统和未知事件 | 沿用 observe-only 或 `ignored_temp` | 不创建命令或 Agent turn |
| 任意 Milky Action catalog | 不支持 | `unsupported` |

### 当前实现状态

T01–T16 和 T18 的协议、canonical/dedup、Gate/Will、wait buffer、Hermes mapping、出站
和 adapter 生命周期已有自动化测试；T19 另有脱敏本地 HTTP/SSE 集成 fixture 和默认只读
Milky smoke。写入 smoke 必须显式使用 `--allow-write`，且目标必须命中运行时 allowlist。

home channel 的网关 live 投递和无附件 standalone 文本投递已接入 Hermes registry；standalone
媒体/文件、WebHook、WebSocket fallback、任意 Action catalog 和其他未声明能力仍保持
`unsupported`。

### 入站上下文与系统事件

普通消息的当前正文和 wait 历史均使用单行尖括号 header，例如
`<sender uid 123 msg_id 7 reply_to 6> 正文`；缺失的 `msg_id` 或 `reply_to` 会省略。header
中的尖括号、反斜杠和换行，以及正文中的换行，都会被编码为字面量，避免伪造 context
记录。当前消息只进入本次正文，历史只进入 `channel_context`。

`face`、`image`、`record`、`video`、`file`、`forward`、`market_face`、`light_app` 和
`xml` 使用带类型的稳定 placeholder。`light_app` 只投影 JSON payload 的 `meta` 根对象，
递归保留其中的字段、数组和 `null`；缺少或 malformed `meta` 使用 `NOT SUPPORTED`。
image 在 trigger 阶段成功交给 Hermes image helper 后，placeholder 会改用 helper 返回路径的
basename，因此与实际落盘文件名一致；helper 失败时使用 `[img:NOT SUPPORTED]`。
`forward` 只展示 `[forward:<forward_id>]`，普通 trigger 不自动查询转发详情。
完整 inline `reply` 只通过 `reply_to` header 和 Hermes reply metadata 表达，不在正文追加
`[引用]`；reply 缺失或补全失败时使用 `[reply:NOT SUPPORTED]`。

`group_nudge`、`friend_nudge`、`group_member_increase` 和 `group_member_decrease` 是
context-only 事件：按 chat 保存到有界 FIFO，下一次同 chat trigger 时按 ingress 顺序注入
`channel_context` 一次，不创建 canonical、Will 或独立 Agent turn。其他系统事件仍为
observe-only；未确认的事件字段和能力继续安全降级。

### 模型可控 QQ 消息

普通 Agent 文本支持受限的 CQ-compatible 出站语法：

- `[CQ:at,qq=<uid>]` 转换为 Milky `mention` segment；
- `[CQ:reply,id=<msg_id>]` 转换为 Milky `reply` segment；
- 未确认映射、未知类型、参数错误或转换失败的 CQ 片段会原样作为 text fallback
  继续发送；fallback 不表示对应 QQ 语义已经执行；
- 默认不会自动 @ 用户或引用当前消息，Hermes 的隐式 `reply_to` 会被忽略。`uid` 和
  `msg_id` 只能复制当前消息或 `channel_context` 消息头中的真实值，不能从昵称或正文
  猜测。

需要 CQ `at`/`reply` 说明时，按需加载插件命名空间 skill：
`hermes-plugin-milky:qq-reference`；需要显式 QQ ToolSpec 的参数边界时，加载
`hermes-plugin-milky:qq-tools`。两个 skill 都是只读参考资料，不注册额外工具；实际
ToolSpec 和 Milky native conversion 才决定可执行能力。CQ-compatible 语法只存在于 Agent
出站适配层，不代表 OneBot 或 Milky 任意 Action 兼容。

### 多媒体出站

Milky adapter 已覆盖当前 Hermes `BasePlatformAdapter` 传入本地附件的 native 媒体交接：

| Hermes 入口 | Milky 出站边界 |
| --- | --- |
| 图片 URL、动画 | `image` segment，经 `send_group_message` 或 `send_private_message` |
| 图片/语音/视频 URI 或本地路径 | `image`、`record` 或 `video` segment，经 `send_group_message` 或 `send_private_message` |
| 文档 URI 或本地路径 | 先生成/校验 `file_uri`，再使用独立 `upload_group_file` 或 `upload_private_file` |
| `file://localhost`、`Path` | 与本地路径相同，常规、非空且不超过 8 MiB 时一次读取并生成 `base64://` |
| 远端 `file://` 或未知 scheme | 网络访问前返回 `invalid_input` 或 `unsupported` |

Hermes 负责从 Agent 输出中解析资源、管理入站媒体下载/缓存和路径权限；plugin 在 Milky
出站边界负责上述受限本地读取。合法 `http(s)://` 和显式 `base64://` URI 原样交给 Milky，
plugin 不下载远端 URI、不解码显式 Base64、不创建持久化媒体缓存，也不把本地路径改发为
文本。协议拒绝、传输结果未知、malformed 和未连接状态分别保持 `rejected`、
`transport_unknown`、`malformed` 和 `unsupported`，不会盲目重试。

这项边界是对 `61d99fc` 的重构修正：恢复 plugin 需要的本地读取和 `base64://` 编码，但不
修改 Hermes core，不建立第二套缓存、SSRF 或权限规则。附件失败时只返回安全分类，不发送
第二条用户可见告警文本或重试可能产生副作用的 Action。

## 配置指南

### Milky 插件环境变量

插件配置在启动时从环境变量读取。必填项如下：

| 变量 | 说明 |
| --- | --- |
| `MILKY_BASE_URL` | Milky HTTP 基址，例如 `http://127.0.0.1:3000`；保留已有 path prefix，Action 使用 `/api/{action}`，事件流使用 `/event`。 |
| `MILKY_ACCESS_TOKEN` | Milky access token；仅用于 `Authorization: Bearer <token>`，不要写入仓库、日志或错误信息。 |

可选项如下：

| 变量 | 说明 |
| --- | --- |
| `MILKY_ALLOWED_CHATS` | 逗号分隔的完整 chat key 白名单，例如 `group:123456789,dm:987654321`；为空时放行。 |
| `MILKY_WILL_POLICY` | JSON 格式的嵌套 Will policy，支持 `engine`、`routing`、`willingness` 和 `priority`。 |
| `MILKY_SESSION_BUFFER_SIZE` | Will 等待消息的插件侧历史缓冲上限，默认 `20`；设为 `0` 禁用历史缓冲。 |
| `MILKY_HOME_CHANNEL` | 可选的系统/cron 默认投递目标，只接受完整 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`；未设置时不创建默认目标。 |

### Will routing schema 与迁移

`MILKY_WILL_POLICY.routing` 支持 `direct`、`mention`、`mentionAll`、`quote`、`poke`、
`allMessage` 和 `keywords`。动作值只能是 `wait` 或 `trigger`；`allMessage` 对每条普通
friend/group 消息生效，默认是 `wait`。`keywords` 是非空字符串数组，正文直接包含任意
关键词时确定性触发；空数组不产生关键词命中。图片仍按普通 segment 进入延迟媒体处理，
不再拥有独立 routing 动作。

```json
{
  "engine": "routing",
  "routing": {
    "direct": "trigger",
    "mention": "trigger",
    "mentionAll": "wait",
    "quote": "wait",
    "poke": "wait",
    "allMessage": "wait",
    "keywords": []
  }
}
```

这是一次 breaking schema 迁移：将旧的群聊兜底设置改为 `allMessage`，移除图片和 here
专用 routing 设置，再按需填写关键词。旧字段会在启动配置校验阶段拒绝，不会建立网络
连接或静默转换为新规则；未确认的 here 信号仍只保留在底层安全扩展边界。

例如，在启动 Hermes 前注入连接配置：

```bash
export MILKY_BASE_URL="http://127.0.0.1:3000"
export MILKY_ACCESS_TOKEN="<从安全凭证存储注入>"
export MILKY_ALLOWED_CHATS="group:123456789,dm:987654321"
export MILKY_HOME_CHANNEL="group:123456789"
hermes
```

`MILKY_ALLOWED_CHATS` 只接受 `group:<十进制群号>` 和 `dm:<十进制 QQ 号>`。临时会话
不会回退到群聊或私聊目标。完整 Will policy 的默认值和字段约束以
`plugin.yaml` 及 `openspec/changes/` 中的配置契约为准；不要使用旧的 allowed groups、
allowed users、muted groups、require mention 或扁平 dm policy 配置名。

`MILKY_HOME_CHANNEL` 只在启动时解析一次，并且不参与入站 allowlist、Gate 或 Will。
Hermes 网关启动/重启通知、系统告警以及 `deliver=milky` 且没有显式目标的 cron 结果
会投递到该目标；显式的 `milky:group:<id>` 或 `milky:dm:<id>` 目标优先。未配置 home
channel 时不会猜测目标或回退到 origin、默认频道、群聊或私聊。网关 live 投递复用已连接
adapter；独立 cron 为单次文本投递创建并关闭临时 Milky client，返回远端 `message_seq`
对应的稳定消息 ID。

standalone cron 当前只支持文本；媒体/文件输入会返回 `unsupported`，不会直传本地路径、
下载 URL 或把 file 放入普通消息 segment。真实 Milky
写入 smoke 仍必须使用运行时注入的凭证，并在执行前取得明确授权；本文示例中的目标仅为
合成占位。

### Hermes Agent 推荐配置

群聊共享会话不是插件环境变量。要让群友共享同一个 `group:<群号>` Hermes 会话，请在
`~/.hermes/config.yaml` 顶层合并以下配置；已有配置文件应保留其他未列出的设置：

```yaml
# 群友共享同一个 group:<群号> 会话
group_sessions_per_user: false

# 长任务跟进
agent:
  gateway_timeout: 1800
  gateway_auto_continue_freshness: 3600
  gateway_notify_interval: 180  # 每 3 分钟发一次“仍在处理”
  session_stall_timeout: 300    # 排队且无进展 5 分钟时提醒

# 关闭自动建议创建 Skill
skills:
  creation_nudge_interval: 0

# 群聊消息不要打断当前任务，排队处理
display:
  busy_input_mode: queue
  busy_ack_enabled: false
  tool_progress_command: false
  background_process_notifications: result
  memory_notifications: off
  platforms:
    milky:
      thinking_progress: off       # 关闭“思考中”状态
      tool_progress: off           # 关闭工具进度
      interim_assistant_messages: false
      long_running_notifications: false  # 可选：关闭“仍在处理”心跳
      show_reasoning: false        # 关闭最终回复中的思考摘要
      streaming: false             # 关闭本插件会话的流式输出
      busy_ack_detail: false       # 隐藏忙碌提示中的迭代/工具详情
      busy_steer_ack_enabled: false
      live_status: off             # 关闭支持状态文本时的实时状态

# 关闭后台自动复盘、自动写入记忆/Skill
auxiliary:
  background_review:
    enabled: false

# /goal 的最大自动续行轮数
goals:
  max_turns: 20

# 推荐闲置一天后重置，避免群聊上下文无限变旧
session_reset:
  mode: idle
  idle_minutes: 1440
  notify: false
```

修改 Hermes 配置后按其部署方式重启 Gateway，使新设置生效。`group_sessions_per_user`
控制 Hermes 的会话归属，插件自身的 `MILKY_SESSION_BUFFER_SIZE` 只控制 Will wait
阶段的有界历史消息，两者不是同一个缓冲区。`thinking_progress`、`tool_progress`、
`interim_assistant_messages` 和 `long_running_notifications` 是 Hermes 的按平台显示覆盖，
应放在 `display.platforms.milky` 下，不是插件环境变量，也不要放在全局 `display` 下。
同样可以按需在该节点配置 `tool_progress_grouping`、`tool_preview_length`、
`reasoning_style` 和 `cleanup_progress`；其中 `cleanup_progress` 只有适配器支持删除消息时
才会生效。`streaming` 的插件局部设置仍受 Hermes 顶层 `streaming` 总开关约束。
