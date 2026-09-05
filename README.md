# hermes-plugin-milky

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)

Hermes 的 Milky QQ 平台适配器

让 Hermes 进入 QQ 私聊和群聊，成为一个会判断何时回应的 AI 参与者：

- 接收消息，并识别提及、引用、图片等上下文；
- 根据会话状态判断何时回应、何时保持沉默；
- 发送文本、@、引用、图片、语音、视频和文件；
- 提供群组、成员、文件和好友/入群请求等 QQ 能力。

> [!WARNING]
> **当前有两类权限隔离尚未完成：**
>
> - **Slash command：** 没有独立的发送者门禁。白名单会话中的任意成员都可能触发 Hermes
>   内置命令或插件命令。
> - **ToolSpec：** 25 个 QQ 工具没有独立的调用者和目标授权。模型、其他会话或 cron
>   可能查询无关群/好友，或执行禁言、踢人、撤回、退群、删好友、接受/拒绝请求等操作。
>
> **最低限度的安全配置：**
>
> - `MILKY_ALLOWED_CHATS` 只填写你能控制、成员可信且用途明确的会话；
> - 不要加入公开群、成员可随意加入的群或不受控私聊；
> - 记住：该配置只限制入站会话，**不等于** ToolSpec 或通用出站 sender 的授权；
> - 留空表示允许所有会话进入。
>
> 示例：
>
> ```dotenv
> MILKY_ALLOWED_CHATS=group:123456789,dm:987654321
> ```
>
> 示例中的 ID 仅为占位值。

详细的模块职责、生命周期和行为契约见 [ARCHITECTURE.md](ARCHITECTURE.md)；进行中的规范和
测试证据见 [openspec/changes/](openspec/changes/)。

<!-- omit in toc -->

## 目录

