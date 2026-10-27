# Tasks

## 1. 执行路径

- [x] 1.1 将固定 Action handler 的 Action 闭包改为接收 `sender` 参数，把 sender 选择收敛到 `_execute_action`；验证 live sender 已绑定时仍只调用该 sender，不创建新 client。
- [x] 1.2 在无 live sender 时按调用时 profile 配置创建一次性 `MilkyClient` 与 `MilkyOutboundSender`，执行本次 Action 后在 `finally` 中关闭；验证每次调用只发一次请求、成功后资源全部关闭。
- [x] 1.3 保持错误分类边界：参数错误仍为 `invalid_input`，配置不可读在网络前返回 `unsupported`，进入 HTTP 边界后无响应仍为 `transport_unknown` 且不重试。

## 2. 共用资源关闭

- [x] 2.1 抽取 `outbound/lifecycle.py::close_quietly`，让 `outbound/standalone.py` 与 `outbound/tools.py` 共用；验证 standalone 既有行为不变，清理异常不覆盖原始结果。

## 3. 测试与验证

- [x] 3.1 新增 `tests/test_tools_without_adapter.py` 覆盖一次性 client 成功、传输失败、配置不可读和 live 优先四条路径；移除 `tests/test_qq_tools.py` 中已过时的「未绑定即拒绝」断言。
- [x] 3.2 用本地 loopback HTTP server 走真实 HTTPX 路径验证 `send_profile_like` 在无 sender 时只发一次请求、携带 Bearer 并原样返回响应体；验证后删除临时脚本。
- [x] 3.3 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .` 和 `git diff --check`。

## 4. 文档与规范

- [x] 4.1 更新 `openspec/specs/qq-action-tools` 与 `openspec/specs/security-boundaries` 的 delta 语义，反映一次性 client 路径、单次请求和配置不可读分类。
- [x] 4.2 更新 `ARCHITECTURE.md`、`README.md`、`skills/milky-qq-action-tools/SKILL.md` 与 `CHANGELOG.md`。

## 5. 真实环境

- [x] 5.1 在目标 Hermes 部署的 cron worker 中验证 `send_profile_like` 真实可用；线上实测确认修复生效，不再返回 `tool is unavailable`。真实目标 QQ 号、响应正文与凭证不进入仓库记录。

## Workflow follow-up

- 完成实现和验证后，运行 `openspec validate --changes --strict`。
- 通过审阅后再归档该 change。
