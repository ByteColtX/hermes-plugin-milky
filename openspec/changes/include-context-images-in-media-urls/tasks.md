## 1. 契约与脱敏 fixture

- [x] 1.1 扩展 resolved trigger batch 的 fake fixture，覆盖两条历史 context 图片、两条当前 trigger 图片、重复本地路径及当前非图片附件；验证 fixture 只使用合成路径、MIME 和消息内容
- [x] 1.2 增加历史图片 materialization 失败、未 materialize 和嵌套 reply 图片未出现在 context 的 fixture；验证失败图片不产生媒体输入且不泄露远端 URL 或完整本地路径

## 2. 结构化资源结果

- [x] 2.1 在资源解析结果中保留每条消息正文实际展示的直接图片 materialization，并与当前消息既有附件集合区分；验证历史音频、视频、文件、未知引用和未展示嵌套图片不会成为历史 context 图片
- [x] 2.2 保持历史与当前资源 helper 的完成边界及失败降级；验证 mapper 只接收通过 Hermes helper 和本地路径校验的结果

## 3. Hermes 媒体交接

- [x] 3.1 将历史 context 图片和当前 trigger materialization 按“历史 context 图片在前、当前消息附件随后”的稳定顺序合并；验证当前图片顺序和既有非图片附件行为不变
- [x] 3.2 对合并后的有效本地路径按首次出现去重，并同步生成等长、同序的 `media_types`；验证跨历史/当前重复路径不会产生孤立类型项
- [x] 3.3 通过结构化参数把历史图片候选交给 mapper，不解析 `channel_context` 文本或写入未经确认的 URL/路径；验证正文、`channel_context` 和媒体输入职责仍然分离

## 4. 回归与质量门禁

- [x] 4.1 增加 mapper 和 pipeline 集成回归，验证历史两图与当前两图全部进入 `media_urls`、顺序正确、重复路径只保留首次项，且当前消息不进入 `channel_context`
- [x] 4.2 覆盖无历史图片、helper 失败、重复图片、历史非图片附件、friend/group 两类 chat 和既有当前音频/视频/文件行为；验证安全降级和兼容性
- [x] 4.3 运行相关测试：`uv run pytest -q tests/test_hermes_pipeline.py tests/test_resources.py tests/test_inbound_context_rendering.py`，并记录结果
- [x] 4.4 运行完整质量门禁：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`；记录结果并按协议、资源、Hermes API、并发或安全分类失败
- [x] 4.5 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，确认 proposal、delta specs、design 和 tasks 一致；未获明确授权时不执行真实 Milky 写入或发送 smoke

## Evidence ledger

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `AGENTS.md`、`ARCHITECTURE.md`、相关主 specs 以及本 change 的 proposal、delta specs、design、tasks | 已完成 | 等待 apply workflow 执行 fixture、实现和回归 |
| fixture/资源 | `uv run pytest -q tests/test_hermes_pipeline.py tests/test_resources.py tests/test_inbound_context_rendering.py` | 36 passed；覆盖历史/当前顺序、路径去重、直接图片与嵌套 reply、失败占位 | 资源和媒体边界通过；继续完成全量门禁 |
| 质量门禁 | `uv run pytest -q`；`uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check` | 526 passed, 22 skipped；Ruff、format（206 files）、build、diff check 均通过 | 未发现协议、资源、Hermes API、并发或安全失败 |
| OpenSpec | `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` | 3 passed, 0 failed | change artifacts 一致；未执行真实 Milky 写入或发送 smoke |
