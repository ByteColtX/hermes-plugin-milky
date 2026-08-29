# hermes-plugin-milky 开发约束

## 项目定位

本仓库是 Hermes 的 Milky QQ 平台适配器。`ARCHITECTURE.md` 是实现契约和行为的唯一事实来源；旧的 OneBot v11 项目只能用于迁移经验和测试思路，不能作为 Milky 协议行为的依据。当前仓库仍处于新建骨架阶段，尚未具备可运行的完整适配器或测试套件，不得把目标架构描述成已经实现的功能。

开始任何代码、测试或配置实现前，必须先读取 `ARCHITECTURE.md` 和当前 OpenSpec change 的全部 artifacts，尤其是 `tasks.md`，再按当前任务读取相关参考项目或源码。Codex 会自动发现 `AGENTS.md` 指令链，但不会因为文件名是 `ARCHITECTURE.md` 或 OpenSpec artifact 就自动加载它们；本文件负责声明它们是本仓库的必读事实来源。

本仓库采用可持续的 vibe coding 工作协议：在同一个 `/goal` 中可以连续推进多个小任务，但每个任务都必须经历“契约/fixture → 实现 → 单元或集成测试 → 质量门禁 → 必要的本地 Milky smoke → 反馈分类 → 最小复现和回归测试 → 修复/重构 → 重新验证”的闭环。不得把“一次生成全部代码，最后统一检查”视为完成标准。任务状态以当前 OpenSpec change 的 `tasks.md` checkbox 为唯一来源，命令结果、真实环境差异和阻塞原因记录在同一文件的证据台账中。

运行时要求 Python 3.13+，使用 `uv` 管理环境和依赖。

## 开发环境与命令

- 运行 Python 脚本使用 `uv run <script.py>`，不得直接使用 `python` 或 `python3`。
- 管理依赖使用 `uv sync`、`uv add` 和 `uv remove`；临时工具使用 `uvx`。
- 代码遵循 Google Python Style Guide；保持类型明确、模块职责单一，并为新增行为补测试。
- Python 注释和 Docstring 必须使用中文；`Hermes`、`Milky`、`plugin`等专业词汇保持英文。
- 常用质量检查命令：

  ```text
  uv run pytest
  uv run ruff check .
  uv run ruff format --check .
  uv build
  git diff --check
  ```

- OpenSpec strict validation 使用可复现的临时 CLI，不依赖全局 `openspec` 是否在 `PATH` 中：

  ```text
  npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict
  ```

- 当前没有完整测试套件时，不能声称上述检查已经通过；实现每个任务时应同时补充可执行的单元、集成或协议 fixture 测试。
- 修改导入、包布局或生命周期代码后，至少运行相关测试、`uv run ruff check .`、`uv run ruff format --check .` 和 `git diff --check`。

## Codex 环境边界

