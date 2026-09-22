# 验证证据

## 已验证行为

- `sticker_search` 与 `sticker_send` 共享现有贴纸库可用性、当前 Milky session 校验、候选匹配、文件校验和固定错误分类；注册阶段只组装 service，不打开贴纸 store。
- 搜索参数只接受 `intent`、`emotion`、`tags`、`limit`，默认 5、上限 10；结果只交付 `status`/`items` 和 `sticker_id`、`emotion`、`tags`、`description`。
- `sticker_send` 支持与查询模式互斥的持久化 opaque `sticker_id`；精确路径跳过匹配和轮换，重新检查当前条目、文件和完整性，并复用一次 claim/一次 Action 边界。
- 搜索是只读的，不发送、不更新使用统计、不改变轮换状态，也不创建、迁移或修复存储；ID 失败分别保留 `not_found`、`missing_file` 和 `storage_error`。
- README、ARCHITECTURE 和 `milky-qq-action-tools` bundled skill 已同步实际接口；平台提示、SOUL、记忆和聊天策略未修改。

## 与未实施 library change 的边界

本 change 只建立在当前人工共享库上，保留 `intent`/`emotion`/`tags` 查询、共享可见范围和发送前 claim 统计。
未归档 `add-qq-sticker-library` 规划中的 `keyword`、`category`、`index`、按会话 scope、自动收藏及成功后计数不属于本次实现；其后续实现需要显式合并双模式工具契约，不由本 change 擅自扩大。

## 检查记录

- 定向 `uv run pytest -q tests/test_sticker_send.py tests/test_sticker_maintenance.py tests/test_sticker_search.py tests/test_qq_tools.py tests/test_plugin_entry.py tests/test_outbound.py`：200 passed（本地 fake host/合成库）。
- 全量 `uv run pytest -q -rs`：975 passed，3 skipped。
- `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check` 和 `openspec validate --changes --strict` 均通过。
- `uv build` 成功生成 source distribution 和 wheel。

## 未验证边界

- 当前工作区没有可用的真实 Hermes 宿主，因此 4.3 的真实工具发现、新会话定义和真实宿主交付仍为 blocked/未验证；fake host 结果不替代该证据。
- 本次没有获得真实 Milky 目标的单次写入授权，因此 4.4 的真实 ID 发送和原查询发送仍保留未完成；本地 fixture 成功不等同于真实 QQ 发送成功。