- [核心能力](#%E6%A0%B8%E5%BF%83%E8%83%BD%E5%8A%9B)
- [安装](#%E5%AE%89%E8%A3%85)
- [配置](#%E9%85%8D%E7%BD%AE)
- [功能与使用](#%E5%8A%9F%E8%83%BD%E4%B8%8E%E4%BD%BF%E7%94%A8)
- [API 与开发](#api-%E4%B8%8E%E5%BC%80%E5%8F%91)
- [贡献](#%E8%B4%A1%E7%8C%AE)
- [维护者、致谢与许可证](#%E7%BB%B4%E6%8A%A4%E8%80%85%E8%87%B4%E8%B0%A2%E4%B8%8E%E8%AE%B8%E5%8F%AF%E8%AF%81)

## 核心能力

插件适合希望把 Hermes 放进 QQ 私聊和群聊的场景：

- **自然参与：** 根据提及、引用、关键词和会话状态，决定回应还是保持沉默；
- **多媒体消息：** 接收图片等上下文，并发送文本、@、引用、图片、语音、视频和文件；
- **QQ 信息能力：** 查询群组、成员、文件和好友/入群请求，并提供部分 QQ 操作；
- **会话安全边界：** 支持 chat 白名单、禁言状态同步、消息去重和有界历史缓冲。

运行环境：Python 3.13+、Hermes Gateway、Milky v1.3 服务和 `httpx`。Hermes 负责 Agent
队列及入站资源的下载、缓存和权限边界；本插件负责 Milky 适配和已声明的 QQ 能力。

## 安装

### 从 Hermes 安装

```bash
hermes plugins install ByteColtX/hermes-plugin-milky
```

### 从源码设置开发环境

```bash
git clone https://github.com/ByteColtX/hermes-plugin-milky.git
cd hermes-plugin-milky
uv sync
```

> [!IMPORTANT]
> 启动前先完成下方的 Milky 配置，并确保启动 Hermes 的进程会加载 `~/.hermes/.env`。
> 配置只在启动时读取；修改后需要重启 Gateway。

## 配置

### Milky 最小配置

建议将环境变量集中保存到 `~/.hermes/.env`：

```dotenv
MILKY_BASE_URL=http://127.0.0.1:3000
MILKY_ACCESS_TOKEN=<从安全凭证存储注入>
MILKY_ALLOWED_CHATS=group:123456789,dm:987654321
MILKY_SESSION_BUFFER_SIZE=20
MILKY_HOME_CHANNEL=group:123456789
# MILKY_MAX_LOCAL_MEDIA_BYTES=33554432
# MILKY_WILL_POLICY=<JSON 字符串，见下方 Will policy>
```

上面的 QQ/群号仅为合成示例。`.env` 只应保存在本机或安全的部署环境中，不要提交到版本库。

| 变量 | 必需 | 作用 |
| --- | --- | --- |
| `MILKY_BASE_URL` | 是 | Milky 服务基址；Action 使用 `<base>/api/{action}`，事件流使用 `<base>/event`。远程部署请使用 HTTPS。 |
| `MILKY_ACCESS_TOKEN` | 是 | Milky access token，只用于 Bearer 认证。 |
| `MILKY_ALLOWED_CHATS` | 否 | 入站 chat key 白名单，例如 `group:123456789,dm:987654321`；留空表示允许所有会话进入。 |
| `MILKY_WILL_POLICY` | 否 | 决定消息等待（`wait`）或触发（`trigger`）的嵌套 JSON 配置。 |
| `MILKY_SESSION_BUFFER_SIZE` | 否 | `wait` 历史消息上限，默认 `20`；设为 `0` 可关闭历史缓冲。 |
| `MILKY_HOME_CHANNEL` | 否 | 系统消息和 cron 的默认目标；不参与入站白名单。 |
| `MILKY_MAX_LOCAL_MEDIA_BYTES` | 否 | 出站本地资源原始字节数上限，默认 `33554432`（`32 MiB`），合法范围 `8388608`（`8 MiB`）至 `33554432`（`32 MiB`）。 |

chat key 只接受 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`；`temp` 会话不会回退到其他目标。

### Hermes Agent 推荐配置

下面的配置让群聊共享 session、在 Agent 忙碌时排队，并减少进度消息。请合并到
`~/.hermes/config.yaml`，保留已有的其他配置：

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

`group_sessions_per_user: false` 会让群友共享同一个 Hermes session；这适合群聊，但也意味着
群内消息会共同影响上下文。`busy_input_mode: queue` 让 Hermes 负责 queue、follow-up、
pending 和 interrupt/steer，插件不复制 Agent 执行队列。

> [!TIP]
> 平台显示设置必须放在 `display.platforms.milky` 下，不要放到全局 `display` 下。

`image_input_mode: native` 与 `model.supports_vision: true` 只应配置在已确认支持
OpenAI-compatible `image_url` 输入的主模型上。如果接口不支持原生图片输入，请移除这两项并
使用文本视觉路径。修改后重启 Gateway；日志应出现 `Image routing: native`。

### 记忆后端

建议使用 Hermes 的 `holographic` 记忆后端：

```bash
hermes config set memory.provider holographic
```

它适合本地部署：数据保存在本地，不依赖付费云服务，并支持围绕实体召回长期上下文。修改后
重启 Gateway 使配置生效。

### Will policy

Will 决定一条消息是先等待，还是交给 Hermes：

- `wait`：放入当前 chat 的有界缓冲，暂不启动 Agent；
- `trigger`：先取出该 chat 的等待历史，再把当前消息交给 Hermes。

`MILKY_WILL_POLICY.engine` 只选择一套引擎。`routing` 和 `willingness` 共用消息特征、都输出
`wait`/`trigger`，但**不会叠加运行**。

| 引擎 | 决策方式 | 适合场景 |
| --- | --- | --- |
| `routing`（默认） | 当前消息命中规则就触发，结果确定 | 希望行为可预测、方便排查 |
| `willingness` | 按 chat 维护分数，再按概率抽样 | 希望机器人偶尔参与、减少刷屏 |

#### routing：确定性规则

`routing` 只看当前消息：不维护分数、不使用随机数。`direct` 等规则字段的值只能是 `wait` 或
`trigger`；`keywords` 不填写动作，命中时固定为 `trigger`。

| 字段 | 命中条件 | 默认行为 |
| --- | --- | --- |
| `direct` | friend 私聊 | `trigger` |
| `mention` | 直接 @Bot（只认 `mention.user_id == self_id`） | `trigger` |
| `mentionAll` | @全体成员 | `wait` |
| `quote` | 回复 Bot 的消息（只认 `reply.data.sender_id == self_id`） | `wait` |
| `poke` | 协议明确指向 Bot 的 poke | `wait` |
| `allMessage` | 每条普通 friend/group 消息 | `wait` |
| `keywords` | 正文包含任意一个非空关键词 | 空数组（不命中） |

一条消息可以同时命中多条规则；结果按 OR 合并，**任一规则为 `trigger` 就触发**，不会被其他
`wait` 抵消。图片没有独立 routing 规则，单独出现时仍由 `allMessage` 决定；
`friend_nudge` 和 `group_nudge` 在普通消息流程中保持 observe-only。

示例：只有私聊、@Bot 或包含“提醒”的消息进入 Hermes，其余消息等待：

```json
{
  "engine": "routing",
  "routing": {
    "allMessage": "wait",
    "direct": "trigger",
    "mention": "trigger",
    "keywords": ["提醒"]
  }
}
```

#### willingness：分数 + 概率

`willingness` 不把每个信号直接设成 `wait`/`trigger`，而是为每个 chat 单独维护一个分数。
普通消息大致经过以下步骤：

1. 先让分数按静默时间衰减；
2. 根据文本、提及、reply、图片、私聊等特征增加分数；
3. 命中 `willingness.keywords` 时提高本次增益倍率；
4. 分数超过 `probabilityThreshold` 后换算成概率并抽样，得到 `wait` 或 `trigger`。

因此，同一条消息可能因为当前分数或随机抽样不同而得到不同结果。`willingness.keywords` 是
**加分倍率，不是确定性触发器**。

`directForce`、`mentionForce`、`quoteForce` 可让对应信号跳过随机抽样，直接 `trigger`。
这里的 `quoteGain`/`quoteForce` 只看是否存在 reply，不要求 reply 指向 Bot；这与 routing 的
`quote` 规则不同。显式 self-poke 使用 `pokeGain`，`friend_nudge` 和 `group_nudge` 仍是
observe-only，不会直接创建 Agent turn。只有 Hermes 接受该次 trigger 后才扣除 `replyCost`；
等待、Gate 拒绝和命令不会扣费。

示例：默认按概率参与，但命中“提醒”时提高增益；私聊和 @Bot 仍不强制触发：

```json
{
  "engine": "willingness",
  "willingness": {
    "keywords": ["提醒"],
    "keywordMultiplier": 1.2,
    "directForce": false,
    "mentionForce": false,
    "quoteForce": false
  }
}
```

#### 配置提示

- 不确定时使用默认的 `routing`；它最容易预测和调试；
- 想切换到概率决策时，将 `engine` 改为 `willingness`，并配置 `willingness` 对象；
- 完整配置可以同时保留两套参数，但运行时只使用 `engine` 选中的一套；
- `priority` 当前只保留在配置 schema 中，不参与 routing 优先级或 willingness 权重计算；
- 旧的扁平字段、`routing.group`、`routing.image` 和 `routing.mentionHere` 不会被静默转换，
  启动时会直接拒绝。

完整默认配置示例（包含两套引擎参数，默认折叠）：

<details>
<summary>展开完整默认配置</summary>

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

</details>

未列出的字段使用插件默认值。配置写入 `MILKY_WILL_POLICY` 时必须是 JSON 字符串。

### Home channel 与 cron

`MILKY_HOME_CHANNEL` 只影响 Hermes 系统消息和 cron 的默认出站目标，不参与入站 allowlist。
显式的 `milky:group:<id>` 或 `milky:dm:<id>` 目标优先。

未配置 home channel 时不会回退到 origin、默认频道、群聊或私聊，也不会猜测目标。standalone
cron 每次创建并关闭临时 Milky client，目前只支持无附件文本；媒体和文件输入返回
`unsupported`。

## 功能与使用

### 消息与媒体

普通入站只处理 `message_receive`：

- friend 和 group 消息进入普通 Agent 流程；
- `temp` 会话直接忽略；
- Milky SSE `GET /event` 中的 `message_recall`、request、notice、lifecycle 和未知事件默认只观察，少数系统事件可作为上下文；
- `face` segment 的正文占位符对非 `emoji 表情` pack 优先使用随插件发布的本地 catalog 名称；未命中、冲突或目录不可用时回退原 `face_id`，缺失 ID 时使用 `NOT SUPPORTED`；
- 同一 chat 按顺序处理，`wait` 消息进入有界历史，`trigger` 时再交给 Hermes。

`message_recall` 的上下文行为如下：

- 只有字段完整且 `message_scene` 为 `friend` 或 `group` 时才登记；friend 写入 `dm:<peer_id>`，group 写入 `group:<peer_id>`，非法场景或 ID 只记录安全诊断；
- 合法事件进入对应 chat 的有界 system context FIFO，在下一次同 chat `trigger` 的 `channel_context` 中按 ingress 顺序出现一次，格式为 `<event message_recall> ...`；
- 无 `operator_id` 或 `operator_id == sender_id` 时显示 `uid <sender_id> 撤回了消息 msg_seq <message_seq>`；群聊仅在 `operator_id != sender_id` 时显示 `管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`，好友有不同操作人时不添加管理员角色；
- 撤回事件不创建普通 Agent turn、不发送回复、不调用主动撤回工具，也不调用 `get_message` 或下载资源；插件只展示撤回元数据，不承诺恢复被撤回消息正文；
- 该路径仍是 observe-only，不经过普通消息的 Gate/Will，也不扣 reply cost。fixture 和 fake host 测试不代表真实 Milky 服务端能力已被集成验证。

Agent 发送本地媒体时，在回复中写入：

```text
MEDIA:<local_path>
```

例如 `MEDIA:~/path/to/clip.mp4`。显式调用 Hermes `send_message` 时，把同一指令放在
`message` 参数中。图片、语音和视频使用 Milky native segment，文档使用独立 file upload。

如果无需回复，只返回 `[SILENT]`，不附加其他内容；该标记由 Hermes core 抑制消息投递，Milky
plugin 不单独解析它。

需要模拟自然聊天节奏时，可把区分大小写的 `[SPLIT]` 单独放在一行。标记行会被删除，空段不
发送，文本按原顺序最多发送三条；超过三段时尾部合并到第三段。每个文本单元仍遵守既有长度
边界，若实际文本消息会超过三条，则在网络访问前整体拒绝。普通长文本没有有效 `[SPLIT]` 时
继续使用原有长度分块。

回复同时包含文本分段和 `MEDIA:` 附件时，Hermes 先投递全部文本，再按提取顺序投递图片、语音、
视频和文档；当前不支持文本段与附件交错，`[SPLIT]` 不改变 `MEDIA:` 的独立交接。

> [!CAUTION]
> `MEDIA:` 会读取本地文件并上传；默认只限制常规、非空且不超过 `33554432` 字节（`32 MiB`）
> 的文件，可用 `MILKY_MAX_LOCAL_MEDIA_BYTES` 在 `8388608` 至 `33554432` 字节之间调整，
> 没有固定的安全目录隔离。Base64 编码会带来约 `4/3` 的请求体放大；内网连接不代表
> Milky、代理或下游平台没有更低的服务端限制。

CQ image 仅用于本地 `file://` URI 的 sticker，例如：

```text
[CQ:image,file=file:///path/to/sticker.ext,type=sticker]
```

普通图片请使用 `MEDIA:<local_path>`。sticker 会在发送前转换为 `base64://`。

本地路径、`Path` 和 `file://localhost` 只在 plugin 边界读取一次并受上述本地字节上限约束；
格式合法的 `http(s)://` 和显式 `base64://` 会原样传递，plugin 不下载、读取或解码，也不应用
本地文件大小检查。

### Slash command

纯文本 `/...` 消息会在 canonical、去重和 Gate 之后分流，不进入 Will 历史或普通 Agent 正文。
合法命令交给 Hermes 既有命令分发；插件自身提供无参数 `/milky`，用于以可读摘要返回 Milky 实现信息。

### QQ ToolSpec

插件固定提供 25 个 QQ ToolSpec，覆盖：

- 群组和成员查询；
- 文件、转发消息和私聊文件链接查询；
- 戳一戳、点赞、撤回、禁言、踢人、退群和删好友；
- 好友请求、入群请求和群邀请的接受/拒绝。

请求/邀请的接受和拒绝不会由通知、普通正文、关键词或 Will 自动触发，必须由 Agent 显式提供
完整参数。未知执行结果返回 `transport_unknown`，不自动重试或更新本地状态。

入站文件只显示为安全占位符，例如
`[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]`；它不会被当作本地路径
或出站文件。

### 连接与生命周期

连接时依次完成登录信息、群列表和每个群的 Bot 成员状态同步，之后才启动事件流并开放普通
消息入口。断开时会取消 event、pipeline、TTL 任务，解除 sender/command 绑定，并关闭
HTTP/SSE 资源。

出站成功使用远端 `data.message_seq` 的稳定字符串作为 `message_id`；协议拒绝、传输未知、
malformed 和 unsupported 会保持明确失败分类。缺少消息序号时不会伪造稳定去重 ID。

## API 与开发

插件不是以 Python package entry point 发布；Hermes 从根目录加载 `plugin.yaml`，再调用唯一
公开入口 `__init__.py::register(ctx)`。

| 对象 | 作用 |
| --- | --- |
| `__init__.py::register(ctx)` | 解析启动配置，注册 platform、`/milky`、ToolSpec、standalone sender 和 QQ 指引 section。 |
| `__init__.py::register_tools(ctx)` | 委托 `outbound.tools` 注册固定 ToolSpec；注册阶段不联网。 |
| `MilkyAdapter` | 管理连接、停止、入站交接和出站委托。 |
| `MilkyOutboundSender` | 校验 `group:/dm:` 目标，格式化消息并调用 Milky Action/upload。 |
| `SlashCommandService` | 管理活动 Milky client，处理 `/milky`。 |

支持 `register_system_prompt_section` 的 Hermes 宿主会在 `after_memory` 登记
`hermes-plugin-milky.qq-platform-guidance`，并在连接完成后使用已确认的 QQ UID 和昵称渲染
媒体、CQ-compatible、无回复和 bundled skill 指引。旧宿主仍可完成平台注册，但只获得首句提示。

详细的稳定模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)；可观察行为、测试要求和进行中的
规范见 [openspec/changes/](openspec/changes/)。

## 贡献

欢迎通过 [GitHub Issues](https://github.com/ByteColtX/hermes-plugin-milky/issues) 提问、报告
问题或提交 pull request。贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和
[ARCHITECTURE.md](ARCHITECTURE.md)。

贡献要求：

- 行为变化先补充脱敏契约或 fixture，再实现并增加回归测试；
- 使用 `uv` 管理 Python 环境和依赖，不使用 `pip`、`pipx` 或直接调用 `python`/`python3`；
- 遵循 Google Python Style Guide，并保持各模块依赖边界；
- 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和
  `git diff --check`；
- 不提交 token、Authorization header、真实 QQ/群 ID、真实媒体 URL/路径、文件内容或敏感正文；
- 使用中文 Conventional Commits。

PR 应说明变更范围、实际执行的命令、测试结果和未解决风险。若行为契约发生变化，请同步
更新对应的 OpenSpec change；安全问题不要公开粘贴到 issue。

## 维护者、致谢与许可证

维护者：[ByteColtX](https://github.com/ByteColtX)。问题、功能建议和安全联系入口见
[CONTRIBUTING.md](CONTRIBUTING.md)。

感谢 Hermes Gateway 的 platform adapter contract、Milky v1.3 协议生态，以及提供协议
fixture、测试和文档改进的贡献者。

本项目使用 MIT License，版权所有 © 2026 ByteColtX。完整条款见 [LICENSE](LICENSE)。