- 项目规则放在本文件；个人跨仓库默认值由用户级 `~/.codex/AGENTS.md` 和 `~/.codex/config.toml` 提供。项目级 `.codex/config.toml` 只有在项目被信任时才生效，不得把个人路径、凭证或机器专属配置提交进仓库。
- `MILKY_ACCESS_TOKEN`、MCP token 和其他秘密只从运行时环境或安全凭证存储注入；不得写入 `AGENTS.md`、架构文档、fixture、日志、快照、异常或提交。
- MCP、浏览器和本地 Milky 服务是可选的外部能力；实现必须先能用 fake transport 和 fixture 验证，不能把当前会话中可用的 MCP 当作 CI 或其他开发者必有的依赖。
- Milky 接口调试必须优先使用当前会话实际暴露的 Milky MCP 连接和测试环境；执行前先读取当前版本的 Milky OpenAPI MCP 文档，接口路径、HTTP 方法、请求参数、响应 envelope 和字段只能以 OpenAPI、MCP 返回或测试环境真实响应为依据。不得使用 OneBot、`mcp__snowluma__*` 或其他相邻协议的接口/字段推断 Milky 行为，也不得凭名称猜测未确认的 Action。
- 当前会话没有可执行的 Milky Action MCP 时，必须明确记录该能力缺失；仅可在必要时使用只读 HTTP fallback 核对测试环境，并对请求、响应和命令输出脱敏。写入、发送、撤回、修改状态、上传文件以及会影响测试环境的 Action 必须先取得明确确认；不能把 OpenAPI 文档清单当成测试环境已经支持，也不能把 HTTP 200 当成协议成功。
- 调试发现的字段差异、可省略字段、空值、未知 segment、版本差异和错误 envelope 必须记录为可复现的协议证据，并在未确认前标记为 `unknown`、`malformed`、`unsupported` 或 `blocked`；不得补默认值、静默改名、跨层级取值或把未知内容伪装成已支持字段。只有经过脱敏的字段形状和边界分类可以进入 fixture/spec，不得提交 live snapshot。
- Milky 调试使用运行时环境变量或安全凭证注入 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN`；不得把 token、`Authorization`、真实 QQ/群 ID、完整敏感正文、媒体 URL/本地路径或原始 live 响应写入仓库、日志、异常、fixture、快照、OpenSpec artifact 或回复。真实环境结论必须同时注明使用的 MCP/fallback、Action、参数边界、响应分类和时间；无法确认的接口保持未实现或 `unsupported`。
- 每次工作开始时报告实际读取的指令/设计来源、当前任务范围和验证计划；结束时报告改动文件、命令结果、未解决风险和下一步任务。

配置依据参见 OpenAI 官方文档：[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Config basics](https://learn.chatgpt.com/docs/config-file/config-basic)、[Environment variables](https://learn.chatgpt.com/docs/config-file/environment-variables)、[MCP](https://learn.chatgpt.com/docs/extend/mcp) 和 [Prompting Codex](https://learn.chatgpt.com/docs/prompting)。

## 公开入口与包边界

- Hermes 只从根目录 `__init__.py::register(ctx)` 发现插件；这是唯一公开注册入口。
- `register(ctx)` 只读取上下文、解析配置、组装依赖和注册平台；standalone sender 暂不纳入当前实现，除非后续先确认 Hermes 扩展点和附件协议。导入或注册阶段不得建立网络连接。
- `adapter.py` 是 `BasePlatformAdapter` 薄层，只负责生命周期和少量委托，不应承载协议解析、环境变量解析、Will 公式或大量 Action 编排。
- `register.py` 不是第二个入口。若保留，只能作为不被 manifest 发现的私有辅助或兼容转发；manifest 和文档不得同时声明两个入口。
- 目标模块职责如下：

  ```text
  config/    配置解析和默认值
  milky/     DTO、HTTP Action、SSE、事件和资源引用
  inbound/   canonical、normalizer、extractor、Hermes mapper、pipeline
  gates/     硬性门禁
  will/      routing/willingness 决策
  session/   chat admission 和有界 wait buffer
  state/     Bot 群禁言状态
  outbound/  Milky segment 格式化、路由、拆分
  tests/     fixture、unit、integration
  ```

- 依赖方向必须保持清晰：`milky` 不依赖 Gate/Will/Hermes transcript；`gates` 不做网络 I/O；`will` 不做授权、网络或文件系统操作；`session` 不使用 Hermes session store；`outbound` 不读取入站白名单或 Will 分数。

## Milky 协议边界

- `MILKY_BASE_URL` 去除末尾斜杠但保留已有 path prefix。HTTP Action 统一为 `/api/{action}`，事件流统一为同 scheme/host/port/prefix 下的 `/event`；事件流路径不得追加 `/api` 或重复 `/event`。
- Action 使用 HTTP `POST` JSON；无参数 Action 也发送 `{}`，不依赖 GET 或 query string。
- 默认使用 `Authorization: Bearer <token>`。token、Authorization header 和任何凭证都不得进入日志、异常、`SendResult`、fixture、快照或提交内容。
- HTTP client 必须区分连接/超时、非 JSON、HTTP 错误和 envelope 的 `status`/`retcode` 错误，并验证当前 Action 所需的最小 `data` 结构。HTTP 200 不代表协议成功。
- 成功发送必须使用远端 `data.message_seq` 生成稳定字符串形式的 `SendResult.message_id`；不得用本地时间、随机数或伪造 ID。
- 发送超时表示远端是否执行未知，默认不得盲目重试；只有明确幂等或明确未执行的请求才允许自动重试。
- v0.1 的事件主路径是 SSE `GET /event`：正确处理 `event:`、多行 `data:`、空行边界、断线、重连、取消和退避。handler 不得阻塞 receive loop，malformed/unknown 事件应安全记录并继续。
- 不实现 OneBot 的 echo、pending response map，也不能让 HTTP Action response 与事件流通过 WS echo 互相唤醒。WebSocket 只能作为未来复用同一 EventStream 接口的 fallback；WebHook 不属于 v0.1。
- 连接完成登录信息和禁言初始同步后，才允许 `message_receive` 进入入站 pipeline。断线重连不保证恢复丢失事件，也不恢复 wait buffer 或 Will 分数。

## 身份、顺序和入站流水线

- 所有进入正常流水线的内部状态只接受规范化 chat key：`group:<十进制群号>`、`dm:<十进制QQ号>`。必须拒绝空值、负数、非数字和包含额外分隔符的 ID；`message_scene=temp` 在协议边界记录 `ignored_temp` 后丢弃，不创建 chat key。
- friend 使用 `dm:`，group 使用 `group:`。临时会话不触发 Agent、不发送，也不进入 canonical、buffer 或 Will；出站不得回退到 dm 或默认目标。
- canonical record 至少包含 `platform`、`self_id`、`scene`、`chat_key`、`peer_id`、`sender_id`、`message_id`、规范化 Unix 秒时间戳、typed segments、正文、mention/quote 信号、媒体引用、raw 和安全 metadata。
- 去重 key 至少为 `milky:<self_id>:<chat_key>:<message_id>`。dedup 是有界 TTL 内存 map，检查和插入必须原子化，并且早于资源补全、Will 和 Hermes turn。缺少 `message_id` 时不得伪造稳定 key；可以处理一次并记录 `no_stable_message_id`。
- 同一 chat 的 canonical、Gate、buffer、Will 和 trigger 交接必须在短暂 admission 边界中按 ingress sequence 完成；trigger 随后进入有界 ordered handoff，按相同顺序完成资源解析、mapper 和 `handle_message()` 提交。该 handoff 不得等待 Agent 执行；Hermes 自己负责 busy/follow-up/interrupt 及单槽 pending，不得在插件中复制 Agent 队列；不同 chat 可以并行。锁之间不得形成循环等待。
- 入站处理顺序必须保持：

  ```text
  SSE /event
    -> 只接受 message_receive
    -> tolerant parse/normalize/canonical
    -> TTL dedup
    -> per-chat admission
    -> SelfMessageGate
    -> ChatAllowlistGate
    -> MutedGroupGate
    -> allow 后写入有界 wait buffer
    -> WillEngine.decide
    -> wait 结束；trigger 则原子 drain 当前 chat
    -> 资源/回复补全
    -> Hermes MessageEvent mapper
    -> adapter.handle_message()
    -> handle_message() 提交正常返回后通知 Will reply cost
  ```

- Gate deny 不得增长 buffer 或修改 Will。wait 不得调用 Hermes，也不得写入 Hermes transcript。trigger 必须先原子 drain，再创建 detached batch；历史 wait 消息只能进入 `channel_context`，当前 trigger 消息只能作为本次正文，不能重复出现。
- detached batch 交接失败时只能重试同一批次或记录不可恢复失败，不得无条件重新追加到 buffer。只有 `handle_message()` 提交正常返回后，才能执行一次 reply cost；v0.1 不等待 Agent 最终完成。
- 只接受 `message_receive` 作为普通消息入口；recall、request、notice、lifecycle 和未知事件默认 observe-only，不得伪装成普通消息触发 Agent。

## Segment、媒体与 Hermes 映射

- normalizer 不做网络 I/O，只生成 tolerant 领域记录和待补全资源引用。支持并测试 text、mention、mention_all、face、reply、image、record、video、file、forward 及未知 segment。
- mention 必须区分 self/all/here；reply 保留目标 ID；face、未知媒体和协议扩展可保留 raw 与可解释占位，但不能悄悄把未知内容变成普通文本或 Agent 指令。
- 一条消息没有任何受支持正文或媒体内容时，记录明确丢弃原因并停止，不得创建空的 `MessageEvent`。
- wait 阶段只保存 URL、file_id、file、名称、MIME/大小提示和原始 segment，禁止下载文件。
- trigger 阶段才允许调用 Milky 资源接口或 `get_message` 做回复补全。远端引用必须交给 Hermes 公共 media helper；插件不得创建 media cache、下载目录、权限规则、SSRF 规则或自行拼接 Hermes 本地路径。
- 资源失败必须保留正文和可解释占位，例如 `[图片不可用]`、`[文件不可用]`、`[语音转写失败]`，并在 metadata 中记录不含凭证的错误类别。
- `message_type` 映射为 friend/private 和 group/group；temp 在 mapper 前已忽略。`source` 固定为 `milky`，`message_id` 使用 Milky ID 字符串，reply 字段和 `channel_context` 按架构契约填充。

## Gate、Will 与 MuteTracker

- Gate 是确定性的硬性门禁，默认顺序不可改变：
  1. `SelfMessageGate`：`sender_id == self_id` 时拒绝。
  2. `ChatAllowlistGate`：`MILKY_ALLOWED_CHATS` 为空则放行，否则要求完整 chat key 命中。
  3. `MutedGroupGate`：读取 MuteTracker 的 member/whole mute 二态快照；任一状态为 muted 即拒绝，未成功维护为 unmuted 前默认拒绝。
- Gate 不得包含概率、关键词、回复发送、网络查询或 Will 分数修改；“当前不想说话”属于 Will，不是 Gate 拒绝。
- Will 只在 Gate allow 后执行，输出 `wait` 或 `trigger`。`WillInput` 必须是已标准化的特征快照，至少包括 self/chat/channel、segments、text、mention kind、quote、image、event type 和 timestamp；clock/random 必须依赖注入。
- `MILKY_WILL_POLICY` 必须支持借鉴 YesImBot 设计的嵌套 `engine`、`routing`、`willingness` 和 `priority` 字段。默认 engine 为 routing，缺省值与 `ARCHITECTURE.md` 完整示例一致；不得静默把旧扁平 schema 与新 schema 合并。
- willingness 的状态按 chat 隔离，仅维护 `score`、`lastMessageAt`、`lastDecayAt`。公式、字段名、force 判断顺序和更新顺序由本项目契约定义，不承诺与 YesImBot 某个源码版本逐项兼容，不得简化为线性增长或单一阈值。
- 测试必须覆盖 routing 顺序、完整 willingness 公式、阈值/半衰期、ratio 分段、概率 clamp、force、关键词、direct/image/reply/poke、时钟回拨、独立 chat 状态和提交即扣费。
- MuteTracker 的初始同步顺序为：`get_login_info` -> `get_group_list` -> 对每个群调用 `get_group_member_info(group_id, user_id=self_id)`。使用 Milky 字段 `member.shut_up_end_time`，不得替换为旧协议字段。
- 维护 member mute、whole mute、观测时间和刷新时间；状态只有 muted/unmuted，初始和未成功维护时默认 muted。全量刷新须清理已不在 group list 的旧群，失败时保留上次二态状态，不能把 API 错误解释为 unmuted。
- `group_mute` 的 `duration=0` 表示取消；`group_whole_mute` 按 `is_mute` 更新。群消息出站失败触发有锁、有冷却、有并发上限的刷新；私聊失败绝不能查询群成员状态。原始发送错误仍须返回 Hermes。

## 出站与配置

- `group:<id>` 使用 `send_group_message`，`dm:<id>` 使用 `send_private_message`；临时目标在网络访问前返回 `unsupported`。目标解析失败必须在网络访问前返回失败，不能回退默认频道或私聊。
- 所有文本和结构化内容由 `outbound/formatter.py` 生成 Milky segment；adapter 不手工拼 Action body。空白消息在访问网络前拒绝，超长文本由 `chunking.py` 按明确边界拆分。
- file 不是 `OutgoingSegment`。文件必须调用 `upload_group_file` 或 `upload_private_file`；不得把 file segment 塞进 send message，也不得假设远端能访问本地路径。
- 未实现的编辑、撤回、reaction 或其他 Action 必须返回 `unsupported`，不得依据 Action 名称猜测能力或报告假成功。错误至少区分 `rejected`、`transport_unknown`、`malformed` 和 `unsupported`。
- v0.1 不声明或使用 `MILKY_HOME_CHANNEL`，不提供任意 Agent-callable Milky Action catalog；只提供架构中列明的三个显式 ToolSpec，也不支持自动批准/拒绝请求事件。
- 当前配置契约只有：必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN`，可选的 `MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`。配置只在启动时解析一次，并输出脱敏摘要；不要同时支持旧的 allowed groups/users、muted groups、require mention 或扁平 dm policy。

