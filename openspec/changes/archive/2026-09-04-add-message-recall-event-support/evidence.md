# Evidence ledger

记录日期：2026-09-04（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_protocol_fixtures.py tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py tests/test_observability.py tests/test_slash_commands.py`：通过，107 passed。
- 撤回解析测试覆盖 friend/group chat key、群员自撤回、群管理员撤回、好友操作人文案、null/缺失 `operator_id`、未知字段过滤、非法 ID、`temp` 和未知场景。
- fake Hermes pipeline 测试覆盖普通 wait、撤回和 nudge 的 ingress 顺序、friend/group 命名空间隔离、system context FIFO 溢出和下一次 trigger 一次性消费。
- observe-only 测试确认撤回事件不创建普通 Hermes MessageEvent、Will 输入、reply cost、资源请求或独立 Agent turn；失败交接只记录安全失败，不回填撤回上下文。
- `npx --yes @fission-ai/openspec@1.12.0 validate add-message-recall-event-support --type change`：通过，change valid。
- `uv run pytest -q`：通过，727 passed，2 skipped；skip 为既有真实 Hermes host 未提供的集成测试。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，266 files already formatted。
- 格式检查首次发现 3 个新增/修改文件未格式化，已执行定向 `uv run ruff format` 修复；未留下未分类失败。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，6 passed、0 failed；输出中的两条 archive 信息提示属于其他 active change，不属于本 change。

## 未覆盖与边界

- 未执行真实 Milky/Hermes host 连接；fixture 和 fake host 结果不能替代真实服务能力验证。
- 未执行真实消息发送、文件上传、撤回或其他远端写入；本 change 未新增 Action、ToolSpec 或配置项。
- `message_recall` 只展示已确认的撤回元数据，不调用 `get_message`，不恢复被撤回消息正文，也不引入事件恢复游标或系统事件 dedup。
