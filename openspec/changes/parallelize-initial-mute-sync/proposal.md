## Why

当前启动阶段对选中的每个群串行调用 `get_group_member_info(no_cache=true)`。真实测试中
242 个群的无界只读并发扫描在 2.59 秒和 2.98 秒内完成且全部成功，而串行执行按已观测的
约 0.36 秒单请求延迟预计需要约 87 秒，超过 Hermes Gateway 默认 30 秒的平台连接预算，
导致 Milky 在完成初始状态同步前被 Gateway 取消并进入重连。

## What Changes

- 将初始群禁言成员查询改为对全部选中群同时发起的无界并发扫描，不增加插件侧 semaphore、
  worker 数或分批等待。
- 保留 `get_login_info -> get_group_list -> 群成员查询` 的阶段顺序，并继续在所有选中群查询
  完成前保持 adapter 未就绪，不提前启动 SSE 或普通消息入口。
- 每个成员查询继续使用 `no_cache=true`；成功结果更新对应快照，失败结果保持
  fail-closed，任一失败仍使本次初始同步失败。
- 处理 Gateway 取消、单群失败和 client 关闭，确保并发请求不会在连接失败后遗留。
- 增加 200+ 群规模、查询失败、取消和结果汇总测试，并记录初始扫描的规模、耗时和结果分类。
- 不改变稳态 `refresh_group()` 的每群锁、冷却和现有并发限制；本 change 的无界策略只适用于
  连接初始化的全量扫描。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `mute-tracking`: 明确初始群禁言扫描对所有选中群无界并发发起，同时保持完整扫描、
  fail-closed 和取消清理语义。

## Impact

- 影响 `state/mute_tracker.py` 的初始同步实现、初始化观测日志和相关单元/集成测试。
- 可能更新 `ARCHITECTURE.md` 对连接初始化阶段的说明；不改变 Milky Action 协议、Gate
  顺序、SSE 边界、出站发送或 Hermes Agent 队列。
- 无新增外部依赖和配置项。无界并发会把服务端承受的瞬时压力交给 Milky/HTTPX 连接池，
  因此测试和运行日志必须保留失败、延迟和取消证据，不把一次成功压测解释为容量保证。
