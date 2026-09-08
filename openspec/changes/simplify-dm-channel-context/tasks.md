## 1. 契约与测试基线

- [ ] 1.1 为 dm wait/trigger 历史上下文补充脱敏 fixture 和聚焦测试，覆盖 body-only 输出、无普通消息 header、正文换行编码、空历史，以及当前 `MessageEvent.text` 仍保留既有 header；验证方式：运行相关 dm context 测试并检查期望字符串。
- [ ] 1.2 为 dm 历史 reply、dm 与 system event 混排补充测试，并为同一批案例保留 group 输出不变断言；验证方式：运行 `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`。
- [ ] 1.3 分别为 `DetachedTriggerBatch.channel_context`、公开 `render_channel_context()`/`format_channel_context` 和资源解析后的 pipeline 历史输出增加同一 dm/group 案例断言；验证方式：确认三条出口的普通记录模板一致，且 resolved body 只出现在最终 pipeline 输出。

## 2. 私聊历史 renderer

- [ ] 2.1 抽出共享的 chat-aware context renderer 和有序合并分支，根据已确认的 `dm:`/`group:` chat namespace 选择模板；dm 普通记录只渲染经过现有 body 编码的正文，group 继续复用既有 header 行为；验证方式：renderer 单元测试覆盖 dm/group 分支、顺序、`None`、边界字符和缺少/混用 namespace 的失败行为。
- [ ] 2.2 将 `DetachedTriggerBatch.channel_context`、公开 `render_channel_context()`/`format_channel_context` 和 pipeline 的 `_render_resolved_history()` 全部接入共享 renderer；保持当前 `MessageEvent.text` 的普通消息 renderer、system event `<event ...>` 格式、ingress 排序和资源解析后正文不变；验证方式：端到端 fake Hermes 测试确认 dm `channel_context` body-only、group `channel_context` 字节级不变、当前 text 不变，并确认 pipeline 使用 resolved body。
- [ ] 2.3 验证 dm 历史不影响 Hermes 内部 reply metadata、canonical、dedup、Gate、Will 和媒体字段；验证方式：在现有 pipeline/reply/media 测试中检查内部字段和资源调用断言。

## 3. 契约文档同步

- [ ] 3.1 根据已验证实现同步 `ARCHITECTURE.md` 的 Context 规则，明确 group 普通历史 header、dm 普通历史 body-only、system event 固定格式和当前 text 不变；验证方式：人工核对文档与聚焦测试输出一致。
- [ ] 3.2 将本 change 的 delta 与已交付行为对齐到主 `openspec/specs/chat-session-buffer/spec.md` 和 `openspec/specs/hermes-message-pipeline/spec.md`；验证方式：运行 OpenSpec strict validation 并确认不存在旧的全 chat 单一格式表述。

## 4. 质量门禁

- [ ] 4.1 运行完整相关质量检查并修复回归：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`；验证方式：所有命令成功且无未预期 diff。
- [ ] 4.2 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`；验证方式：变更 artifacts 和主规范通过 strict validation，并记录任何真实集成未覆盖边界。
