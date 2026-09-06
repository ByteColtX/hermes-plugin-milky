# Evidence ledger

记录日期：2026-09-06（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_mute_tracker.py tests/test_adapter_lifecycle.py tests/test_milky_local_integration.py`：通过，44 passed，1 skipped。
- `uv run pytest -q -rs`：通过，801 passed，2 skipped；skip 为当前测试环境没有 Hermes host 的
  `tests/test_adapter_lifecycle.py:485` 和 `tests/test_multimedia_outbound.py:625` 集成测试。
- 新增初始扫描规模测试：240 个合成群在 `max_concurrent_refreshes=1` 时全部发起成员查询，峰值并发达到 200 以上，每次请求使用 `no_cache=true`，且全部结果收集后才完成同步。
- 新增失败测试：所有选中群查询均完成后，失败群保持 `muted`，汇总准确记录 2 个成功和 1 个失败，初始同步保持失败。
- 新增取消测试：取消初始同步会取消并等待全部未完成成员查询，client 无活动查询，不写入普通成员查询失败诊断。
- 新增 adapter 生命周期测试：初始同步取消时不启动 SSE 或 pipeline，后续 `disconnect()` 仍关闭 tracker 和 client。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，305 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，2 passed、0 failed；包含当前 change 和同时存在的 `charge-willingness-on-trigger`。

## 未覆盖与边界

- 未执行真实 Milky/Hermes 连接；本 change 只使用 fake client、fake host 和现有 HTTP fixture，不能替代真实服务容量或连接预算验证。
- 未执行真实消息发送、上传或其他远端写入；本 change 未新增 Action、ToolSpec 或配置项。
- 初始扫描采用无界 fan-out 是本 change 的策略取舍；`refresh_group()` 仍保留每群锁、冷却和全局并发上限，未把成功测试解释为服务端容量保证。
- 测试使用合成群号、身份和错误，不记录 token、Authorization、完整响应、异常正文、媒体 URL、路径或敏感正文。
