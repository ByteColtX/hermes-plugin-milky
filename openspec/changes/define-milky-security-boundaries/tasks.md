## 1. 契约和合成资料

- [ ] 1.1 对照本 change 与现有主 spec，确认只保留日志、Tool 原样回显、Hermes 资源所有权和合成资料四个范围；验证：HTTP/SSE、allowlist、持久化和发布流程没有新增实现任务
- [ ] 1.2 建立只含合成身份、占位正文、占位资源和合成协议值的 fixture/helper；验证：测试资料不包含真实 token、真实身份、真实正文、真实媒体引用或 live 响应
- [ ] 1.3 通过 Hermes 源码或既有测试 contract 确认实际资源入口；验证：记录已确认入口，未确认的能力明确测试为 `unsupported`，不发明通用 seam

## 2. 日志和 Tool

- [ ] 2.1 移除业务 ID、chat key、message ID 和昵称的日志掩码，但不新增凭证过滤器；验证：日志测试断言业务值原样出现，认证 header 不作为日志调用参数
- [ ] 2.2 让已注册 Tool 的日志记录 Tool 名称、调用入参和远端结果；验证：日志捕获测试断言入参和结果不摘要、不改名、不掩码、不删除未知业务字段
- [ ] 2.3 让已注册 Tool 的成功结果原样返回当前调用方，保留完整 envelope 和未知字段；验证：fake response 与调用方收到的结果结构和值一致，Tool 结果没有 DTO 重构
- [ ] 2.4 保持参数错误、未注册 Action 和无远端响应使用既有错误分类；验证：失败测试不伪造远端成功结果，也不触发额外 Action

## 3. Hermes 资源边界

- [ ] 3.1 删除入站和出站插件侧 URL 下载、远端 bytes 读取、本地文件读取、媒体缓存、下载目录、路径拼接和 `base64://` fallback；验证：网络/文件读取测试桩被触发时，插件不调用这些路径并返回 `unsupported`
- [ ] 3.2 将 trigger 资源引用交给已确认的 Hermes core 入口，并保留 reply、forward、图片、语音、视频和文件失败占位；验证：wait 阶段不访问资源，trigger 只使用 core 返回结果
- [ ] 3.3 将 Hermes materialized 出站资源交给对应 native media 或独立文件 upload Action；验证：群/私聊文件使用正确 upload Action，消息 segments 不包含 file，未 materialize 资源不访问网络

## 4. 规格与文档同步

- [ ] 4.1 同步 `openspec/specs/adapter-observability` 和 `openspec/specs/plugin-lifecycle` 中与业务日志不掩码冲突的要求；验证：主 spec 不再要求同一类业务字段脱敏
- [ ] 4.2 同步 `ARCHITECTURE.md` 和 README 中仍描述插件侧本地读取或 `base64://` fallback 的内容；验证：文档与本 change 的 Hermes-only 资源规则一致，示例全部使用合成值
- [ ] 4.3 保持 `pii_safe`、配置 schema、HTTP/SSE、Tool allowlist 和持久化语义不变；验证：相关现有测试或静态检查确认本 change 未扩大范围

## 5. 验收

- [ ] 5.1 运行相关日志、Tool、资源和出站测试；验证：覆盖本 change 每个 scenario，失败时只记录合成的最小复现
- [ ] 5.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；验证：逐条记录命令结果，不能把未执行命令标记为通过
