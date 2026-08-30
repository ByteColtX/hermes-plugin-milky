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

当前 manifest 仅声明三个显式 ToolSpec：`milky_profile_like`、`milky_nudge` 和
`milky_recall_group_message`。三者的参数校验、目标校验和错误分类已由出站边界统一处理；
`tools.py` 继续保持安全的发现边界。

### 当前实现状态

T01–T16 和 T18 的协议、canonical/dedup、Gate/Will、wait buffer、Hermes mapping、出站
和 adapter 生命周期已有自动化测试；T19 另有脱敏本地 HTTP/SSE 集成 fixture 和默认只读
Milky smoke。写入 smoke 必须显式使用 `--allow-write`，且目标必须命中运行时 allowlist。

home channel 的网关 live 投递和无附件 standalone 文本投递已接入 Hermes registry；没有
Hermes 安全附件 seam 的 standalone 媒体/文件、WebHook、WebSocket fallback、任意
Action catalog 和其他未声明能力仍保持 `unsupported`。

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

standalone cron 没有经过 Hermes 安全 materialization 的媒体/文件输入 seam 时会返回
`unsupported`，不会直传本地路径、下载 URL 或把 file 放入普通消息 segment。真实 Milky
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
