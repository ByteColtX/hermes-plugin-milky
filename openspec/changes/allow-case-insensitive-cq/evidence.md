# Evidence ledger

记录日期：2026-09-09（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_cq_formatter.py tests/test_outbound_splitting.py tests/test_outbound.py`：通过，158 passed。
- `uv run pytest -q -rs`：通过，913 passed、3 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，394 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，3 passed、0 failed。
- `ruby` plugin manifest 解析：通过，`plugin.yaml: valid`。
- `uv run scripts/milky_smoke.py --help`：通过，仅检查帮助入口，未执行远端操作。
- Markdown 相对链接目标检查：通过。

## 行为证据

- formatter 测试覆盖 `[CQ:]`、`[cq:]`、`[Cq:]` 和 `[cQ:]` 的 at、reply、sticker image 转换，
  以及未知/非法/未闭合控制码的原始文本 fallback。
- splitting 测试覆盖大小写变体的完整 unknown CQ 候选、malformed CQ-like 文本和后续 `[SPLIT]`；
  完整候选受保护，损坏候选仍按普通文本分段。
- chunking、结构化 text segment、组合控制码、平台提示和 bundled CQ reference 均通过现有回归
  测试；未新增 Action、ToolSpec、配置项或远端请求。
- `ARCHITECTURE.md` 和 `README.md` 已补充 `CQ` 前缀大小写不敏感、类型/字段/真实 ID 约束及
  fallback 边界；主 OpenSpec 仍由当前未归档 change 的 delta 覆盖，未提前同步主规范。

## 未覆盖与边界

- `tests/test_adapter_lifecycle.py:637` 因 Hermes host unavailable 跳过；
  `tests/test_hermes_prompt_integration.py:17` 需要显式 `RUN_HERMES_INTEGRATION=1` 跳过；
  `tests/test_multimedia_outbound.py:625` 因 Hermes host unavailable 跳过。
- 未连接真实 Milky 服务，未发送消息、上传文件或执行其他远端写入；未使用 `--allow-write`。
- 测试、fixture 和本证据未记录 token、Authorization、真实 QQ/群身份、完整响应、媒体 URL、
  媒体文件路径或敏感正文。
