# 主规范整理记录（2026-09-26）

本次整理覆盖全部 30 个主 capability 的审阅，保留现有路径和归档历史。只修改规范及受影响的活动 change 规划文档，不修改运行代码，不推进功能任务。当前行为入口见 [主规范导航](../README.md)。

## 语义校正依据

| 校正 | 当前证据 |
|---|---|
| 贴纸先提交统计 claim，再调用 Milky；claim 失败不发送 | [sending.py](../../stickers/sending.py)、[test_sticker_send.py](../../tests/test_sticker_send.py) 的 claim 失败测试 |
| 显式命令与已授权 Web 导入/重新分析共用维护语义 | [plugin_api.py](../../dashboard/plugin_api.py)、[management.py](../../stickers/management.py)、[test_sticker_management.py](../../tests/test_sticker_management.py) |
| 空白名单阻止普通入站，管理指令可以热发布白名单 | [配置规范](../specs/configuration/spec.md)、[热白名单规范](../specs/hot-chat-allowlist/spec.md)、[test_gate_registry.py](../../tests/test_gate_registry.py) |
| 行中 SPLIT 与结构化 mention/reply 保持支持 | [formatter.py](../../outbound/formatter.py)、[test_outbound_splitting.py](../../tests/test_outbound_splitting.py)、[test_cq_formatter.py](../../tests/test_cq_formatter.py) |
| 原始响应交付只约束固定 Milky Action 工具，贴纸工具保留结构化结果 | [工具规范](../specs/qq-action-tools/spec.md)、[信息边界](../specs/security-boundaries/spec.md)、[test_qq_tools.py](../../tests/test_qq_tools.py) |

## 场景合并与改名映射

下表只记录原场景标题消失或同名重复项减少的情况；仅移动到合适 Requirement 的场景保留原名。

| capability | 原场景 | 去向或校正 |
|---|---|---|
| agent-facing-message-controls | Agent 获得基础语法；Agent 获得基础语法说明 | 合入 Agent 获得基础语法和分段说明，保留 CQ 大小写及默认无自动引用规则 |
| configuration | 空白名单保持原有语义 | 改名为空白名单阻止全部普通入站 |
| outbound-message-splitting | 标记不是完整独立行 | 改名为识别行中有效标记 |
| outbound-messaging | 超长文本 | 合入超长普通文本 |
| slash-commands | /milky 带参数 | 改名为未声明分支不得触发业务操作 |
| slash-commands | 显式 sticker add | 合入 sticker add 触发人工导入和视觉打标、sticker add dry-run 只预览视觉结果 |
| plugin-lifecycle | 空白名单保持全群语义 | 改名为空白名单执行零成员扫描 |
| qq-action-tools | Hermes 发现新增工具 | 改名为 Hermes 发现固定工具 |
| qq-action-tools | 状态变更请求结果未知 | 合入状态变更请求未取得响应体，保留中断/超时/读取失败及不得假报拒绝 |
| qq-action-tools | 成功 data 结构缺失 | 合入响应缺少历史最小结构，保留 data 不是空对象的条件 |
| qq-action-tools | 未连接或未取得响应 | 分别由未连接或已关闭、状态变更请求未取得响应体及统一无响应规则覆盖 |
| qq-group-action-tools | 查询结果缺少最小结构 | 合入查询结果缺少历史最小结构或表示失败，保留对象数组类型约束 |
| qq-group-action-tools | 远端协议拒绝群操作 | 合入远端协议拒绝或 HTTP 错误，保留 message/wording |
| qq-group-action-tools | 协议拒绝或响应结构错误 | 合入协议拒绝、HTTP 错误或响应结构错误 |
| qq-group-action-tools | 成功设置返回空对象 envelope | 合入成功设置返回远端响应，保留 status/retcode 条件 |
| media-and-reply-resolution | trigger 补全 forward；引用查询失败 | 分别合入 forward 只保留引用 ID、资源查询失败 |
| will-willingness | 结构化提及文字不产生关键词命中；非文本片段隔断关键词 | 每项重复两次改为共同匹配边界下各一次，gain 与 force 均引用 |
| system-events-and-safety | Agent 调用首批工具 | 改名为 Agent 调用已注册消息工具 |
| qq-sticker-maintenance | 维护输入边界 | 合入命令参数试图改变输入目录及固定目录 Requirement |
| qq-sticker-maintenance | add 校验失败 | 合入排除非图片和不安全文件、确定性筛选和去重先于视觉分析 |
| qq-sticker-maintenance | 字段级维护 | 合入 edit 只更新指定字段、edit 清除人工覆盖及原子部分更新 |
| qq-sticker-maintenance | 维护操作不改变统计 | 合入维护和搜索不改变使用统计，包含 list 与 Web 维护 |
| qq-sticker-maintenance | 维护失败保持脱敏 | 合入失败结果脱敏及维护失败隔离条款 |
| qq-sticker-maintenance | 普通消息或 Agent 输出触发维护 | 合入非显式普通流程不触发维护 |
| qq-sticker-maintenance | 无效发送不计数 | 移至 qq-sticker-send 的本地校验失败不计数，条件明确为 claim 前 |
| qq-sticker-maintenance | 发起发送后原子更新使用统计 | 校正并移至 qq-sticker-send 的发送前原子更新使用统计 |
| qq-sticker-maintenance | Milky 状态不影响计数 | 合入 qq-sticker-send 的 Action 成功、失败或未知均计数 |
| qq-sticker-maintenance | 统计写入失败不重复发送 | 校正并合入 qq-sticker-send 的统计 claim 写入失败：失败发生在发送前，禁止发送 |

概要 Requirement 中独有的 plugin-data API、随机不透明 ID、流式 SHA-256、Web 暂存边界和安全媒体响应例外已转入详细主条款。生命周期中两组贴纸库要求合并，原场景及跨实例所有权保留。

## 活动 change 对齐

- add-idle-session-wakeup：配置快照保留热白名单例外；候选使用当前有效规则；空白名单沿用阻止语义；主动策略仍仅启动解析。
- add-group-moderation-workflow：MODIFIED 块采用最新工具场景和 Action 工具结果范围，保留计划中的群管授权增量。
- add-qq-sticker-library：proposal、design、delta 和任务措辞统一为发送前 claim，保留 Web 维护基线与未来自动收集边界。
- add-milky-relationship-system：审阅后无本次整理所需修订。

任务状态仍分别为 0/14、0/31、0/29、0/28。未实现的主动唤醒、群管、自动贴纸收集及关系系统没有同步为主规范能力。

## 验证与限制

- 主规范严格校验：30/30 通过；活动 change 严格校验：4/4 通过。
- 相对链接、Requirement 唯一性、同一 Requirement 内场景唯一性及 MODIFIED 块基线场景保全检查通过。
- 聚焦测试分四组运行：342 通过/1 跳过、158 通过、74 通过、39 通过，共 613 通过/1 跳过。
- 跳过项为 Hermes 宿主不可用；本次未验证真实 Hermes/Milky 集成或进行真实发送。
- OpenSpec 仍对部分长 Requirement 给出 INFO 建议；这不影响严格校验，后续拆分应以完整保留契约为前提。
