## 1. 契约与测试夹具

- [ ] 1.1 在插件入口测试中建立可记录 `register_system_prompt_section` 的 fake host，并以脱敏合成账号数据验证 section ID、位置、回调注册和注册阶段无网络/无后台任务
- [ ] 1.2 为迁移文案建立可审计的测试断言，验证 `PLATFORM_HINT` 严格等于首句、其余原文逐段按顺序完整出现在 section，且不重复出现在 platform hint
- [ ] 1.3 为生命周期 fake 依赖补齐连接后可读取的合成 nickname 与身份快照观察点，验证初始同步失败时不会发布未确认身份

## 2. 插件注册与身份缓存实现

- [ ] 2.1 拆分根入口的静态平台首句和迁移正文，并在支持宿主 API 时从 Milky `register(ctx)` 注册稳定的 `after_memory` system prompt section；验证注册只登记回调，不调用 Milky Action、SSE 或长期任务
- [ ] 2.2 实现注册级、受同步保护的账号身份快照，将同一快照交给 section renderer 和 adapter factory；验证渲染只读快照、不访问 client、不从 session metadata/消息/config 推断身份
- [ ] 2.3 在 adapter 完成既有 `connect()` 初始同步并具备普通消息就绪条件后一次性发布已确认 `self_id`/`nickname`，保持现有 SSE、pipeline、sender、Gate/Will 生命周期顺序；验证重连和断开不新增账号查询
- [ ] 2.4 处理未连接、初始同步失败和异常 nickname 的安全降级，确保不输出占位/猜测身份、首行保持单行且不泄露远端响应、凭证、路径或正文；验证 renderer 不触发网络
- [ ] 2.5 在缺少 `register_system_prompt_section` 的旧宿主上下文中跳过 section 登记但继续完成只含首句的平台注册；验证不恢复完整旧 hint、不抛出注册异常

## 3. 行为回归与隔离验证

- [ ] 3.1 增加连接成功后的 section 渲染测试，验证首行严格使用合成 decimal UID 与 nickname，正文完全迁移且重复渲染不重新获取账号信息
- [ ] 3.2 增加连接失败和连接前 prompt 渲染测试，验证 section 不生成 `unknown`/默认身份，platform hint 仍仅包含首句，且普通 adapter 消息入口继续保持未就绪
- [ ] 3.3 增加 Milky 与其他 platform fake 注册并存的隔离测试，验证只有 Milky section 含 QQ 指引/身份行，其他 platform hint、section 和身份行为不变

## 4. 质量门禁与证据

- [ ] 4.1 运行聚焦测试 `uv run pytest -q tests/test_plugin_entry.py tests/test_adapter_lifecycle.py`（以及新增的 prompt/identity 测试文件），记录通过或最小失败复现
- [ ] 4.2 运行完整质量门禁 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，确认未修改 Hermes core 且未引入敏感数据
- [ ] 4.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，把命令结果、任何 skip/外部宿主未验证边界和必要的安全 smoke 说明记录在本 change evidence ledger 中；不执行未授权的真实 Milky 写入、上传或消息发送
