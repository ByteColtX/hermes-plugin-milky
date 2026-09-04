## 1. 契约与测试夹具

- [ ] 1.1 建立脱敏 `[SPLIT]` fixture，覆盖 LF/CRLF 独立行、大小写变体、前后空格、行内文本、空段、相邻标记、三段以上文本和无标记普通文本，并验证只有严格独立行命中
- [ ] 1.2 建立分段出站边界测试数据，覆盖逻辑段合并、既有长度分块、物理消息超过三条时的网络前整体拒绝，以及 CQ-compatible 内容在各段内保持顺序，并验证 fixture 不含凭证、真实 QQ 号、媒体 URL 或本地路径
- [ ] 1.3 建立 fake Hermes/Milky 有序交接 fixture，记录文本 Action、图片/语音/视频 Action 和文件 upload 的脱敏事件序列，并验证文本先于附件、附件按提取顺序投递且无交错猜测

## 2. `[SPLIT]` 文本出站实现

- [ ] 2.1 实现只在统一 formatter 前运行的严格独立行解析，并验证有效标记被删除、空段不发送、相似文本原样保留且不触发 CQ 或媒体副作用
- [ ] 2.2 将有效分段接入普通文本发送路径：先形成最多三个逻辑文本单元，再应用既有长度分块和总数预检，并验证首个网络 Action 前即可拒绝超过三条、空内容和非法目标
- [ ] 2.3 按序串行发送预检通过的文本单元，并验证中间 Action 失败时保留已成功结果和首个安全分类、不发送后续单元、不重试或 fallback
- [ ] 2.4 验证无有效 `[SPLIT]` 的普通长文本、CQ-compatible 片段、group/dm 路由、媒体 native segment、独立文件 upload 和现有 SendResult 语义保持回归通过

## 3. 媒体顺序与 Agent-facing 指引

- [ ] 3.1 在 fake Hermes 交接测试中验证“文本分段全部完成后再发送 MEDIA 附件”的可观察顺序、多个附件的提取顺序、附件失败的部分结果和不交错边界；验证 plugin 不从原始正文位置推断附件顺序
- [ ] 3.2 更新 `PLATFORM_GUIDANCE`，加入 `[SPLIT]` 的独立行/大小写/三条/空段说明、文本先于附件且暂不支持交错的说明，并将 `NO_REPLY` 替换为 `[SILENT]`；验证 `[SILENT]` 不触发插件解析或 Milky Action
- [ ] 3.3 更新 system prompt、入口注册和文案相关测试，验证 Milky section 包含新指引、静态 platform hint 不重复承载正文、动态身份行为不变且其他平台不受影响

## 4. 文档、质量门禁与证据

- [ ] 4.1 更新 `ARCHITECTURE.md` 和 `README.md`，明确严格 `[SPLIT]` 语法、最多三条文本消息、附件先后顺序、当前不支持交错和 `[SILENT]` 由 Hermes core 处理，并验证文档不引入未确认能力或敏感数据
- [ ] 4.2 运行聚焦测试 `uv run pytest -q tests/test_outbound.py tests/test_multimedia_outbound.py tests/test_model_control_integration.py tests/test_plugin_entry.py` 及新增测试文件，并将结果或最小失败复现写入 change evidence ledger
- [ ] 4.3 运行完整质量门禁 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，确认无 Hermes core 修改、无凭证和无真实媒体写入
- [ ] 4.4 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，记录通过结果、fake host/真实 Hermes 边界和任何跳过项；未经明确授权不执行真实 Milky 消息发送或文件上传 smoke
