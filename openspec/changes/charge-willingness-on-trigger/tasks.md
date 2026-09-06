## 1. Will 反馈语义

- [x] 1.1 将 willingness reply-cost 反馈入口的说明和调用语义改为“trigger 参与成本”，保留 per-chat 隔离、一次扣费和不回滚规则；用 `tests/test_will_willingness.py` 的状态与扣费测试验证分数计算未改变
- [x] 1.2 确认 routing engine、wait、Gate deny、命令、temp 和系统事件不进入 willingness 扣费路径；用对应 pipeline/routing 回归测试验证无额外扣费

## 2. Trigger pipeline

- [x] 2.1 在同 chat admission 内、Will 返回 `trigger` 后立即执行一次 reply cost，再 drain buffer 和启动 detached handoff；移除 handoff 完成后的重复扣费；用连续 trigger 测试验证后续决策读取已扣分状态且一次 trigger 只扣一次
- [x] 2.2 保留资源解析、mapper、Hermes `handle_message()` 和 Agent 解耦行为，并使这些后续失败不回滚已执行扣费；用失败 resolver、mapper 或 Hermes 提交 fixture 验证扣费仍然保留
- [x] 2.3 调整 reply-cost 日志和 pipeline 计数，使其表示已执行的 trigger 扣费而非成功 handoff；用日志断言和成功/失败交接测试验证不重复记录

## 3. 契约、文档与回归

- [x] 3.1 更新 `ARCHITECTURE.md`、`README.md` 或其他受影响行为说明，明确 replyCost 在 trigger 决策时扣除且不等待最终发送；用文档搜索确认旧的“提交成功后扣费”表述已移除或改为历史说明
- [x] 3.2 运行 `uv run pytest -q tests/test_will_willingness.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`，确认 focused 回归通过
- [x] 3.3 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，确认完整质量门禁通过
- [x] 3.4 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认 change artifacts 与实现前契约一致
