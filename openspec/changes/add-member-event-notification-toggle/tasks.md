## 1. 配置与入站边界

- [x] 1.1 在启动配置中增加 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 的大小写不敏感布尔解析，默认值为 `false`，非法值启动失败，并将安全摘要与配置对象测试补齐；验证 `uv run pytest -q tests/test_config.py` 覆盖未配置、`true`/`false` 变体和非法值。
- [x] 1.2 将解析后的成员事件开关沿 adapter pipeline 构造路径传递：成员事件始终进入 system context，关闭时不追加 Tip 且不即时注入，开启时追加 Tip 并调用已确认 session key 的 Hermes `inject_message`；验证关闭留存、成功注入后 drain、注入拒绝时保留缓冲且不重复触发。

## 2. 英文事件文案与上下文契约

- [x] 2.1 将 `group_nudge`、`friend_nudge`、`message_recall`、群成员增加和群成员减少的 body 改为 delta spec 中的固定英文模板，并让 `Tip` 仅在通知开启时追加；保留可选字段省略和未确认字段过滤；验证 `tests/test_inbound_context_rendering.py` 覆盖五类事件及 recall 操作人分支。
- [x] 2.2 更新协议 fixture 与 `channel_context` 断言，确认 `<event <event_type>>` 前缀仍由上下文格式统一添加、关闭时基础 body 留在缓冲、开启时 Tip 随注入内容消费，且英文 body 不包含 payload 中的 display 文本、URL、timestamp 或 raw 扩展；验证 `uv run pytest -q tests/test_protocol_fixtures.py tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py`。

## 3. 运行文档与实现边界

- [x] 3.1 更新 `README.md` 的环境变量和当前能力说明，明确开关默认关闭、`true` 的启用方式、启动期读取、无 Tip 缓冲和开启后的即时通知语义；验证文档中的变量名、默认值与配置测试一致。
- [x] 3.2 更新 `ARCHITECTURE.md` 的系统事件、配置表和 Hermes 交接边界，明确关闭时等待普通消息、开启时只通过已确认 session key 的 `inject_message` 触发，且不猜测 session key 或直接调用 Milky Action；验证文档不引入未经确认的 Hermes core 能力。

## 4. 回归与交付验证

- [x] 4.1 运行受影响的配置、系统事件、pipeline、Hermes injection fake 和协议 fixture 测试，并修复回归；验证命令 `uv run pytest -q tests/test_config.py tests/test_protocol_fixtures.py tests/test_inbound_context_rendering.py tests/test_hermes_pipeline.py` 通过。
- [x] 4.2 运行项目质量门禁 `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`；验证所有命令成功且不提交 token、真实 QQ 身份、媒体路径或敏感正文。
