## 1. 契约与 fixture

- [ ] 1.1 为 `message_recall` 补充脱敏的 group、friend、可选 `operator_id` 和非法字段 fixture，并更新协议 fixture 索引；运行 `uv run pytest -q tests/test_protocol_fixtures.py` 验证所有 fixture 均被登记且不含凭证、URL、路径或敏感正文。
- [ ] 1.2 为撤回事件解析补充单元测试，覆盖 `message_scene` 到 `dm:`/`group:` 的映射、群员自撤回文案、管理员撤回群员文案、好友事件的无角色文案、未知字段过滤、`temp`/未知场景和非法 ID fail-closed；运行对应聚焦测试验证 `malformed`/`observe_only` 分类准确。

## 2. 系统事件与上下文实现

- [ ] 2.1 扩展系统事件解析，使字段完整的 `message_recall` 生成 context-only 记录，并复用既有 ID 校验和安全渲染边界；运行系统事件测试验证无 `operator_id` 时使用 `uid <sender_id> 撤回了消息 msg_seq <message_seq>`，有 `operator_id` 时使用 `管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`。
- [ ] 2.2 将合法撤回记录接入既有 per-chat admission 和 context FIFO，验证 friend/group 命名空间隔离、与普通 wait/其他系统事件的 ingress 顺序、容量溢出和下一次 trigger 一次性消费；运行 `uv run pytest -q tests/test_hermes_pipeline.py tests/test_inbound_context_rendering.py tests/test_wait_buffer.py` 验证上下文结果。
- [ ] 2.3 验证撤回事件仍保持 observe-only：不创建 canonical、Gate/Will 状态、reply cost、资源请求、普通 Hermes MessageEvent、独立 Agent turn 或 `recall_group_message` Action；运行 pipeline、slash command 和 observability 回归测试验证无额外调用及安全日志。
- [ ] 2.4 验证包含撤回事件的 detached context batch 在交接失败时只重试同一批次或记录安全失败，不自动重复追加；运行 fake Hermes 失败路径测试验证不会产生重复上下文或 Agent turn。

## 3. 文档与契约一致性

- [ ] 3.1 更新 `ARCHITECTURE.md` 和 `README.md` 的系统事件说明，明确 `message_recall` 的 SSE 来源、上下文展示格式、observe-only 边界及“不恢复撤回正文”的限制；运行文档检索和 OpenSpec 校验确认没有宣称未验证的真实服务能力。
- [ ] 3.2 对照 active delta spec 检查实现、fixture、测试和文档的字段名、分类、chat key、顺序与副作用边界一致；运行 `npx --yes @fission-ai/openspec@1.12.0 validate add-message-recall-event-support --type change` 验证 change 工件有效。

## 4. 回归与交付证据

- [ ] 4.1 运行撤回事件相关聚焦测试，至少覆盖 `tests/test_protocol_fixtures.py`、系统事件解析、`tests/test_hermes_pipeline.py`、`tests/test_inbound_context_rendering.py`、`tests/test_wait_buffer.py`、`tests/test_observability.py` 和 `tests/test_slash_commands.py`，并将结果写入 evidence ledger。
- [ ] 4.2 运行完整质量门禁 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；记录失败分类，不把 fake host 结果或 skip 宣称为真实 Hermes/Milky 集成通过。
- [ ] 4.3 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，记录 active changes 的校验结果、真实 host 未覆盖边界及未执行真实消息发送、上传、撤回或其他写入操作。
