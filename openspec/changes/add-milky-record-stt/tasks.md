## 1. 契约与测试夹具

- [ ] 1.1 补充脱敏的纯 `record`、多 `record`、`record` 与文本/图片混合、资源 materialization 失败和历史 `channel_context` 场景夹具；验证夹具不包含凭证、真实媒体 URL、本地路径或敏感正文。
- [ ] 1.2 在 mapper/resolver 测试中固定 `media_urls` 与 `media_types` 的音频路径/MIME 配对、成功与失败 occurrence 的区分以及历史 record 不进入本次媒体输入；验证 `uv run pytest -q tests/test_resources.py tests/test_hermes_pipeline.py` 的新增断言可独立复现契约。

## 2. MessageEvent 映射实现

- [ ] 2.1 调整当前消息类型判定：纯 `record` 且至少一个音频已成功 materialize 时使用 Hermes `MessageType.VOICE`，混合消息和非音频附件继续按现有规则处理；验证纯 record、record+text、record+image 和 record+file 的类型及媒体数组回归测试通过。
- [ ] 2.2 在当前 Agent-facing 文本生成边界按 typed record reference slot 移除成功 materialize occurrence 的 `[record:NOT SUPPORTED]`，保留失败 occurrence、资源诊断和历史 renderer 的既有 placeholder；验证多 record 成功/失败混合时不会全局误删或错配。
- [ ] 2.3 保持 record 的资源解析只使用 Hermes audio helper 和既有本地路径过滤，不新增 Milky STT provider、配置项、下载缓存或远端 URL 写入；验证 resolver 的 Action/helper 调用和安全降级测试通过。

## 3. Hermes core 交接验证

- [ ] 3.1 使用 fake Hermes `MessageType` 和 `MessageEvent` 验证纯 record 事件以 `VOICE`、本地 audio `media_urls` 和等长 `media_types` 交接，且事件正文不包含插件 STT 提示；验证 `uv run pytest -q tests/test_hermes_mapper.py tests/test_hermes_pipeline.py`（按仓库实际测试文件调整）通过。
- [ ] 3.2 验证 core 侧 STT 配置状态不被插件读取或改写：成功、未配置/禁用、provider 失败和空转录只由宿主处理，插件不追加重复提示；验证 fake host 只检查事件输入，真实 provider 结果保留为受控实机 evidence。
- [ ] 3.3 验证历史 record 仍只保留在既有 `channel_context` 文本策略中，不被自动 STT、不新增历史 `media_urls`，且当前 record 不进入 `channel_context`；验证对应 pipeline context 测试通过。

## 4. 回归与交付检查

- [ ] 4.1 运行聚焦测试、`uv run ruff check .`、`uv run ruff format --check .` 和 `git diff --check`，修复本 change 引入的失败。
- [ ] 4.2 运行 `uv run pytest -q`、`uv build` 和 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`；记录测试、fake host 限制和真实 Hermes/Milky STT 未覆盖边界，确认未修改 Hermes core。