## 测试与安全验收

- 协议 fixture 应覆盖 URL 派生、Bearer、POST `{}`、成功/失败 envelope、`message_seq`、字段缺失和未知字段；SSE 应覆盖事件边界、断线重连、取消、unknown event 和 handler 不阻塞 receive loop。
- 单元/集成测试应覆盖 friend/group、temp 忽略、全部 segment、canonical/dedup、Gate、routing/willingness、admission/buffer、媒体延迟补全、出站文件上传、SendResult、MuteTracker、首批三个 ToolSpec 和 fake Hermes/fake Milky pipeline。
- 本地 Milky smoke test 必须使用运行时环境变量提供凭证；任何真实 token、个人 QQ、媒体路径和敏感正文都不得进入 fixture、日志或提交。
- 外部 Action 的参数在进入 HTTP client 前做类型、范围和目标校验；inbound 不是授权来源，授权只能来自 allowlist、MuteTracker 和未来明确的审批机制。
- 变更完成前核对 `ARCHITECTURE.md` 的完成定义：唯一入口、canonical/dedup 在前、Gate/Will 分离、完整 willingness、正确禁言字段、Hermes 媒体所有权、文件 upload、temp/unknown/unsupported 的明确降级、首批 ToolSpec 的参数边界，以及可复现的测试证据。

## Git 提交

- 提交消息遵循 Conventional Commits，subject/body 全部使用中文。
- 使用标准 type：`feat`、`fix`、`refactor`、`perf`、`docs`、`test`、`chore`、`ci`、`build`、`style`、`revert`；scope 可选但建议使用。
- subject 使用祈使语气、全小写、无句号且不超过 72 个字符；subject 与 body 之间必须保留一个空行。
- 每个提交必须包含正文，不得只提交 subject。body 必须使用项目符号逐项说明变更背景、修改动机、关键影响和未解决风险；不得只罗列文件名或机械重复 subject。
- body 的每一项必须以 `- ` 开头；较长项目必须手动换行，续行使用缩进并保持可读，不得把多项内容挤成一行。
- body 说明修改动机而非重复修改内容；适用时在 footer 引用 issue 或 breaking change。提交前必须检查最终提交消息确实包含正文和项目符号。
