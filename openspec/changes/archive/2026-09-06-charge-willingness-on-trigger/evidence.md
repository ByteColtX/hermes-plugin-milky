# Evidence ledger

记录日期：2026-09-06（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_will_willingness.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`：通过，42 passed。
- `uv run pytest -q -rs`：通过，813 passed，2 skipped；skip 为当前测试环境没有 Hermes host 的
  `tests/test_adapter_lifecycle.py:485` 和 `tests/test_multimedia_outbound.py:625` 集成测试。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，314 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，3 passed、0 failed。

## 语义覆盖

- 聚焦回归覆盖 trigger 决策完成后立即扣除一次 `replyCost`、连续同 chat 状态可见、wait/Gate deny
  和非普通事件不扣费，以及资源解析、映射或 Hermes 交接失败后不回滚扣费。
- 相关 OpenSpec delta 已合并到 `hermes-message-pipeline` 与 `will-willingness` 主 spec，并通过
  `npx --yes @fission-ai/openspec@1.12.0 validate --specs`。

## 未覆盖与边界

- 未执行真实 Milky/Hermes 连接；当前证据来自 fake host、fake client 和脱敏测试 fixture，不能替代
  目标部署环境的连接、容量或消息链路验证。
- 未执行真实消息发送、上传或其他远端写入；发布授权不扩展为 QQ 写入 smoke 授权。
- 测试和证据未记录 token、Authorization、完整响应、媒体 URL、本地路径或敏感正文。
