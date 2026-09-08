## 1. 契约与测试基线

- [x] 1.1 补充 dm 当前消息和历史消息的 body-only renderer 测试，覆盖无 header、换行编码、尖括号/反斜杠、空上下文，以及 group 当前/历史输出不变；验证方式：运行 renderer 和 wait buffer 聚焦测试并检查精确字符串。
- [x] 1.2 补充 fake Hermes pipeline 测试，覆盖无历史和有历史的 dm `MessageEvent.text`，确认最终 event.text 与日志可见的当前消息均无普通 header，且 dm `channel_context` 仍使用 resolved body；验证方式：运行 `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`。
- [x] 1.3 补充 dm reply、canonical、dedup、Gate、Will、资源和媒体字段回归断言；验证方式：确认 Agent-facing 文本无 header，但 `message_id`、`reply_to_message_id`、reply author、own-message、metadata 和 media 字段保持真实值。

## 2. 私聊普通消息 renderer

- [x] 2.1 将已确认 `dm:`/`group:` namespace 的 chat-aware 普通消息 renderer 同时用于当前消息和历史消息；dm 只输出 body，group 继续复用既有 header；验证方式：renderer 单元测试覆盖显式/一致 namespace、混用或缺失 namespace 失败、system event 固定格式。
- [x] 2.2 将 detached batch 的当前文本和 `inbound.hermes_mapper` 的 `MessageEvent.text` 接入共享 renderer；保持历史 resolved body、ingress 顺序、当前 group header 和 dm system event 行为不变；验证方式：fake Hermes 测试确认 dm 当前/历史均无 header，group 字节级不变。
- [x] 2.3 验证 dm body-only 文本与 Hermes 内部 metadata、资源解析、媒体代表和 reply 字段解耦；验证方式：运行现有 reply/media/pipeline 测试并确认没有因删除 header 而改变内部字段或资源调用。

## 3. 稳定契约同步

- [x] 3.1 更新 `ARCHITECTURE.md`，明确普通 dm 当前消息与历史消息均 body-only、普通 group 消息保留 header、system event 保留 `<event ...>`、内部 metadata 不变；验证方式：人工核对文档与聚焦测试输出一致。
- [x] 3.2 将 delta 同步到主 `openspec/specs/chat-session-buffer/spec.md` 和 `openspec/specs/hermes-message-pipeline/spec.md`，删除“当前 dm text 保留 header”的旧表述；验证方式：运行 OpenSpec strict validation 并检查 requirement/scenario 完整保留。

## 4. 质量门禁

- [x] 4.1 运行完整质量检查并修复回归：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`；验证方式：所有命令成功，记录既有真实 Hermes host skip 边界。
- [x] 4.2 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`；验证方式：新 change artifacts 和主规范通过 strict validation，并补充 evidence ledger。

## Evidence ledger

记录日期：2026-09-08（Asia/Shanghai）

### 已执行

- `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`：通过，50 passed（实现前基线）。
- `uv run pytest -q tests/test_canonical.py tests/test_gate_registry.py tests/test_resources.py tests/test_inbound_image_dedup.py tests/test_will_routing.py tests/test_hermes_pipeline.py tests/test_inbound_context_rendering.py tests/test_wait_buffer.py tests/test_slash_commands.py`：通过，159 passed。
- `uv run pytest -q`：通过，836 passed、2 skipped。
- `uv run pytest -q -rs`：通过，836 passed、2 skipped；skip 为既有 Hermes host 不可用（`tests/test_adapter_lifecycle.py:541`、`tests/test_multimedia_outbound.py:625`）。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，360 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，4 passed、0 failed。

### 行为证据

- renderer 单元和 wait buffer 测试证明 `dm:` 当前/历史普通消息只输出 body，并编码换行；`group:` 当前/历史仍保留原 header、字段顺序和 self-reply 文案；混用或缺失 namespace 被拒绝；system event 继续使用 `<event <event_type>> <body>`。
- fake Hermes pipeline 测试证明无历史和有历史的 dm `MessageEvent.text` 均无普通 header，历史使用 resolved body；真实 Milky message ID、reply metadata、own-message、metadata、media 字段和 group 文本保持不变。
- 测试保留 canonical、TTL dedup、Gate、Will、资源解析、媒体去重和 wait/trigger ingress 顺序回归；本 change 只改变 Agent-facing 普通 dm 文本。

### 未覆盖与 skip

- 未执行真实 Hermes host 或真实 Milky 服务集成；当前证据来自 fake Hermes、脱敏 fixture 和本地单元/集成测试，不能证明真实宿主日志的外部展示细节。
- 未执行真实 Milky 写入 smoke；本 change 不需要写入授权，且遵循 smoke 的默认只读边界。
- 所有 fixture、日志和证据均未记录 token、Authorization、真实 QQ、完整响应、媒体 URL、媒体路径或敏感正文。
