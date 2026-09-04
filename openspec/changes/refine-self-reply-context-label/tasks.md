## 1. 契约与展示视图

- [ ] 1.1 为 Agent-facing header 增加“实际展示的 reply 目标是否为当前 Bot”的安全视图字段或等价判定，并验证无引用、未知 sender 和缺少目标 ID 时不生成 `your_previous_msg`
- [ ] 1.2 将 current 消息、历史 `channel_context` 和通用 renderer 接入同一判定规则，并验证 Bot 自引用显示为 `reply_to your_previous_msg`、当前消息真实 `msg_id` 保留且字段顺序/转义不变

## 2. 回归测试

- [ ] 2.1 增加脱敏单元测试，覆盖 Bot 引用、引用他人、未知引用发送者、多个 reply、无引用以及 wait 历史引用 Bot 的 Agent-facing 文本
- [ ] 2.2 增加 pipeline/mapper 集成断言，验证 Agent-facing header 使用 `your_previous_msg`，同时 Hermes `reply_to_message_id`、reply author 和 `reply_to_is_own_message` 仍保留既有真实值
- [ ] 2.3 运行 `uv run pytest -q tests/test_wait_buffer.py tests/test_inbound_context_rendering.py tests/test_normalizer.py tests/test_canonical.py tests/test_hermes_pipeline.py`，确认普通他人引用和现有入站行为无回归

## 3. 质量门禁与交付证据

- [ ] 3.1 运行 `uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，记录结果并修复本 change 引入的失败
- [ ] 3.2 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认 proposal、delta spec、design 和 tasks 一致；将未执行真实 Milky/Hermes 实机验证的边界写入 evidence
