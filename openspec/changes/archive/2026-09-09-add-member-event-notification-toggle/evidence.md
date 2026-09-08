# Evidence ledger

记录日期：2026-09-08（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_config.py tests/test_protocol_fixtures.py tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py`：通过，147 passed；覆盖启动配置、英文系统事件、payload 字段过滤、context renderer、关闭/成功注入/拒绝注入路径和 protocol fixture 回归。
- `uv run pytest -q`：通过，864 passed，3 skipped。
- `uv run pytest -q -rs`：3 个 skip 均为受控外部边界：Hermes host unavailable、真实 Hermes prompt integration 需显式 `RUN_HERMES_INTEGRATION=1`、Hermes multimedia host unavailable。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，1 change validated，0 failed。
- 修复后 `uv run pytest -q tests/test_adapter_lifecycle.py tests/test_hermes_pipeline.py tests/test_inbound_context_rendering.py`：通过，63 passed，1 skipped；覆盖入群和退群即时注入及持久化 session route 恢复。
- OrbStack `hermes-dev` 受控重启后 `hermes_plugins.milky.adapter` 记录 `stage=session operation=restored classification=accepted session_count=7`，Gateway 状态为 active；未发送或重放真实群成员事件。

## 边界与未覆盖

- 未连接真实 Milky 服务；未发送消息、上传文件或执行任何远端写入。
- Hermes session key 和 `inject_message` 交接使用 fake host 与 adapter 边界测试；当前环境未提供真实 Hermes Gateway，因此未宣称实机注入成功。
- 测试、fixture 和 evidence 未写入 token、Authorization、真实 QQ/群身份、媒体 URL、文件路径、完整响应或敏感正文。
