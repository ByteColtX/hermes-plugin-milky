# Evidence ledger

## Baseline（修复前）

- `outbound/tools.py` 的 26 个固定 Action handler 在 `_ACTIVE_SENDER is None` 时直接返回
  `_tool_error("unsupported")`，对外 JSON 为
  `{"ok":false,"classification":"unsupported","error":"tool is unavailable"}`。
- `_ACTIVE_SENDER` 只在 `MilkyAdapter._bind_sender`（`adapter.py:830-837`）绑定，断开时
  `_unbind_sender` 清空。
- Hermes cron 的 managed 部署在独立 worker 进程执行 job
  （`cron/scheduler.py::_launch_external_cron_worker`），该进程不物化 Milky 平台，
  `_ACTIVE_SENDER` 恒为 `None`，因此全部固定工具不可用。
- 用户安装的 platform 插件在 worker 中由 `gate_manifest` 判定为 `load`，`register(ctx)`
  会执行并注册全部工具；失败点不在注册，而在 handler 对 live sender 的硬依赖。

## Verification

- `uv run pytest -q tests/test_tools_without_adapter.py`：4 passed。
- `uv run pytest -q tests/test_tools_without_adapter.py tests/test_qq_tools.py tests/test_outbound.py tests/test_home_channel.py`：175 passed。
- `uv run pytest -q`：1488 passed, 6 skipped；skip 为需要 Hermes host 或显式启用的真实集成。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`：全部通过。
- `uv run openspec validate fix-fixed-tools-without-live-adapter --type change --strict`：valid。
- `uv run openspec validate --specs`：30 passed。
- 本地 loopback HTTP smoke（真实 HTTPX，无 live sender）：`send_profile_like` 只发一次
  `POST /milky/api/send_profile_like`，携带 Bearer，body 为 `{"user_id":...,"count":10}`，
  响应体原样返回；临时脚本已删除。

## Real environment

- 线上实测确认由 cron 发起的 QQ 名片赞可用，不再返回 `tool is unavailable`。
- 真实目标 QQ 号、响应正文、token 和 Authorization 不进入仓库记录。

## Retained boundaries

- `sticker_send` / `sticker_search` 仍要求当前 Milky task-local 会话；cron 无会话上下文时
  返回 `unsupported` 是正确语义，不在本次修复范围。
- 有 live adapter 时仍复用已绑定 client，行为不变。
