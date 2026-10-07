# Design

## Context

See proposal.md for motivation and the spec deltas for observable behavior. 当前 `outbound/tools.py` 的工具日志只保留工具名、分类和耗时。项目最低宿主版本为 `0.21.4`；本地 `../hermes-agent` 的 `v0.21.4+canary.20260925T065930Z` 源码已提供 `post_tool_call` 插件观察 hook 和回调注册接口。事件包含工具名、参数、结果、耗时、状态/错误类型和若干可选关联 ID；hook 不提供完成时间戳，且自身是有界、容错的观察路径。已有 Dashboard 扩展使用宿主认证和显式 profile，维护任务另有自己的持久化语义。

## Goals / Non-Goals

**Goals:**

- 以 `post_tool_call` 作为调用观察入口，并严格按插件声明的 Milky/QQ 工具名过滤。
- 保存观察时间、耗时、受限状态和逐工具参数白名单摘要，使只读 Dashboard 能检索记录并计算有界统计。
- 让历史数据与 Dashboard 当前选择的 profile 一一对应；记录过程不影响原工具调用。

**Non-Goals:**

- 不审批、拦截、重写或重放工具调用；不注册 `pre_tool_call` 或结果变换 hook。
- 不捕获其他 Hermes 工具，不保存原始参数对象、远端响应或 hook 自由文本诊断。
- 不把该功能作为完整取证、QQ 远端结果核实、告警或跨主机遥测系统。

## Decisions

### 使用调用后观察 hook

只接入 Hermes 的 `post_tool_call`，在观察回调中筛选工具名。事件提供 `tool_name`、`args`、`duration_ms`、`status` 和 `error_type` 等可用字段；记录器忽略 `result`、`error_message` 和 `middleware_trace`。状态按固定集合归一化，未知状态归为 `unknown`。由于事件没有墙钟完成时间，记录器在回调收到事件时生成 UTC 观察时间，并将 `duration_ms` 原样作为独立耗时；不声称观察时间等于精确的工具结束时刻。

选择调用后 hook 而非扫描运行日志，是因为现有日志不含调用参数，不能回答工具如何使用；相比逐个包装 Tool handler，调用后 hook 能在一个观察边界覆盖已声明工具，并能收到 Hermes 提供的终态状态。`pre_tool_call` 可能改变是否执行，结果变换 hook 可能改变 Tool 交付内容，二者都不适合作为本功能入口。

### 将参数映射成逐工具白名单摘要

按工具名使用固定字段白名单和类型检查，只保存经确认可用于识别目标/选项的数值 QQ ID、序号、数量、布尔值及贴纸 ID。其他已提供字段以“已提供、值未保存”表示；不得递归复制输入对象或对任意 JSON 使用通用敏感词过滤。白名单投影应受单条大小上限约束，并与工具 schema 变更一起维护。

这能显示如目标群/用户及调用选项等实际用法信息，同时避免把 `reason`、查询文本、资源标识、URL、令牌或未知嵌套字段长期保存。将每次调用的完整参数存入历史更容易复现请求，但会违反项目对 Tool 原始参数和敏感内容的边界；只依赖现有日志则无法提供调用方式。

### 以独立的 profile 本地存储持有历史

每个 Hermes profile 使用独立的 SQLite 文件：`<profile-home>/plugin-data/hermes-plugin-milky/tool-call-history.db`。文件放在现有 profile 插件数据根下，与 `dashboard-jobs.db` 并列；不混用任务库，以免将调用历史的字段、统计和保留策略耦合到任务状态及其 7 天/1000 条清理规则。

库中使用 `tool_calls` 表，每次观察到的调用一行，字段为：随机生成的 `record_id` 主键、UTC ISO 8601 `observed_at_utc`、非负整数 `duration_ms`、`tool_name`、归一化 `status`、可空的白名单 `error_type`，以及只包含安全投影的 `args_summary_json`。在观察时间、工具名和状态字段上建立索引，以支持时间倒序列表及对应筛选。表结构中不设原始 args、result、error message 或 middleware trace 列。

写端只在首次收到已声明工具的观察事件时创建目录、数据库和表结构；import/register 阶段仍只登记 hook，不创建存储、后台任务或网络连接。每次写入使用短事务，并在同一写入边界清理过期和超量记录；写锁超时或磁盘错误按观察 hook 的 fail-open 边界处理，不影响 QQ 工具结果。Dashboard 查询端只打开所选 profile 对应的既有文件并以只读方式查询；文件不存在时返回空历史，不为浏览建库，也不接受客户端文件路径。

记录保存上限采用每 profile 30 天或 10,000 条，以先达到者为准。统计只覆盖仍保留且符合当前筛选的记录，包含调用数量、按工具/观察状态计数和耗时概览；它不推断 Milky 协议响应表示 QQ 业务成功。

### Dashboard 仅提供只读查询

在既有 Dashboard 扩展和宿主认证组件中加入历史入口。查询参数只有明确 profile、时间范围、工具名、观察状态和分页信息；记录列表与汇总使用相同的过滤条件。页面显示观察到的调用时间和状态，不提供批准、执行、重放或记录修改入口。

## Risks / Trade-offs

- [容错观察 hook 可能超时、未触发或回调写入失败] → 工具执行保持原样，记录可能缺失；页面文案和统计仅称为“观察到的调用历史”，不承诺完整覆盖。
- [逐工具白名单随 Tool schema 演变可能过期] → 对每个声明工具验证摘要映射；未知字段仅显示已提供，不落原值。
- [Hermes 的 `ok`/`error` 是调用观察分类，不是 QQ 远端语义] → UI、统计和文档统一标为“观察状态”，不展示“QQ 成功率”。
- [记录含必要的 QQ 用户/群 ID，且会跨重启保留] → 只在选定 profile 的认证 Dashboard 显示，并按 30 天/10,000 条上限回收。

## Migration Plan

新安装或升级后从首次观察到的调用开始积累记录，不从旧日志回填参数或结果。页面启用时没有存储文件即显示空历史，不为只读浏览初始化其他 QQ 数据。回滚或停用后停止采集和查询；保留既有历史数据供后续兼容版本读取，不在回滚过程中自动删除。

## Open Questions

无。30 天/10,000 条保留上限是本提案的首版默认边界，可在实现前的变更评审中调整。
