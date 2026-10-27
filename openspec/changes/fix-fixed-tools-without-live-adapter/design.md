# Design

## 现状与根因

`outbound/tools.py` 的 26 个固定 Action handler 在进入 `_execute_action` 前都做同一个判断：

```python
sender = _ACTIVE_SENDER
if sender is None:
    return _tool_error("unsupported")
```

`_ACTIVE_SENDER` 只在 `MilkyAdapter` 连接成功时由 `bind_sender` 绑定（`adapter.py:830-837`），断开
时清空。Hermes cron 的 managed 部署把 job 移交给独立 worker 进程（`cron/scheduler.py` 的
`_launch_external_cron_worker`），该进程不物化 Milky 平台，因此 `_ACTIVE_SENDER` 恒为 `None`，
所有固定工具返回 `{"ok":false,"classification":"unsupported","error":"tool is unavailable"}`。

插件已有可复用范式：`outbound/standalone.py::standalone_send` 在无 live adapter 时从
`load_config()` 现场构造 `MilkyClient` 与 `MilkyOutboundSender`，执行一次并在 `finally` 中关闭。

## 决策

1. **执行入口统一收敛到 `_execute_action`。** handler 的 `lambda` 改为接收 `sender` 参数的
   `Callable[[MilkyOutboundSender], Any]`，把「用哪个 sender」的决定从 26 个 handler 里抽走，避免
   重复分支和后续漂移。
2. **优先 live client。** 进程内已有绑定 sender 时行为完全不变：复用网关连接、不新建 client，
   保持现有事件循环、认证和生命周期语义。
3. **无 live client 时按调用时配置构造一次性资源。** 每次工具调用独立创建 `MilkyClient` 与
   `MilkyOutboundSender`，执行本次 Action 后在 `finally` 中先关 sender 再关 client；不写入任何
   进程级缓存，因此不会跨事件循环复用连接池，也不会让 cron worker 长期持有连接。
4. **配置不可读归为 `unsupported`。** 与「工具当前无法执行」的既有语义一致，且在创建 client
   之前失败，符合「网络前失败」边界。参数错误仍然是 `invalid_input`。
5. **关闭辅助下沉到 `outbound/lifecycle.py`。** standalone 与 Tool 路径共用同一实现，避免
   `tools.py` 跨模块导入 `standalone.py` 的私有函数。
6. **贴纸工具不改。** `sticker_send`/`sticker_search` 需要当前 Milky 会话的 chat key；cron 中没有
   会话上下文，返回 `unsupported` 是正确语义。为它们创建一次性 client 会绕过会话边界。

## 风险与缓解

- [风险] 一次性路径可能在频繁调用时反复建立连接。→ 该路径只出现在无 adapter 的进程；有 live
  adapter 时始终复用。文档与规范明确不缓存、不复用。
- [风险] 构造 `MilkyOutboundSender` 时若配置值非法会抛 `ValueError`。→ 在 `try` 内统一转换为
  `unsupported`，网络前失败。
- [风险] 关闭异常覆盖原始结果。→ `close_quietly` 吞掉清理异常，与 standalone 现有行为一致。
- [风险] 误以为 cron worker 里贴纸工具也可用。→ 规范和文档保留贴纸工具的会话前提。

## 备选方案

- **把 cron 改回网关进程内执行**：需要改变部署形态并放弃 restart-safe 隔离，且不解决其他无
  adapter 会话（CLI/TUI）的问题，拒绝。
- **并回 `codex/milky-tools-entry` 的根 `tools.py`**：只影响 bundled 平台插件的延迟加载，对用户
  安装插件的工具注册没有作用，且不解决 handler 缺少 sender 的问题，拒绝。
- **让工具进程跨进程调用网关 adapter**：需要 Hermes core 提供 seam，超出本仓库边界，拒绝。

## Migration

无配置迁移；行为向后兼容。升级后无需重启配置，工具在无 live adapter 的会话中直接可用。
