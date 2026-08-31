## 1. 契约和合成资料

- [x] 1.1 对照本 change 与现有主 spec，确认只保留日志、Tool 原样回显、Hermes 资源所有权和合成资料四个范围；验证：HTTP/SSE、allowlist、持久化和发布流程没有新增实现任务
- [x] 1.2 建立只含合成身份、占位正文、占位资源和合成协议值的 fixture/helper；验证：测试资料不包含真实 token、真实身份、真实正文、真实媒体引用或 live 响应
- [x] 1.3 通过 Hermes 源码或既有测试 contract 确认实际资源入口；验证：记录已确认入口，未确认的能力明确测试为 `unsupported`，不发明通用 seam

## 2. 日志和 Tool

- [x] 2.1 移除业务 ID、chat key、message ID 和昵称的日志掩码，但不新增凭证过滤器；验证：日志测试断言业务值原样出现，认证 header 不作为日志调用参数
- [x] 2.2 让已注册 Tool 的日志记录 Tool 名称、调用入参和远端结果；验证：日志捕获测试断言入参和结果不摘要、不改名、不掩码、不删除未知业务字段
- [x] 2.3 让已注册 Tool 的成功结果原样返回当前调用方，保留完整 envelope 和未知字段；验证：fake response 与调用方收到的结果结构和值一致，Tool 结果没有 DTO 重构
- [x] 2.4 保持参数错误、未注册 Action 和无远端响应使用既有错误分类；验证：失败测试不伪造远端成功结果，也不触发额外 Action

## 3. Hermes 资源边界

- [x] 3.1 删除入站和出站插件侧 URL 下载、远端 bytes 读取、本地文件读取、媒体缓存、下载目录、路径拼接和 `base64://` fallback；验证：网络/文件读取测试桩被触发时，插件不调用这些路径并返回 `unsupported`
- [x] 3.2 将 trigger 资源引用交给已确认的 Hermes core 入口，并保留 reply、forward、图片、语音、视频和文件失败占位；验证：wait 阶段不访问资源，trigger 只使用 core 返回结果
- [x] 3.3 将 Hermes materialized 出站资源交给对应 native media 或独立文件 upload Action；验证：群/私聊文件使用正确 upload Action，消息 segments 不包含 file，未 materialize 资源不访问网络

## 4. 规格与文档同步

- [x] 4.1 同步 `openspec/specs/adapter-observability` 和 `openspec/specs/plugin-lifecycle` 中与业务日志不掩码冲突的要求；验证：主 spec 不再要求同一类业务字段脱敏
- [x] 4.2 同步 `ARCHITECTURE.md` 和 README 中仍描述插件侧本地读取或 `base64://` fallback 的内容；验证：文档与本 change 的 Hermes-only 资源规则一致，示例全部使用合成值
- [x] 4.3 保持 `pii_safe`、配置 schema、HTTP/SSE、Tool allowlist 和持久化语义不变；验证：相关现有测试或静态检查确认本 change 未扩大范围

## 5. 验收

- [x] 5.1 运行相关日志、Tool、资源和出站测试；验证：覆盖本 change 每个 scenario，失败时只记录合成的最小复现
- [x] 5.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；验证：逐条记录命令结果，不能把未执行命令标记为通过

## 实施证据台账

- 1.1：已读取 `ARCHITECTURE.md`、本 change 全部 artifacts 及相关主 spec；范围仅涉及业务日志、Tool 原样回显、Hermes 资源所有权和合成资料，未新增 HTTP/SSE、allowlist、持久化或发布任务。
- 1.2：新增 `tests/fixtures/security_boundary_inputs.py`，全部身份、正文、资源引用和协议扩展均为合成值；基线相关测试 117 passed、1 skipped。
- 1.3：只读审计 `/Users/bytecolt/PythonProjects/hermes-agent/gateway/platforms/base.py` 及相关 gateway 入口，确认图片/语音入站 core helper 与 adapter native 出站入口；未确认通用 URL-to-bytes 或本地文件 upload seam，后续按 `unsupported` 验证。
- 2.1–2.4：`milky/observability.py` 保留字段白名单和固定错误诊断，但业务 ID/chat/message/nickname 原样输出；人类日志用 `chat_key[...]` 避免 Hermes secret redactor 误判，结构化字段仍为原始 `chat_key`；`outbound/tools.py` 使用 `milky_tool_call` 记录 Tool 名称、入参和结果，成功返回完整 envelope，失败沿用固定分类。
- 3.1–3.3：移除插件侧 `materialize_media_uri`、`url_to_bytes`、bytes cache 和本地路径读取；图片/语音继续走确认的 Hermes URL helper，视频/文件无入口时保留占位，出站本地路径返回 `unsupported`，显式 URI 走 native/upload Action。
- 4.1：同步 `openspec/specs/adapter-observability/spec.md` 与 `openspec/specs/plugin-lifecycle/spec.md`，业务关联字段改为原样关联；普通日志的字段白名单、固定事件、错误分类和秘密边界保持不变。
- 4.2：同步 `ARCHITECTURE.md` 与 `README.md`，删除插件读取本地资源和生成 `base64://` fallback 的描述；资源示例使用 `media.example.invalid`、合成 chat key 和占位凭证。
- 4.3：变更文件未触及 `pii_safe`、配置解析、HTTP/SSE、ToolSpec allowlist 或持久化状态；相关回归测试 142 passed、4 skipped，目标代码 ruff 检查和格式检查通过。
- 5.1：相关日志、Tool、资源、出站和禁言测试 153 passed、4 skipped；日志测试 30 passed；完整测试套件 480 passed、22 skipped，失败复现均未使用 live 数据。
- 5.2：最终验收全部通过：`uv run pytest`（480 passed、22 skipped）、`uv run ruff check .`、`uv run ruff format --check .`（184 files already formatted）、`uv build`、`git diff --check`、`npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`（1 passed、0 failed）。strict 校验曾因 delta scenario 标题不一致失败，已按诊断补齐并重新通过。
- 后续日志审计：复查全部 `log_event` 调用和业务字段，确认 `file_id` 及其他 ID、chat key、昵称均不做插件侧脱敏；Hermes formatter 合成扫描结果全部保留原值；新增字段回归测试 30 passed。
