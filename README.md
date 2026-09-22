# hermes-plugin-milky

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)

Hermes 的 Milky QQ 平台适配器

让 Hermes 进入 QQ 私聊和群聊，成为一个会判断何时回应的 AI 参与者：

- 接收消息，并识别提及、引用、图片等上下文；
- 根据会话状态判断何时回应、何时保持沉默；
- 发送文本、@、引用、图片、语音、视频和文件；
- 提供群组、成员、文件和好友/入群请求等 QQ 能力。

> [!WARNING]
> **当前仍有一类权限隔离尚未完成：**
>
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
>
> 允许使用 `dm:*` 放行所有私聊，或使用 `group:*` 放行所有群聊；通配符只匹配对应的
> `dm:`/`group:` 命名空间，也可以和具体 chat key 混用。

详细的模块职责、生命周期和行为契约见 [ARCHITECTURE.md](ARCHITECTURE.md)；主规范、未归档
change 和已归档 change 的测试证据见 [openspec/](openspec/)。

<!-- omit in toc -->

## 目录

- [核心能力](#%E6%A0%B8%E5%BF%83%E8%83%BD%E5%8A%9B)
- [安装](#%E5%AE%89%E8%A3%85)
- [配置](#%E9%85%8D%E7%BD%AE)
- [日志](#%E6%97%A5%E5%BF%97)
- [常用运维](#%E5%B8%B8%E7%94%A8%E8%BF%90%E7%BB%B4)
- [功能与使用](#%E5%8A%9F%E8%83%BD%E4%B8%8E%E4%BD%BF%E7%94%A8)
- [API 与开发](#api-%E4%B8%8E%E5%BC%80%E5%8F%91)
- [贡献](#%E8%B4%A1%E7%8C%AE)
- [维护者、致谢与许可证](#%E7%BB%B4%E6%8A%A4%E8%80%85%E8%87%B4%E8%B0%A2%E4%B8%8E%E8%AE%B8%E5%8F%AF%E8%AF%81)

## 核心能力

插件适合希望把 Hermes 放进 QQ 私聊和群聊的场景：

- **自然参与：** 根据提及、引用、关键词和会话状态，决定回应还是保持沉默；
- **多媒体消息：** 接收图片等上下文，并发送文本、@、引用、图片、语音、视频和文件；当前语音
  交给 Hermes core 的 STT 流程，插件不负责 provider 适配或音频格式转换；
- **QQ 信息能力：** 查询群组、成员、文件和好友/入群请求，并提供部分 QQ 操作；
- **会话安全边界：** 支持 chat 白名单、禁言状态同步、消息去重和有界历史缓冲。
- **QQ 会话介绍：** 在支持 system prompt section 的 Hermes 宿主中，首次 Milky friend/group
  session prompt 可看到当前会话的最小资料；介绍来自入站消息快照，不实时查询 Milky。
- **人工贴纸维护：** 通过显式 `/milky sticker` 命令维护插件持久目录中的图片库；普通消息、入站图片、
  关键词、Will 和 Agent 输出不会自动收集贴纸。
- **Agent 贴纸发送：** 插件运行时依赖 `jieba` 且库中存在可用条目时，`sticker_send` 依据当前 Milky 会话和意图发送一张贴纸；
  Agent 不能指定目标、贴纸 ID、路径或 URL。

运行环境：Python 3.13+、Hermes Gateway、Milky v1.3 服务以及插件声明的 `httpx`、Pillow、`jieba`。
Hermes 负责 Agent
队列及入站资源的下载、缓存和权限边界；本插件负责 Milky 适配和已声明的 QQ 能力。

## 安装

### 从 Hermes 安装

```bash
hermes plugins install ByteColtX/hermes-plugin-milky --enable
```

`--enable` 会在安装成功后直接启用插件并跳过确认提示。首次安装完成后，可以用下面的命令确认
插件状态：

```bash
hermes plugins list
```

如果 `hermes-plugin-milky` 显示为 disabled，启用插件：

```bash
hermes plugins enable hermes-plugin-milky
```

插件启用后，按[配置](#%E9%85%8D%E7%BD%AE)完成 Milky 服务地址、access token 和可选白名单配置，
然后重启 Gateway：

```bash
hermes gateway restart
```

已有安装需要拉取新版本时，执行：

```bash
hermes plugins update hermes-plugin-milky
hermes gateway restart
```

更新插件代码或配置后都需要重启 Gateway，运行中的进程不会自动加载新的插件代码。

### 从源码设置开发环境

```bash
git clone https://github.com/ByteColtX/hermes-plugin-milky.git
cd hermes-plugin-milky
uv sync
```

源码安装适合开发和调试。拉取新代码后重新同步环境，并重启 Gateway：

```bash
git pull
uv sync
hermes gateway restart
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
# MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS=false
# MILKY_WILL_POLICY=<JSON 字符串，见下方 Will policy>
```

上面的 QQ/群号仅为合成示例。`.env` 只应保存在本机或安全的部署环境中，不要提交到版本库。

| 变量 | 必需 | 作用 |
| --- | --- | --- |
| `MILKY_BASE_URL` | 是 | Milky 服务基址；Action 使用 `<base>/api/{action}`，事件流使用 `<base>/event`。远程部署请使用 HTTPS。 |
| `MILKY_ACCESS_TOKEN` | 是 | Milky access token，只用于 Bearer 认证。 |
| `MILKY_ALLOWED_CHATS` | 否 | 入站 chat key 白名单，支持具体 `group:<群号>`/`dm:<QQ号>` 以及 `group:*`/`dm:*`；通配符只匹配对应命名空间，可混用；留空表示允许所有会话进入。 |
| `MILKY_WILL_POLICY` | 否 | 决定消息等待（`wait`）或触发（`trigger`）的嵌套 JSON 配置。 |
| `MILKY_SESSION_BUFFER_SIZE` | 否 | `wait` 历史消息上限，默认 `20`；设为 `0` 可关闭历史缓冲。 |
| `MILKY_HOME_CHANNEL` | 否 | 系统消息和 cron 的默认目标；不参与入站白名单。 |
| `MILKY_MAX_LOCAL_MEDIA_BYTES` | 否 | 出站本地资源原始字节数上限，默认 `33554432`（`32 MiB`），合法范围 `8388608`（`8 MiB`）至 `33554432`（`32 MiB`）。 |
| `MILKY_LONG_TEXT_FORWARD_THRESHOLD` | 否 | 超长文本合并转发阈值，默认 `0`（关闭）；只接受 `0..4096` 的十进制整数，只有可见规范化文本长度严格大于正值时才选择一个 `forward`。 |
| `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` | 否 | 群成员入退群即时通知，默认 `false`；只接受大小写不敏感的 `true`/`false`，只在启动时读取。开启后追加固定英文 Tip，并在 Hermes 已确认或持久化恢复的 session key 且接受注入时立即触发 Agent turn。 |

消息 chat key 只接受 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`；白名单另支持完整的
`group:*` 和 `dm:*` 规则，`temp` 会话不会回退到其他目标。

### Hermes Agent 推荐配置

下面的配置让群聊共享 session、在 Agent 忙碌时排队，并减少进度消息。请合并到
`~/.hermes/config.yaml`，保留已有的其他配置：

启用 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS=true` 时，还必须保留下面的
`plugins.entries.hermes-plugin-milky.allow_gateway_injection: true`；这是允许成员事件通过
已有 Gateway session 触发 Agent turn 的插件级授权。

```yaml
# 群友共享同一个 group:<群号> 会话
group_sessions_per_user: false

# 显式指定时区
timezone: Asia/Shanghai

# 长任务跟进与卡住自恢复
agent:
  gateway_timeout: 360          # 无 Agent 活动 6 分钟后终止当前 turn
  gateway_timeout_warning: 120  # 超时前 2 分钟发出提醒
  gateway_auto_continue_freshness: 3600
  gateway_notify_interval: 180  # 每 3 分钟发一次“仍在处理”
  session_stall_timeout: 120    # 有排队消息且无进展 2 分钟时提醒
  local_stream_stale_timeout: 180  # 本地 provider 无实际流内容 3 分钟后重连
  api_max_retries: 1            # 减少卡住 provider 的重复等待
  # 已确认主模型支持图片输入时，直接以内联图片交给主模型
  image_input_mode: native

# 自定义 provider 的模型不会总能从模型目录自动识别视觉能力。
# 请在已有 model 配置中保留其他字段，并追加 supports_vision: true。
model:
  supports_vision: true

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

# Slash Command 发送者门禁；命令名不带 /
platforms:
  milky:
    extra:
      # 私聊管理员 QQ 号
      allow_admin_from:
        - "123456789"

      # 私聊普通用户允许的只读命令
      user_allowed_commands:
        - "milky"
        - "status"
        - "context"
        - "agents"

      # 群聊管理员 QQ 号
      group_allow_admin_from:
        - "123456789"

      # 群聊普通用户允许的只读命令
      group_user_allowed_commands:
        - "milky"
        - "status"
        - "context"
        - "agents"

# 成员入退群即时通知需要允许插件向已有 Gateway session 注入消息
plugins:
  entries:
    hermes-plugin-milky:
      allow_gateway_injection: true

# 关闭后台自动复盘、自动写入记忆/Skill
auxiliary:
  background_review:
    enabled: true

memory:
  memory_enabled: true
  user_profile_enabled: true
  nudge_interval: 20    # 每累计 20 个对话回合，触发一次自动记忆复盘，写入 MEMORY.md / USER.md

# 关闭自动建议创建 Skill
skills:
  creation_nudge_interval: 0

# /goal 的最大自动续行轮数
goals:
  max_turns: 20

# 推荐闲置 2 小时后重置，避免群聊上下文无限变旧
session_reset:
  mode: idle
  idle_minutes: 120
  notify: false
```

管理员可以执行所有已注册命令；普通用户默认可以执行 `/help` 和 `/whoami`，以及对应
`user_allowed_commands` 中列出的命令。私聊和群聊的管理员列表分别配置；某个作用域未配置
对应的 `*_allow_admin_from` 时，该作用域的 Slash Command 门禁不会启用。

建议只开放明确的只读命令。`config`、`tools`、`model`、`sessions`、`cron`、`goal`、
`memory`、`suggestions` 和 `skills` 等命令包含配置、会话、工具或任务状态变更，不建议加入普通用户白名单。

修改后需要重启 Gateway；配置只在启动时读取。

设置 `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 为正数后，超出阈值的有序文本/native
`image`/`record`/`video` 批次会通过一次 `send_group_message` 或
`send_private_message` 发送，顶层 `message` 只含一个 `forward`，节点身份优先使用已确认的
Bot `uin`/昵称。身份读取失败、昵称为空或含控制字符时固定使用 `user_id=10001`、
`sender_name=QQ用户`；成功出参使用单一 `data.message_seq`。配置为 `0` 或文本长度不超过阈值时，
继续使用普通分块和 `[SPLIT]` 三条预检。文档/文件不是该自动 forward 的目标，继续走独立
file upload；Hermes 若只提供分离的 `MEDIA:` 调用，插件不会猜测其与文本属于同一批次。

需要回滚时删除该变量或改回 `0`，然后重启 Gateway。本文不宣称 Milky 服务端对 forward
总大小或节点数量的未验证上限。

`group_sessions_per_user: false` 会让群友共享同一个 Hermes session；这适合群聊，但也意味着
群内消息会共同影响上下文。`busy_input_mode: queue` 让 Hermes 负责 queue、follow-up、
pending 和 interrupt/steer，插件不复制 Agent 执行队列。

> [!TIP]
> 平台显示设置必须放在 `display.platforms.milky` 下，不要放到全局 `display` 下。

### 关闭自动压缩进度提示

如果不希望在 QQ 中看到自动压缩过程中的 `413`/compression 提示，可通过 CLI 关闭：

```bash
hermes config set compression.progress_notices false
hermes gateway restart
```

该配置只隐藏常规压缩进度提示；压缩最终失败时的错误提示仍会保留。

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

查看本地记忆库中的事实记录：

```bash
sqlite3 -header -column ~/.hermes/memory_store.db "SELECT fact_id, content, category, tags, trust_score, updated_at FROM facts ORDER BY fact_id;"
```

### Will policy

Will 决定一条消息是先等待，还是交给 Hermes：

- `wait`：放入当前 chat 的有界缓冲，暂不启动 Agent；
- `trigger`：先取出该 chat 的等待历史，再把当前消息交给 Hermes。

`MILKY_WILL_POLICY.engine` 只选择一套引擎。`routing` 和 `willingness` 共用消息特征、都输出
`wait`/`trigger`，但**不会叠加运行**。

三类关键词（`routing.keywords`、`willingness.forceKeywords` 和
`willingness.interestKeywords`）只匹配当前消息顶层的 text、markdown 内容，按连续文本直接
做子串匹配。结构化 @ 的显示名称、回退 QQ 号和“全体成员”展示文字不参与关键词匹配，
也不会带来兴趣关键词倍率；直接 @Bot 的独立触发与提及增益仍按对应配置生效。
用户在普通文本里手动输入 `@提醒小助手` 时，“提醒”仍可命中。相邻 text、markdown 可以
组成关键词，但中间有 @、图片等非文本片段时不会跨过它拼接，例如“提”＋@某人＋“醒”
不会命中“提醒”。未命中兴趣关键词时仍使用 `defaultMultiplier` 计算原有基础和属性增益。

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
3. 命中 `willingness.interestKeywords` 时提高本次增益倍率；
4. 命中 `willingness.forceKeywords` 时直接得到 `trigger`，否则在分数超过
   `probabilityThreshold` 后换算成概率并抽样，得到 `wait` 或 `trigger`。

因此，同一条消息可能因为当前分数或随机抽样不同而得到不同结果。`willingness.interestKeywords`
只控制**加分倍率**，不是确定性触发器；`willingness.forceKeywords` 才是**包含即触发**的
确定性规则。

`directForce`、`mentionForce`、`quoteForce` 可让对应信号跳过随机抽样，直接 `trigger`。
其中 `mentionForce` 只匹配直接提及当前 Bot（`mention.user_id == self_id`），`quoteForce` 只匹配
至少一个明确引用当前 Bot 的 reply（`reply.data.sender_id == self_id`）；他人提及、`mention_all`、
`here`、他人引用和无法确认目标的引用都会继续走其他 force 条件或概率抽样。
`forceKeywords` 与这些 force 字段等价地跳过随机抽样，但不额外增加 score；两类关键词同时
命中时，`interestKeywords` 仍控制增益倍率，`forceKeywords` 决定最终触发。
`mentionGain` 只在直接提及当前 Bot 时加分；`quoteGain` 只在至少一个 reply 明确引用当前 Bot
时加分，`has_reply` 只保留 reply 存在性事实，不会单独产生 `quoteGain`；`pokeGain` 只在协议
确认 Bot 为接收者的 self-poke 时加分。非 Bot 或无法确认目标的 mention、reply、poke 均不产生
对应 gain。routing 的 `quote` 规则同样只认引用 Bot；`friend_nudge` 和 `group_nudge` 仍是
observe-only，不会直接创建 Agent turn。通过 Gate 且得到 `trigger` 后立即扣除一次
`replyCost` 参与成本，不等待 Hermes 接受、资源解析或最终发送；后续失败不回滚。等待、Gate
拒绝、命令、temp 和系统事件不会扣费。

示例：默认按概率参与，命中“提醒”时提高增益，命中“紧急”时直接触发：

```json
{
  "engine": "willingness",
  "willingness": {
    "interestKeywords": ["提醒"],
    "forceKeywords": ["紧急"],
    "keywordMultiplier": 1.2,
    "directForce": false,
    "mentionForce": false,
    "quoteForce": false
  }
}
```

迁移时将旧的 `willingness.keywords` 改为 `willingness.interestKeywords`；旧字段不会被静默
兼容。需要包含即触发时再配置 `willingness.forceKeywords`，省略或配置为空数组表示关闭。
两者都只匹配规范化正文的直接子串，不支持正则、分词或隐式大小写转换。

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
    "interestKeywords": [],
    "forceKeywords": [],
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

## 日志

运行时日志使用 `hermes_plugins.milky.*` 标准 logger，并传播到 Hermes root。关键消息使用
`event=milky.lifecycle`、`milky.action`、`milky.sse`、`milky.inbound`、`milky.resource`、
`milky.outbound`、`milky.mute` 或 `milky.tool` 标签；插件不创建独立日志文件、handler、异步队列
或脱敏后端。

常用查看命令：

```bash
hermes logs -f
hermes logs --level DEBUG -f
hermes logs gateway -f
```

Action、Tool 和出站日志保留结果分类、已知状态码和 `duration_ms`，不记录 token、Authorization、
完整 URL、请求/响应 body、消息正文、媒体引用、路径、文件内容、Tool 原始参数或结果。Tool 日志
使用 `delivered` 表示已取得远端响应；协议拒绝和 HTTP 错误也使用该分类并附已知状态码，只有
`invalid_input`、`unsupported` 和 `transport_unknown` 是插件本地 Tool 结果分类。日志不可用或
handler 失败不改变连接、重连、Gate/Will、扣费、发送和未知结果语义。

## 常用运维

### Gateway 与 Hermes 状态

```bash
# 查看 Gateway 状态
hermes gateway status

# 重启 Gateway，使启动配置生效
hermes gateway restart

# 执行 Hermes 整体状态和深度健康检查
hermes status --deep
hermes doctor
```

### 日志与配置

```bash
# 查看最近的 Gateway 日志和错误
hermes logs gateway -n 100
hermes logs errors --since 30m

# 临时提高日志级别并实时跟踪
hermes logs gateway --level DEBUG --since 15m -f

# 列出日志文件，以及检查配置文件位置和有效性
hermes logs list
hermes config path
hermes config env-path
hermes config check
hermes config get security.redact_secrets
```

### 插件与 Milky smoke

```bash
# 查看已安装插件及启用状态
hermes plugins list

# 在源码 checkout 中执行只读 Milky smoke
uv run scripts/milky_smoke.py

# 生成用于提交 issue 的脱敏诊断摘要
hermes dump
```

`milky_smoke.py` 默认只执行登录、群列表、Bot 成员禁言同步和有界 SSE 连接。发送消息或上传文件
必须显式使用 `--allow-write`，并且目标还必须位于 `MILKY_ALLOWED_CHATS` 中；没有明确授权时不要
使用该选项。`hermes dump` 用于生成脱敏诊断摘要，不要把包含敏感配置的命令输出直接粘贴到公开 issue。

### 排查日志中的 chat key 脱敏

Hermes core 默认会对日志中的敏感字段进行脱敏。如果需要临时确认日志中的完整 `chat_key`，可用
Hermes CLI 关闭全局脱敏：

```bash
hermes config set security.redact_secrets false
```

修改后必须重启 Gateway；该配置只在进程启动时读取。排查完成后立即恢复脱敏：

```bash
hermes config set security.redact_secrets true
```

该开关影响 Hermes 全局的日志、工具输出和聊天响应，不只影响 Milky。关闭期间可能泄露 API key、
token 或密码，仅应在受控环境中短时使用。

## 功能与使用

### 消息与媒体

普通入站只处理 `message_receive`：

- friend 和 group 消息进入普通 Agent 流程；
- `temp` 会话直接忽略；
- Milky SSE `GET /event` 中的 `message_recall`、request、notice、lifecycle 和未知事件默认只观察，少数系统事件可作为上下文；
- `face` segment 的正文占位符对非 `emoji 表情` pack 优先使用随插件发布的本地 catalog 名称；未命中、冲突或目录不可用时回退原 `face_id`，缺失 ID 时使用 `NOT SUPPORTED`；
- 同一 chat 按顺序处理，`wait` 消息进入有界历史，`trigger` 时再交给 Hermes。

支持 system prompt section 的 Hermes 宿主会额外注册
`hermes-plugin-milky.qq-session-context`。合法 friend 介绍只包含 `user_id`、`nickname`、
`sex`；合法 group 介绍只包含 `group_id`、`group_name`、`member_count`、`description`、
`announcement`。快照在资源解析、MessageEvent mapper 成功后、Hermes `handle_message()` 前登记，
以 `dm:<id>`/`group:<id>` 隔离并使用有界进程内缓存；不同 Hermes user session 可以共享同一个 group
介绍。介绍不会写入当前消息正文、历史 `channel_context`、platform hint 或出站正文。

昵称、群名、描述和公告按不可信 metadata 处理：控制字符和换行会被中和并限制长度，未知扩展、
raw、凭证、媒体 URL、文件路径和敏感正文不会渲染。Gate deny、wait、temp、系统事件、重复消息或
资源/mapper 失败不登记介绍；缓存淘汰和资料缺失安全返回空 section。Hermes 已持久化 prompt 恢复
时保留原介绍字节，显式 prompt rebuild 才使用当前本地快照；插件不提供实时刷新。

`message_recall` 的上下文行为如下：

- 只有字段完整且 `message_scene` 为 `friend` 或 `group` 时才登记；friend 写入 `dm:<peer_id>`，group 写入 `group:<peer_id>`，非法场景或 ID 只记录安全诊断；
- 合法事件进入对应 chat 的有界 system context FIFO，在下一次同 chat `trigger` 的 `channel_context` 中按 ingress 顺序出现一次，格式为 `<event message_recall> ...`；
- 无 `operator_id` 或 `operator_id == sender_id` 时显示 `uid <sender_id> recalled message msg_seq <message_seq>`；群聊仅在 `operator_id != sender_id` 时显示 `Admin uid <operator_id> recalled uid <sender_id>'s message msg_seq <message_seq>`，好友有不同操作人时不添加管理员角色；
- 撤回事件不创建普通 Agent turn、不发送回复、不调用主动撤回工具，也不调用 `get_message` 或下载资源；插件只展示撤回元数据，不承诺恢复被撤回消息正文；
- 该路径仍是 observe-only，不经过普通消息的 Gate/Will，也不扣 reply cost。fixture 和 fake host 测试不代表真实 Milky 服务端能力已被集成验证。

`group_nudge` 和 `friend_nudge` 也只进入对应 chat 的 system context，固定英文 body 分别为
`uid <sender_id> poked uid <receiver_id>` 和 `uid <user_id> poked once`。成员事件使用以下基础
英文 body，并由 renderer 统一添加 `<event group_member_increase>` 或
`<event group_member_decrease>` 前缀：

- `uid <user_id> joined the group. Details: {"group_id": ..., "user_id": ..., "operator_id": ..., "invitor_id": ...}`
- `uid <user_id> left the group. Details: {"group_id": ..., "user_id": ..., "operator_id": ...}`

缺失或为 null 的 `operator_id`/`invitor_id` 会从 `Details` 省略；display text、URL、timestamp、raw
扩展和撤回正文不会进入 body。默认 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS=false` 时，成员事件不
带 Tip、不即时触发 Agent，保留在 system context 等下一次普通消息。设置为大小写不敏感的 `true`
后，成员 body 末尾追加固定英文 Tip，并只通过 Hermes 已有的 `inject_message` 交接；没有已确认或持久化恢复的
session key、没有注入授权、宿主不可用或注入被拒绝时，带 Tip 的上下文保留，不猜测 session key，
也不直接调用 Milky Action。配置值在启动后不热切换，修改后需要重启 Gateway。

Agent 发送本地媒体时，在回复中写入：

```text
MEDIA:<local_path>
```

例如 `MEDIA:~/path/to/clip.mp4`。显式调用 Hermes `send_message` 时，把同一指令放在
`message` 参数中。图片、语音和视频使用 Milky native segment，文档使用独立 file upload。

如果无需回复，只返回 `[SILENT]`，不附加其他内容；该标记由 Hermes core 抑制消息投递，Milky
plugin 不单独解析它。

需要模拟自然聊天节奏时，可把区分大小写且未转义的 `[SPLIT]` 单独放在一行，或直接放在普通
正文行中。独立行标记及其分隔边界会被删除，行中标记只删除自身；空段不发送，文本按原顺序
最多发送三条。超过三段时尾部合并到第三段，每个文本单元仍遵守既有长度边界，若实际文本消息
会超过三条，则在网络访问前整体拒绝。需要显示字面量 `[SPLIT]` 时使用 `[[SPLIT]]`；语法完整的
CQ-compatible 或 unknown type CQ 候选中的标记不触发分段；候选的 `CQ` 前缀大小写不敏感，但
malformed 或未闭合 CQ-like 内容中的标记按普通文本规则处理。普通长文本没有有效 `[SPLIT]` 时
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

`CQ` 前缀大小写不敏感，但 type、字段和真实 ID 仍按既有规则校验；未知或转换失败的 CQ
控制码保留完整原文。普通图片请使用 `MEDIA:<local_path>`。sticker 会在发送前转换为 `base64://`。

本地路径、`Path` 和 `file://localhost` 只在 plugin 边界读取一次并受上述本地字节上限约束；
格式合法的 `http(s)://` 和显式 `base64://` 会原样传递，plugin 不下载、读取或解码，也不应用
本地文件大小检查。

### Slash command

纯文本 `/...` 消息会在 canonical、去重和 Gate 之后分流，不进入 Will 历史或普通 Agent 正文。
合法命令交给 Hermes 既有命令分发；插件自身提供无参数 `/milky`，用于以可读摘要返回 Milky 实现信息。

`/milky sticker` 只处理显式人工维护参数，固定命令为：

```text
/milky sticker add [--dry-run]
/milky sticker list [--limit 1..100]
/milky sticker edit <sticker_id> [--emotion=<enum>] [--tags=<tag1>,<tag2>,...] [--description=<text>] [--clear=<field>[,<field>...]]
/milky sticker reanalyze <sticker_id>
/milky sticker del <sticker_id>
/milky sticker cleanup [--dry-run]
/milky sticker reindex
```

首次有效维护命令才会在 Hermes plugin-data 下创建 `stickers/inbox/`、`stickers/library/`、
`stickers/junk/` 和独立 `stickers.db`。`add` 递归扫描 inbox，只接受 PNG、JPEG、GIF、WebP，单文件
上限为 `10 MiB`，按流式 SHA-256 去重；视觉辅助只在显式 `add`、`add --dry-run` 或 `reanalyze`
中调用。每次 add 最多处理 50 张唯一候选，同时最多 10 个视觉调用；其余候选留在 inbox 并报告
`batch_deferred`。合法 `is_sticker=true` 原文件原子移动到 library，`false` 原文件移动到 junk，
视觉失败或结构非法留在 inbox。dry-run 只校验、去重、分析和预览，不移动文件或写入数据库。

库条目保存 `detected_*` 视觉基线、当前生效 `emotion`/`tags`/`description`、字段级 `vision`/`manual`
来源、`created_at`/`updated_at`/`detected_at`、`use_count` 和 UTC `last_used_at`。`edit` 只更新指定
字段；`--clear` 恢复对应视觉基线。`reanalyze` 只刷新视觉基线，人工字段保持不变；返回 `false` 时
报告 `not_sticker` 并保留原条目。`list` 输出受限摘要，不输出路径、URL、原文件名或图片 bytes。
`cleanup` 不扫描或删除 junk；`reindex` 只重建 library 的 `sticker_files` 技术索引，不创建贴纸条目。

当前 command handler 只收到 `raw_args`，本 change 不推断 Milky friend/group 或操作者身份，也不增加
`MILKY_STICKER_OPERATOR_IDS` 等插件授权配置。贴纸维护不创建旁路 Milky client、Agent Tool、主 Agent
transcript、普通消息 handoff 或脱离命令生命周期的后台视觉任务。

`sticker_send` 是独立的语义 Tool，不是任意 Milky Action。插件通过 `plugin.yaml` 的 `python_dependencies`
和项目运行时依赖声明提供 `Pillow>=12.3.0`、`jieba>=0.42.1`；它只在库中有可用条目时进入 Agent
definitions，空库时隐藏，不按需导入或检查可选 tokenizer，也不影响维护命令和其他
Tool。参数只允许 `intent`、`emotion`、`tags`，目标来自当前 task-local `HERMES_SESSION_PLATFORM=milky` 和
`HERMES_SESSION_CHAT_ID`。检索只使用当前 `emotion`、`tags`、`description`，以完整短语/全部 token/部分 token
固定层级比较；没有 `sticker_search`，也不使用远程模型、embedding 或数值阈值。只有完全并列候选才按当前 chat
软轮换，发送前校验 library 文件和双索引 SHA-256，单次调用只发一张 `sub_type=sticker` 图片。结果使用
`sent`、`no_match`、`invalid_input`、`missing_session_context`、`unsupported`、`missing_file`、
`storage_error`、`rejected`、`http_error`、`malformed` 和 `transport_unknown` 等固定分类。

### QQ ToolSpec

插件固定提供 25 个与 Milky operationId 对齐的 QQ Action ToolSpec，另提供一个受限的语义 `sticker_send`：

- 群组和成员查询；
- 文件、转发消息和私聊文件链接查询；
- 戳一戳、点赞、撤回、禁言、踢人、退群和删好友；
- 好友请求、入群请求和群邀请的接受/拒绝。

请求/邀请的接受和拒绝不会由通知、普通正文、关键词或 Will 自动触发，必须由 Agent 显式提供
完整参数。25 个 Action Tool 只要取得响应体就把 UTF-8 解码后的字符串原样交给 Hermes core：
不校验 HTTP 状态、`status`/`retcode`、`data` 结构，不重建 envelope，不附加状态码，也不脱敏
`access_token`、`authorization`、`cookie`、`password`、`token`（任意大小写）字段。无法按 UTF-8
解码的字节使用替换字符。参数非法、Tool 不支持或未取得响应体时分别返回 `invalid_input`、
`unsupported` 或 `transport_unknown`；有副作用的调用最多提交一次且不自动重试。

Tool 结果进入 Hermes core 后，宿主可能运行 `transform_tool_result`、截断 JSON `error` 字段，或
把超长结果落盘并以预览替换上下文内容。这些后置处理由宿主负责，插件不注册、不规避，也不承诺
最终进入模型上下文的内容与 Milky body 一致。原样交付可能使上述五类字段进入宿主转录或落盘，
上下文策略由宿主负责。

`sticker_send` 不属于上述 Action catalog；它不接受 `sticker_id`、`chat_id`、`session_id`、路径或 URL，
也不限制 Agent 在不同调用中重复请求。它的 target、库读取、统计 claim 和单次发送由独立的贴纸 service 管理。

入站文件只显示为安全占位符，例如
`[file:file_id=<file_id>,file_name=<file_name>,file_hash=<file_hash>]`；它不会被当作本地路径
或出站文件。

### 连接与生命周期

连接时依次完成登录信息、群列表和每个群的 Bot 成员状态同步，之后才启动事件流并开放普通
消息入口。断开时会取消 event、pipeline、TTL 任务，解除 sender/command 绑定，并关闭
HTTP/SSE 资源。

非 Tool 出站成功在插件侧使用远端 `data.message_seq` 的稳定字符串作为 `message_seq`，交给 Hermes 时映射为宿主要求的 `message_id`；协议拒绝、传输未知、
malformed 和 unsupported 会保持明确失败分类。缺少消息序号时不会伪造稳定去重 ID。

## API 与开发

插件不是以 Python package entry point 发布；Hermes 从根目录加载 `plugin.yaml`，再调用唯一
公开入口 `__init__.py::register(ctx)`。

| 对象 | 作用 |
| --- | --- |
| `__init__.py::register(ctx)` | 解析启动配置，注册 platform、`/milky`、ToolSpec、standalone sender、QQ 指引 section 和 QQ 会话介绍 section。 |
| `__init__.py::register_tools(ctx)` | 委托 `outbound.tools` 注册固定 ToolSpec；注册阶段不联网。 |
| `MilkyAdapter` | 管理连接、停止、入站交接和出站委托。 |
| `MilkyOutboundSender` | 校验 `group:/dm:` 目标，格式化消息并调用 Milky Action/upload。 |
| `SlashCommandService` | 管理活动 Milky client，处理 `/milky` 和显式贴纸维护命令。 |
| `stickers/` | 懒加载独立 `stickers.db`，校验 inbox 图片，执行维护命令以及受限 `sticker_send` 检索/claim；`jieba` 由插件运行时依赖提供。 |

支持 `register_system_prompt_section` 的 Hermes 宿主会在 `after_memory` 登记
`hermes-plugin-milky.qq-platform-guidance`，并在连接完成后使用已确认的 QQ UID 和昵称渲染
媒体、CQ-compatible、无回复和 bundled skill 指引。旧宿主仍可完成平台注册，但只获得首句提示。

同一宿主还会登记 `hermes-plugin-milky.qq-session-context`；其 callback 只读取当前
`HERMES_SESSION_CHAT_ID` 对应的本地安全快照，不发起网络或文件 I/O。旧宿主、没有当前 chat
context、资料缺失或快照已淘汰时不注入会话介绍。

详细的稳定模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)；可观察行为和测试要求见
[openspec/](openspec/)。新建的未归档 change 会放在 [openspec/changes/](openspec/changes/)。

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
