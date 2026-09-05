# hermes-plugin-milky agent guide

这是 Hermes 的 Milky QQ directory plugin。Hermes 从根目录的 `plugin.yaml` 和
`__init__.py::register(ctx)` 加载它；`pyproject.toml` 只用于 uv 开发环境和质量检查。

## 开始工作前

- 阅读本文件、`ARCHITECTURE.md`、相关 `README.md`、实际源码和测试。
- 查看 `openspec/changes/` 下未归档 change；相关 change 的 `proposal.md`、`design.md`、
  全部 delta spec 和 `tasks.md` 都要读完。归档 change 只作历史参考。
- 不从 OneBot v11 或旧代码推断 Milky 行为。`tasks.md` checkbox 表示进度，命令结果、skip
  和外部阻塞写入 evidence ledger。
- 发现实现、文档和契约冲突时，先定位差异，再更新正确的事实来源，不能静默扩大范围。

## 常用命令

Python 要求 3.13+；使用 `uv`/`uvx`，不要直接调用 `python`、`python3`、`pip` 或 `pipx`。

```text
uv sync
uv run pytest -q
uv run pytest -q tests/test_config.py tests/test_outbound.py
uv run ruff check .
uv run ruff format --check .
uv build
git diff --check
npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict
```

修改导入、生命周期、协议或出站路径后，运行相关测试、Ruff、format 和 diff 检查；行为变化
再运行完整质量门禁。skip 或只在 fake host 上通过的检查，不算真实集成通过。

本地 smoke：`uv run scripts/milky_smoke.py --help`。默认只读；发送/上传必须有明确授权、
`--allow-write`，且目标命中运行时 `MILKY_ALLOWED_CHATS`。真实响应和 smoke 输出不回写仓库。

## 实现硬约束

- 只有根目录 `__init__.py::register(ctx)` 是公开入口；import/register 阶段不得联网、建立
  SSE 或创建长期任务。不得修改、替换或 monkey patch Hermes core。
- `connect()` 先完成 `get_login_info`、`get_group_list` 和每个群的
  `get_group_member_info(..., no_cache=true)`，再开放普通消息和 SSE；断开时释放所有任务和
  client。standalone sender 每次独立创建/关闭 client，当前只支持无附件文本。
- 普通 Agent 流程只接受 `message_receive`。friend 使用 `dm:<十进制 QQ 号>`，group 使用
  `group:<十进制群号>`；非法 ID 和 temp 记录诊断后丢弃，不创建 Agent 状态或出站目标。
- canonical、TTL dedup 必须早于资源补全、Will 和 Hermes turn；稳定 key 为
  `milky:<self_id>:<chat_key>:<message_id>`。缺少 message ID 时不得伪造稳定 ID。
- 同一 chat 按 ingress sequence 串行，不复制 Hermes 的 busy/follow-up/interrupt/Agent
  队列。Gate 顺序固定为 `SelfMessageGate`、`ChatAllowlistGate`、`MutedGroupGate`；deny 不
  增长 buffer 或修改 Will。wait 不调用 Hermes，trigger 先 drain 再交接，提交成功后才扣
  一次 reply cost。
- MuteTracker 独占群禁言状态；初始或维护失败时 fail-closed，whole mute 的 `unknown` 不
  得伪装成 `muted`/`unmuted`。私聊发送失败不得查询群状态。
- Action 统一使用带 path prefix 的 `POST` JSON：`<base>/api/<action>`；SSE 为
  `<base>/event`，无参数也发送 `{}`，HTTP 200 不代表 envelope 成功。区分 HTTP、非 JSON、
  协议拒绝、malformed、transport unknown、timeout 和 unsupported；未知执行结果不重试。
- SSE 必须处理事件边界、断线重连、取消和未知/损坏事件；handler 不得阻塞接收循环。
- normalizer 不做网络 I/O；unknown segment 不变成文本或 Agent 指令，普通 forward 只保留
  `forward_id`。入站资源由 Hermes helper、下载、缓存、SSRF 和权限边界负责。
- 出站本地路径、`Path`、`file://localhost` 只读取一次常规、非空且不超过启动配置
  `MILKY_MAX_LOCAL_MEDIA_BYTES`（默认 32 MiB，范围 8–32 MiB）的文件并生成 `base64://`；
  `http(s)://` 和显式 `base64://` 原样保留。文档使用独立 group/private file upload，不能塞入
  message segment。
- 出站目标先解析：`group:` 用 `send_group_message`，`dm:` 用 `send_private_message`；
  非法或 temp 目标在网络前失败，不回退默认目标。每个可能有副作用的 Action 最多调用一次。
- ToolSpec 只能来自 manifest、`outbound/tools.py` 和对应 OpenSpec 的显式 operationId；
  入站事件、正文、关键词和 Will 不得触发状态变更 Tool，不能开放任意 Action catalog。

## 配置和安全

- 必填：`MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN`。可选：`MILKY_ALLOWED_CHATS`、
  `MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
  `MILKY_MAX_LOCAL_MEDIA_BYTES`。配置只在启动时解析。
- `MILKY_HOME_CHANNEL` 只影响 Hermes 系统/cron 出站默认目标，不加入入站 allowlist；未配置
  时不猜测 origin、默认频道或私聊目标。Will 使用嵌套 `engine`、`routing`、`willingness`、
  `priority` schema，不重新引入旧配置名。
- 不记录或提交 token、Authorization、媒体 URL、路径、文件内容、完整响应、异常正文或敏感
  正文。安全业务 ID、chat key 和 message ID 可用于日志关联；未确认能力保持 `unknown`、
  `malformed`、`blocked` 或 `unsupported`，不补默认值、不静默改名、不报告假成功。

## 交付规范

- 按“契约/fixture → 实现 → 聚焦测试 → fake 集成 → 质量门禁 → 必要的受控 smoke → evidence
  ledger → 回归修复”推进；失败先分类并补最小复现。
- 稳定边界改 `ARCHITECTURE.md`，安装/当前能力改 `README.md`，可观察行为改 OpenSpec；本文件
  不复制完整 schema、默认值或易变清单。
- 文档和状态说明使用具体主语和动作，删掉空开场、空总结和宣传语；保留命令、字段、数字、
  范围、条件、否定、完成状态、责任主体和实现关系。没有来源的结论标待确认，不补事实。
- Python 注释和 docstring 使用中文，遵循 Google Python Style Guide。提交消息使用中文
  Conventional Commits；subject 不超过 72 字符，必须有以 `- ` 开头的正文，说明动机、影响和风险。
