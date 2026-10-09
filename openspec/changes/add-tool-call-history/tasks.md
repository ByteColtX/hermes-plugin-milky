# Tasks

## 1. 采集与持久化

- [x] 1.1 在 manifest 声明 `post_tool_call` 并注册只读观察回调；用 fake host 验证声明与注册匹配、只接收本插件声明的 Milky/QQ 工具，且 import/register 不创建存储、任务或网络连接。
- [x] 1.2 在 `plugin-data/hermes-plugin-milky/tool-call-history.db` 实现一条调用一行的 SQLite 存储，字段限定为内部记录 ID、UTC 观察时间、耗时、工具名、归一化状态/错误类型和白名单参数摘要 JSON；用合成 hook 事件验证数据库中没有原始 args、result、error message 或 middleware trace，且写入失败不改变工具结果。
- [x] 1.3 为每个 profile 独立创建该数据库，增加时间/工具/状态索引、30 天/10,000 条清理及筛选统计；用可控时钟及 fake profile 验证懒创建、重启后可查、边界回收、profile 不串数据和统计口径，并同步更新架构文档。

## 2. Dashboard 历史查看

- [x] 2.1 增加宿主认证下的只读历史查询，以只读方式打开明确 profile 已有的数据库并支持时间、工具、状态、稳定有界分页和全范围汇总；用 fake host 验证空库不建文件、未授权/停用/伪造 profile 被拒绝且查询不触发工具。
- [x] 2.2 在既有 Dashboard 中加入只读历史页，呈现 profile、时间、工具、观察状态、白名单参数摘要、分页和同范围统计；用前端验证覆盖空记录、筛选、翻页及切换 profile 后迟到响应不污染新页面。
- [x] 2.3 更新 README 的功能和数据边界说明；核对文档明确说明参数白名单、原始结果不保存、观察状态不代表 QQ 成功及 hook 可能漏记。

## 3. 集成验证

- [x] 3.1 用当前支持的 Hermes fake host 验证 hook、Dashboard 认证/profile 流程和停用/卸载行为；只报告 fake host 证据，不执行会改变 QQ 状态的真实 Tool 调用。
- [x] 3.2 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `openspec validate --changes --strict`；分别报告通过、失败、skip 及未验证的真实 Hermes/Milky 边界。
