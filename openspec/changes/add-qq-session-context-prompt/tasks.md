## 1. Canonical 场景资料

- [ ] 1.1 扩展 canonical record，使通过身份交叉校验的 friend/group 消息分别保留本 change 规定的最小场景 metadata，并确保 `raw`、`extras`、群成员资料和未声明字段不会进入介绍资料；用 friend/group 正常 fixture、身份不一致 fixture 和未知扩展 fixture 验证字段边界
- [ ] 1.2 对齐 Hermes source mapper 使用 canonical 中的 friend/group 资料和既有 sender fallback，确保 `dm:<id>`、`group:<id>`、sender name、message ID 和正文行为不回归；运行 canonical 与 mapper 聚焦测试验证

## 2. 本地会话快照与渲染

- [ ] 2.1 实现与单次 `register(ctx)` 绑定的不可变、线程安全、有界 chat metadata snapshot store，使用 `dm:<id>`/`group:<id>` 作为 key，支持不同 chat 隔离、同 group 多 session 共享和淘汰后安全缺省；用并发访问、容量淘汰和注册实例隔离测试验证
- [ ] 2.2 实现 friend/group 白名单字段的快照构造和确定性渲染，按规定顺序省略缺失值，对 nickname、group_name、description、announcement 做控制字符/换行中和与长度限制，并明确标注为不可信 metadata；用恶意文本、超长文本、缺失字段和未知扩展测试验证不会生成 prompt 结构或指令

## 3. Pipeline 与 Hermes section 接线

- [ ] 3.1 在现有 pipeline 中把快照登记接到资源解析和 MessageEvent mapper 成功之后、Hermes `handle_message()` 之前，并保持 dedup、Gate、Will、wait、temp、系统事件和 mapper 失败不登记快照；用顺序断言和失败路径测试验证
- [ ] 3.2 在根 `register(ctx)` 为每个注册实例创建并共享 snapshot store，注册独立稳定的 `hermes-plugin-milky.qq-session-context` section；callback 通过 `HERMES_SESSION_CHAT_ID` 查询本地快照，缺少 chat context 或资料时返回空内容，且不执行 Milky Action、HTTP/SSE、文件访问或阻塞 I/O；用 fake Hermes context 和网络访问断言验证
- [ ] 3.3 保留现有 `hermes-plugin-milky.qq-platform-guidance` 的 Bot identity 来源和职责，并对没有 `register_system_prompt_section` 的旧 Hermes 宿主安全降级；用 section 注册顺序、旧宿主注册和多平台共存测试验证

## 4. Prompt 缓存与集成回归

- [ ] 4.1 增加 fake Hermes 测试覆盖 friend/group 新 session 的 section 内容、同 chat 与不同 chat 的隔离、同 group 多 session 共享、资料缺失和 snapshot 淘汰；验证介绍不进入 MessageEvent、`channel_context`、`platform_hint` 或出站正文
- [ ] 4.2 增加真实 Hermes 受控集成测试，覆盖首次 system prompt、已有 prompt restore、显式 prompt rebuild、旧宿主降级和 callback 无网络，并将当前源码/运行结果写入 evidence ledger；验证已持久化 prompt 恢复不会重新查询或改变已持久化介绍
- [ ] 4.3 回归既有入站 canonical、Hermes pipeline、adapter lifecycle、prompt guidance 和插件入口测试，确认消息正文、Gate/Will、资源处理、出站路由及 reply cost 语义不变

## 5. 文档与规范同步

- [ ] 5.1 更新 `ARCHITECTURE.md` 和 `README.md`，说明 QQ 会话介绍 section、最小字段、快照时序、无网络 callback、缓存/降级边界和不支持实时刷新；通过文档审阅确认没有写入凭证、真实 QQ 号、敏感正文或未实现能力
- [ ] 5.2 将本 change 的稳定行为同步到 `openspec/specs/canonical-messages/spec.md`、`openspec/specs/hermes-message-pipeline/spec.md` 和 `openspec/specs/milky-platform-prompt-guidance/spec.md`，并补充/落地 `milky-session-context-prompt` 主规范；运行 OpenSpec strict validation 验证 delta 与主规范一致

## 6. 质量门禁

- [ ] 6.1 运行相关聚焦 pytest、`uv run ruff check .`、`uv run ruff format --check .` 和 `git diff --check`，修复新增实现、测试、文档中的失败项并记录结果
- [ ] 6.2 运行完整 `uv run pytest -q`、`uv build` 和 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认实现、构建和 change artifacts 均通过；所有跳过或仅 fake host 通过的检查必须在 evidence ledger 中明确标注
