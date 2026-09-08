## 1. 契约与测试基线

- [ ] 1.1 盘点并建立 `message_seq`、`msg_seq`、Hermes `message_id` 和 `ingress_sequence` 的边界断言，更新 canonical、pipeline、outbound、context 相关测试的预期接口；验证 `rg` 不遗漏受本 change 影响的旧诊断和 header 标签。
- [ ] 1.2 更新脱敏 fixture 与测试辅助对象中的稳定序号字段命名，保持 Milky wire fixture 的 `message_seq`、数值范围和缺失字段场景不变；验证 parser fixture 测试仍能覆盖正常、reply 和缺失序号消息。

## 2. 入站 canonical 与诊断

- [ ] 2.1 将插件 canonical 稳定身份、dedup helper 参数/局部变量和相关安全诊断从 `message_id` 迁移为 `message_seq`，使缺失序号只产生 `no_stable_message_seq`，不改变字符串规范化、TTL 时序或去重值；验证 `uv run pytest -q tests/test_canonical.py tests/test_milky_parser.py tests/test_observability.py`。
- [ ] 2.2 保持 Milky parser/model、reply segment、`get_message` 和 `recall_group_message` 的 wire/API 字段为 `message_seq`，并检查 resource、pipeline、日志关联字段只在插件内部按新术语表达而不泄漏敏感内容；验证相关协议 fixture 和 `uv run ruff check .`。

## 3. Agent-facing context 与 Hermes boundary

- [ ] 3.1 将 group 普通消息历史/current header 的标签从 `msg_id` 改为 `msg_seq`，保持 `reply_to`、自引用标签、转义、排序和 dm body-only 行为不变，并增加旧标签不存在的断言；验证 `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_wait_buffer.py`。
- [ ] 3.2 调整 canonical 到 Hermes 的映射，使确认的插件 `message_seq` 在 `MessageEvent.message_id`、`reply_to_message_id` 和 source metadata 的既有宿主边界正确落位，Hermes 字段名不改；验证 `uv run pytest -q tests/test_hermes_pipeline.py tests/test_inbound_context_rendering.py tests/test_slash_commands.py`。

## 4. 出站结果兼容映射

- [ ] 4.1 将 Milky client/插件侧发送成功结果命名为 `message_seq`，继续只接受远端 `data.message_seq`，并在 adapter sender 边界一次性映射为 Hermes `SendResult.message_id`；验证成功、缺字段、协议拒绝和 transport unknown 场景的既有错误分类测试。
- [ ] 4.2 更新 outbound sender、standalone/home channel、媒体 fake 和集成 fake 的字段断言，确保分块、forward、媒体和文件路径不产生本地伪造序号或 continuation ID；验证 `uv run pytest -q tests/test_milky_client.py tests/test_outbound.py tests/test_home_channel.py tests/test_multimedia_outbound.py`。

## 5. 文档与回归门禁

- [ ] 5.1 更新 `ARCHITECTURE.md`、`README.md`、主 specs 和相关开发说明，明确 Milky `message_seq`、Agent header `msg_seq`、Hermes `message_id` 与 `ingress_sequence` 的边界，并记录 `msg_id`/`no_stable_message_id` 的迁移影响；验证文档中的协议字段与实现行为一致。
- [ ] 5.2 运行完整质量门禁并修复本 change 引入的问题：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`；确认未修改 Hermes core、Milky wire contract 或敏感日志边界。
