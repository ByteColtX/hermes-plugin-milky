# hermes-plugin-milky

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)

Hermes 的 Milky QQ 平台适配器

`hermes-plugin-milky` 是 Hermes Gateway 的 Milky QQ platform directory plugin，通过
Milky v1.3 的 HTTP Action 和 SSE 事件流接入 Hermes。插件由仓库根目录的 `plugin.yaml` 和
`__init__.py::register(ctx)` 发现，不依赖 Python package entry point，也不修改 Hermes core。

详细的模块职责、生命周期和行为契约见 [ARCHITECTURE.md](ARCHITECTURE.md)；进行中的规范和
测试证据见 [openspec/changes/](openspec/changes/)。

<!-- omit in toc -->

## 目录

- [背景](#%E8%83%8C%E6%99%AF)
- [安装](#%E5%AE%89%E8%A3%85)
- [配置](#%E9%85%8D%E7%BD%AE)
- [API](#api)
- [维护者](#%E7%BB%B4%E6%8A%A4%E8%80%85)
- [致谢](#%E8%87%B4%E8%B0%A2)
- [贡献](#%E8%B4%A1%E7%8C%AE)
- [许可证](#%E8%AE%B8%E5%8F%AF%E8%AF%81)

## 背景

插件将 Milky 的 HTTP Action 和 SSE `GET /event` 适配到 Hermes platform adapter。运行时需要
Python 3.13+、Hermes Gateway、Milky v1.3 服务和 `httpx`。Hermes 继续负责 Agent 队列及
入站资源的下载、缓存和权限边界，插件只实现已声明的 Milky 适配能力。

## 安装

### 从 Hermes 安装

准备 Hermes Gateway 和可访问的 Milky 服务后，执行：

```bash
hermes plugins install ByteColtX/hermes-plugin-milky
```

启动前请按下方“配置”章节的示例设置环境变量，并确保启动 Hermes 的进程会加载
`~/.hermes/.env`。配置只在启动时读取一次，修改后重启 Gateway。

### 从源码设置开发环境

```bash
git clone https://github.com/ByteColtX/hermes-plugin-milky.git
cd hermes-plugin-milky
uv sync
```

## 配置

### Hermes Agent 推荐配置

下面的配置用于让群聊共享 Hermes session，在 Agent 忙碌时排队，并减少进度消息。请将需要的
字段合并到 `~/.hermes/config.yaml`，保留已有的其他配置：

```yaml
# 群友共享同一个 group:<群号> 会话
group_sessions_per_user: false

# 长任务跟进
agent:
  gateway_timeout: 1800
  gateway_auto_continue_freshness: 3600
  gateway_notify_interval: 180  # 每 3 分钟发一次“仍在处理”
  session_stall_timeout: 300    # 排队且无进展 5 分钟时提醒
  # 已确认主模型支持图片输入时，直接以内联图片交给主模型
  image_input_mode: native

# 自定义 provider 的模型不会总能从模型目录自动识别视觉能力。
# 请在已有 model 配置中保留其他字段，并追加 supports_vision: true。
model:
  supports_vision: true

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

# 推荐闲置 2 小时后重置，避免群聊上下文无限变旧
session_reset:
  mode: idle
  idle_minutes: 120
  notify: false
```

`group_sessions_per_user` 控制 Hermes 的 session 归属；`MILKY_SESSION_BUFFER_SIZE` 只控制
Will `wait` 阶段的插件侧历史消息。`busy_input_mode: queue` 让 Hermes 负责 queue、
follow-up、pending 和 interrupt/steer 语义，插件不复制 Agent 执行队列。平台显示覆盖应放在
`display.platforms.milky` 下，不要放到全局 `display` 下。

`image_input_mode: native` 与 `model.supports_vision: true` 只应配置在已确认支持
OpenAI-compatible `image_url` 输入的主模型上。前者选择原生图片路径，后者防止自定义模型被
误判为文本模型后逐张降级调用 `vision_analyze`。修改后重启 Gateway；日志应出现
`Image routing: native`，且不再出现 `Analyzing image`、`Processing image with vision model`
或 `Image analysis completed`。如果接口不支持原生图片输入，请移除这两项并使用文本视觉路径。

### Milky 插件配置

#### 环境变量

插件在启动时读取一次配置：

建议将环境变量集中保存到 `~/.hermes/.env`，并确保启动 Hermes 的进程会加载该文件：

```dotenv
MILKY_BASE_URL=http://127.0.0.1:3000
MILKY_ACCESS_TOKEN=<从安全凭证存储注入>
MILKY_ALLOWED_CHATS=group:123456789,dm:987654321
MILKY_SESSION_BUFFER_SIZE=20
MILKY_HOME_CHANNEL=group:123456789
# MILKY_WILL_POLICY=<JSON 字符串，见下方 Will policy>
```

上面的 QQ/群号仅为合成示例。`.env` 只应保存在本机或安全的部署环境中，不要提交到版本库；
`MILKY_WILL_POLICY` 的完整配置见下方 Will policy。

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `MILKY_BASE_URL` | 是 | Milky HTTP(S) 服务基址，保留 path prefix；Action 使用 `<base>/api/{action}`，SSE 使用 `<base>/event`。 |
| `MILKY_ACCESS_TOKEN` | 是 | Milky access token，只用于 Bearer header，不写入日志、异常或发送结果。 |
| `MILKY_ALLOWED_CHATS` | 否 | 逗号分隔的完整 chat key 白名单，例如 `group:123456789,dm:987654321`。 |
| `MILKY_WILL_POLICY` | 否 | JSON 格式的嵌套 Will policy，支持 `engine`、`routing`、`willingness` 和 `priority`。 |
| `MILKY_SESSION_BUFFER_SIZE` | 否 | 插件侧 Will `wait` 历史消息上限，默认 `20`；设为 `0` 禁用历史缓冲。 |
| `MILKY_HOME_CHANNEL` | 否 | Hermes 系统消息和 cron 的默认目标，只接受 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`。 |

chat key 只接受 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`；`temp` 会话不会回退到其他目标。

#### Will policy

`MILKY_WILL_POLICY` 必须使用嵌套 schema；`engine` 可选 `routing` 或 `willingness`，默认
engine 为 `routing`。动作值只能是 `wait` 或 `trigger`：

- `direct`、`mention`、`mentionAll`、`quote`、`poke` 控制对应信号；`mention` 只匹配
  `mention.user_id == self_id`，`quote` 只匹配 `reply.data.sender_id == self_id`，`poke` 只
  匹配协议明确确认 Bot 为接收者的 nudge；
- `allMessage` 对每条普通 friend/group 消息生效，默认 `wait`；
- `keywords` 是正文直接匹配的非空字符串数组，命中时确定性触发；空数组不产生命中；
- 图片没有独立 routing 动作，作为普通 segment 进入延迟媒体处理。

`friend_nudge` 和 `group_nudge` 始终是 observe-only。self-poke 可以作为 Will routing 信号，
但不会直接创建普通 `MessageEvent`、Agent turn、回复扣费或隐式 Action 调用。

完整默认示例：

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
  },
  "willingness": {
    "maxScore": 100,
    "initialScore": 0,
    "decayHalfLifeSeconds": 600,
    "probabilityThreshold": 55,
    "probabilityAmplifier": 0.04,
    "replyCost": 35,
    "textGain": 12,
    "mentionGain": 100,
    "quoteGain": 15,
    "directGain": 40,
    "imageGain": 8,
    "pokeGain": 80,
    "keywords": [],
    "keywordMultiplier": 1.2,
    "defaultMultiplier": 1,
    "hotWindowSeconds": 15,
    "warmWindowSeconds": 60,
    "hotDecayWeight": 0.3,
    "warmDecayWeight": 0.7,
    "mentionForce": false,
    "quoteForce": false,
    "directForce": false
  },
  "priority": 1000
}
```

旧的扁平群聊兜底字段、图片专用字段和 here 专用 routing 设置不会被静默转换；配置校验会在
建立网络连接前拒绝它们。字段约束以 [plugin.yaml](plugin.yaml) 和 active OpenSpec change
中的配置契约为准。

#### Home channel 与 cron

`MILKY_HOME_CHANNEL` 只影响 Hermes 系统消息和 cron 的默认出站目标，不参与入站 allowlist。
网关 live 投递复用已连接 adapter；`deliver=milky` 且没有显式目标的 cron 结果可使用该目标，
显式的 `milky:group:<id>` 或 `milky:dm:<id>` 目标优先。

未配置 home channel 时不会回退到 origin、默认频道、群聊或私聊，也不会猜测目标。standalone
cron 为每次投递创建并关闭临时 Milky client，目前只支持无附件文本；媒体和文件输入返回
`unsupported`。

## API

插件不是以 Python package entry point 发布；Hermes 从根目录加载 `plugin.yaml`，再调用以下
注册边界：

| 入口或对象 | 作用 |
| --- | --- |
| `__init__.py::register(ctx)` | 解析启动配置，注册 platform、`/milky`、17 个 ToolSpec 和 standalone 文本 sender；注册阶段不联网、不启动 SSE |
| `tools.py::register_tools(ctx)` | 将显式 ToolSpec 发现转发到 `outbound.tools`；不创建 client 或发起网络请求 |
| `MilkyAdapter` | 实现 Hermes `BasePlatformAdapter` 的连接、停止、入站交接和出站委托 |
| `MilkyOutboundSender` | 校验 `group:/dm:` 目标，格式化文本和 native segment，并调用 Milky Action/upload |
| `SlashCommandService` | 管理 adapter 生命周期内的唯一活动 client，处理无参数 `/milky` |

Agent 在普通回复中发送本地图片、语音、视频或文档时，应在最终回复中包含
`MEDIA:<local_path>`，例如 `MEDIA:~/path/to/clip.mp4`；显式调用 Hermes 内置的 `send_message`
时，则在其 `message` 中包含同一指令。Hermes 会按文件类型调用本插件的 `send_image_file`、
`send_voice`、`send_video` 或 `send_document`；其中图片、语音和视频使用 Milky native segment，
文档使用独立 file upload。`MEDIA:` 是通用发送入口，不属于下方 17 个显式 QQ ToolSpec；只有
发送入口返回失败时才应报告发送失败。

注册后，`connect()` 先完成 `get_login_info`、`get_group_list` 和每个群的 bot 成员状态同步，
再启动 SSE 并开放普通消息入口；`disconnect()` 会取消 event/pipeline/TTL 任务、解除
sender/command 绑定并关闭 HTTP/SSE 资源。

出站发送成功时使用远端 `data.message_seq` 的稳定字符串作为 `message_id`；协议拒绝、传输
未知、malformed 和 unsupported 会保持明确失败分类。

## 维护者

[ByteColtX](https://github.com/ByteColtX) 负责项目维护。问题、功能建议和安全联系入口见
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 致谢

感谢 Hermes Gateway 的 platform adapter contract、Milky v1.3 协议生态，以及提供协议
fixture、测试和文档改进的贡献者。

## 贡献

欢迎通过 [GitHub Issues](https://github.com/ByteColtX/hermes-plugin-milky/issues) 提问、报告
问题或提出建议，也欢迎提交 pull request。贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)
和 [ARCHITECTURE.md](ARCHITECTURE.md)。

贡献要求包括：

- 行为变化先补充脱敏契约或 fixture，再实现并增加回归测试；
- 使用 `uv` 管理 Python 环境和依赖，不使用 `pip`、`pipx` 或直接调用 `python`/`python3`；
- 遵循 Google Python Style Guide，并保持 milky、inbound、gates、will、session、state 和
  outbound 的依赖边界；
- 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和
  `git diff --check`；
- 不提交 token、Authorization header、真实 QQ/群 ID、真实媒体 URL/路径、文件内容或敏感
  正文；
- 使用 Conventional Commits，提交消息的 subject 和 body 均使用中文。

PR 被接受前应说明变更范围、实际执行的命令、测试结果和未解决风险。若行为契约发生变化，
请同步更新对应的 OpenSpec change；安全问题不要公开粘贴到 issue。

## 许可证

本项目使用 MIT License，版权所有 © 2026 ByteColtX。完整条款见 [LICENSE](LICENSE)。
