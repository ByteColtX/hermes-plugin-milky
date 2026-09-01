## 1. 契约与脱敏 fixture

- [x] 1.1 增加普通消息单行 context fixture，覆盖 sender、uid、msg_id、reply_to 缺省和边界字符，并验证上下文记录不会被换行或尖括号打断
- [x] 1.2 扩展 14 类 incoming segment fixture 的预期正文，覆盖 `market_face`、`light_app`、`xml`、可变嵌套 `meta` 和缺少 `meta` 的降级，并验证不依赖固定 meta 字段集合
- [x] 1.3 增加 `group_nudge`、`friend_nudge`、`group_member_increase` 和 `group_member_decrease` 的脱敏事件 fixture，覆盖可选 Details 字段、字段缺失和非法 chat key 分类
- [x] 1.4 建立 forward 不自动查询的 fake client 断言和系统 context 顺序预期，验证 fixture 不包含凭证、真实 QQ、完整 live 正文或媒体 URL

## 2. 普通消息与 segment 展示

- [x] 2.1 将普通消息和当前 trigger 的渲染改为单行尖括号格式，保留可选字段顺序和边界字符转义，并验证历史只进入 `channel_context`、当前消息只进入正文
- [x] 2.2 为 face、image、record、video、file、forward、market_face、light_app 和 xml 实现契约规定的 placeholder，验证 segment 顺序、缺失标识和未知 segment raw-only 行为
- [x] 2.3 实现 `light_app.json_payload` 的 JSON 解析与 `meta` 根投影，递归保留 `meta` 全部字段和值、忽略其他顶层字段，并验证 malformed/missing meta 使用 `NOT SUPPORTED`
- [x] 2.4 更新 Hermes mapper 和 channel context 集成断言，验证普通消息、结构化 placeholder 和 reply header 能正确交给 `MessageEvent`

## 3. 系统事件 context-only 注入

- [x] 3.1 增加按 chat 隔离且有界的 system context 状态，分配 ingress sequence、按 FIFO 淘汰并在 drain 后原子清除，验证不同 chat 不串扰且溢出有诊断
- [x] 3.2 实现 nudge 和群成员变更的可读事件渲染，验证 group nudge 使用双 UID、friend nudge 使用好友 UID、成员变更使用协议字段 JSON Details 且可选字段缺失时省略
- [x] 3.3 将 context-only 事件接入 observe pipeline，验证事件不经过普通 canonical、dedup、Gate、Will、reply cost 或独立 Hermes turn
- [x] 3.4 在 trigger 交接时按 ingress sequence 合并普通 wait 历史和 system context，验证只注入一次、当前 trigger 不重复进入 `channel_context`、无上下文时保持 `None`

## 4. 引用查询边界

- [x] 4.1 移除普通 trigger resolver 对 `get_forwarded_messages` 的自动调用，保留 `forward_id` placeholder 和诊断边界，并验证 reply 补全仍按 inline/缺失状态执行
- [x] 4.2 更新资源和 pipeline 集成测试，验证 forward 不产生远端查询或嵌套正文，媒体/file/reply 的既有分类行为不被改变

## 5. 文档与质量门禁

- [x] 5.1 更新 `ARCHITECTURE.md`、`README.md` 和本 change 证据台账，说明单行上下文、light_app meta、context-only 事件和 forward 查询边界，并标记尚未实现的能力
- [x] 5.2 运行入站、segment、资源、会话、事件流和集成测试，验证新旧行为的回归结果并按格式、协议、资源、并发或安全分类失败
- [x] 5.3 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，记录真实命令结果
- [x] 5.4 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证 proposal、delta specs、design、tasks 一致；未获明确授权时不执行真实 Milky 写入或发送 smoke

## 6. 实测回归修复

- [x] 6.1 审计所有入站正文和资源替换路径，移除完整 reply 的 `[引用]` 成功占位符，并将失败 reply 统一为类型化降级
- [x] 6.2 增加实测样例回归，验证 reply header 保留目标、正文不重复引用标记，其他 segment 不出现旧 placeholder

## 7. 图片占位符与 Hermes 落盘文件名对齐

- [x] 7.1 增加 image helper basename 的单图、多图顺序和失败降级契约测试
- [x] 7.2 在 trigger 资源成功解析后使用 helper 返回路径 basename 重写对应 image placeholder，并保持 `media_urls` 顺序一致
- [x] 7.3 更新文档和证据台账，运行相关测试、完整质量门禁与 OpenSpec strict 校验

## Evidence ledger

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `AGENTS.md`、`ARCHITECTURE.md`、现有主 specs、已完成媒体 change artifacts，并通过 Milky OpenAPI MCP 核对 v1.3.0 的 segment/event 枚举 | 已完成 | 新范围固定为入站 context 渲染、`light_app.meta`、forward 查询边界和 context-only 系统事件 |
| fixture/实现 | `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_protocol_fixtures.py` | 17 passed | 已覆盖单行 context、14 类 segment、可变 `meta`、系统事件字段和脱敏边界 |
| 集成 | `uv run pytest -q tests/test_inbound_context_rendering.py tests/test_normalizer.py tests/test_canonical.py tests/test_resources.py tests/test_wait_buffer.py tests/test_admission.py tests/test_milky_event_stream.py tests/test_hermes_pipeline.py tests/test_protocol_fixtures.py` | 113 passed, 2 skipped | 格式、协议、资源、并发和安全相关回归未发现失败 |
| 质量门禁 | `uv run pytest -q`；`uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check` | 522 passed, 22 skipped；其余均通过 | 未执行真实 Milky 写入或发送 smoke |
| OpenSpec | `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` | 2 passed, 0 failed | 未执行真实 Milky 写入或发送 smoke；change artifacts 一致 |
| 实测回归修复 | `rg` 运行时 placeholder 审计；`uv run pytest -q tests/test_inbound_context_rendering.py tests/test_normalizer.py tests/test_resources.py tests/test_hermes_pipeline.py`；混合 reply 回归 | 未发现旧类型 placeholder；42 passed | 完整 inline reply 仅保留 `reply_to` header；移除 resolver 中会误删其他失败 reply 标记的旧兼容分支 |
| 图片占位符回归 | `uv run pytest -q tests/test_resources.py tests/test_inbound_context_rendering.py tests/test_normalizer.py tests/test_hermes_pipeline.py`；`uv run pytest -q`；Hermes core `gateway/platforms/base.py` 只读核对 | 44 passed；全量 522 passed, 22 skipped；确认 helper 使用 `img_<12位随机十六进制><ext>` | 成功图片占位符改用 helper 返回 basename；失败时使用 `[img:NOT SUPPORTED]`；未执行真实 Milky 写入或发送 smoke |
