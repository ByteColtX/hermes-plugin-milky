## 1. 契约与测试基线

- [x] 1.1 为初始群禁言扫描补充 200+ 群规模的 fake client/fixture，验证所有选中群查询均被发起、每次使用 `no_cache=true`，且初始化等待全部结果后才完成
- [x] 1.2 补充一个或多个成员查询失败场景，验证失败结果保持对应群的 fail-closed 状态、汇总计数准确且整体初始同步失败
- [x] 1.3 补充取消场景，验证取消初始化会取消并等待所有未完成成员查询，不遗留使用 client 的后台任务或错误地标记为普通查询失败

## 2. 初始扫描实现

- [x] 2.1 将选中群的初始 `get_group_member_info` 查询改为无界 fan-out，同时保留登录、群列表和成员查询阶段顺序；用 200+ 群规模测试验证查询启动不受插件 semaphore、worker 数或分批等待限制
- [x] 2.2 按群标识收集并应用并发查询结果，保持 `shut_up_end_time`、member/whole 状态、TTL 和 `no_cache=true` 语义；运行现有 `tests/test_mute_tracker.py` 聚焦回归
- [x] 2.3 完善并发初始化的异常传播、取消清理和安全扫描观测，验证失败、取消和 client 关闭后不会启动 SSE、开放消息入口或遗留任务
- [x] 2.4 保持运行期 `refresh_group()` 的每群锁、冷却和全局并发上限不变，运行发送失败刷新和并发刷新测试确认无界策略未扩散到稳态维护

## 3. 文档与质量门禁

- [x] 3.1 更新 `ARCHITECTURE.md` 的连接初始化流程，明确初始成员查询为无界并发、完整结果收集后才就绪，并区分运行期有界刷新
- [x] 3.2 运行 `uv run pytest -q tests/test_mute_tracker.py tests/test_adapter_lifecycle.py tests/test_milky_local_integration.py`，确认生命周期、真实 HTTP fixture 和规模回归通过
- [x] 3.3 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，确认完整质量门禁通过
- [x] 3.4 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认 change artifact、delta spec 和实现状态一致
