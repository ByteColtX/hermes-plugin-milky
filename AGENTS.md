# hermes-plugin-milky agent guide

这是 Hermes 的 Milky QQ directory plugin。Hermes 从根目录的 `plugin.yaml` 和
`__init__.py::register(ctx)` 加载它；`pyproject.toml` 只用于 uv 开发环境、质量检查和构建。

本文件按 [OpenAI GPT-5.6 官方提示词指南](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6)
保持精简。稳定协议和行为细节不在此重复。

## 事实来源与范围

- `ARCHITECTURE.md` 维护稳定模块边界、生命周期和所有权；`README.md` 维护安装、配置和当前能力；`openspec/` 维护可观察行为、测试要求和 change 进度；源码与测试提供当前实现证据。
- 按任务范围读取相关文档、源码、测试和未归档 change。未归档 change 是规划，不是已交付能力；只有实现、测试和 evidence ledger 已证实的行为才能写入当前能力。
- 发现实现、文档和契约冲突时，先定位差异，再更新正确的事实来源；不要从 OneBot v11 或旧代码推断 Milky 行为，也不要扩大任务范围。

## 工作边界

- 安全的本地读取、检查、编辑和测试可以直接执行。外部写入、破坏性操作、发布、合并或超出当前范围的动作，先完成可审阅结果，再请求确认。
- 回答、审查、诊断和报告任务不默认修改仓库；明确的实现任务完成后继续验证并报告结果。
- 根目录 `__init__.py::register(ctx)` 是唯一公开入口。import/register 阶段不得联网、建立 SSE 或创建长期任务；不得修改、替换或 monkey patch Hermes core。
- 不记录或提交 token、Authorization、完整响应、异常正文、媒体 URL、路径、文件内容或敏感正文；未确认能力保持 `unknown`、`malformed`、`blocked` 或 `unsupported`，不报告假成功。

## 实现时必须保留的边界

- 连接必须先完成登录、群列表和 Bot 群成员状态同步，再开放普通消息和 SSE；断开时取消并等待插件任务，释放事件流、pipeline、sender、MuteTracker 和 client。
- 普通 Agent 流程只处理 `message_receive`；canonical 和 TTL dedup 先于资源补全、Will 和 Hermes turn，缺少 `message_seq` 时不得伪造稳定 ID；同一 chat 按 ingress sequence 串行。
- 只接受已确认的 `dm:<十进制 QQ 号>` 和 `group:<十进制群号>` 目标。非法或 temp 目标在网络前失败，不回退其他目标；可能有副作用的 Action 最多调用一次。
- 入站资源、下载、缓存和 SSRF 边界由 Hermes 负责；出站本地资源遵守启动时的大小限制并只读取一次。工具只来自 manifest、`outbound/tools.py` 和显式 OpenSpec operationId，不开放任意 Action catalog，也不由正文、关键词、Will 或事件隐式触发状态变更。
- 保持既有 Gate、Will、MuteTracker、错误分类、日志和消息/媒体边界；具体顺序、字段、默认值和协议行为以 `ARCHITECTURE.md`、`README.md`、源码和相关 OpenSpec 为准。

## 常用命令与交付

Python 3.13+ 只使用 `uv`/`uvx`，不要调用 `python`、`python3`、`pip` 或 `pipx`。

```text
uv sync
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv build
git diff --check
npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict
```

按任务风险运行聚焦测试或完整质量门禁；只在 fake host 通过或被 skip 的检查，不算真实集成通过。smoke 使用 `uv run scripts/milky_smoke.py --help`，默认只读；发送或上传必须获得明确授权、使用 `--allow-write`，且目标命中运行时 `MILKY_ALLOWED_CHATS`。

交付前检查相关文档、manifest、实现、测试和 OpenSpec 的字段名、错误分类、默认值和状态一致。最终报告说明改动文件、验证命令及结果、skip/外部阻塞和仍待确认边界。

Python 注释和 docstring 使用中文，遵循 Google Python Style Guide。提交消息遵循 Conventional Commits：标题使用 `<type>[optional scope][!]: <description>`；正文和页脚可选，规范不规定其内容。项目约定 subject 使用中文、简洁且不超过 72 字符。
