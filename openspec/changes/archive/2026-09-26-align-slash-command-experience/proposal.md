# Proposal

## Why

当前 `/milky allowlist` 已使用清晰的分段帮助、中文结果和可执行提示，而无参数 `/milky` 仍返回英文技术错误，`/milky sticker` 则直接返回 JSON 和单行长 usage，用户在同一命令树中需要切换阅读方式。以 allowlist 的中文反馈为基准，精简并统一全部插件命令帮助，可提高功能发现、错误恢复和结果判断的一致性；同时补充独立运行状态入口，避免把协议实现信息当作当前运行健康证明。

## What Changes

- 建立适用于全部现有插件侧 slash 输出的统一约定：帮助和查询使用 `Milky · 功能名` 标题，帮助只保留 Usage、Commands 及确有必要的选项说明或少量示例，不套完整 man-page 章节，操作反馈使用中文结果标题、必要对象和简洁说明。
- 新增 `/milky help`、`/milky sticker help`；空参数 `/milky sticker` 显示相同贴纸帮助。保留无参数 `/milky` 的实现信息查询和 allowlist 的既有空参数帮助语义。
- 帮助以简洁为先，借用方括号等常见参数记法；Commands 只列真实子命令，默认行为用一句话说明。allowlist 在 Commands 末尾以一行 e.g. 展示 add/del 共用的具体目标和通配符，取消独立 Targets、Examples 分段，保留缺省目标说明。
- 新增 /milky status，只读展示可确认的插件运行状态、SSE 状态、本次运行时长、运行白名单条数及配置一致性；不主动探测网络，不枚举规则或泄露配置，无可信实例或字段证据时明确暂不可用或未知。
- 统一非法参数为“指令格式不正确。”以及就近的 Usage、Help；覆盖全部 sticker 维护动词和 allowlist 子命令，不回显非法原始输入。
- 将 sticker 查询、单项维护、批次、预览、空结果和失败转换为可读中文，保留必要条目 ID、字段来源、使用统计及实际结果差异；补充 `sticker remove` 为 `del` 等价别名，与 allowlist 保持删除操作习惯一致。
- 将协议信息失败转换为固定中文说明，区分未连接/归属不明、远端拒绝、无效响应和结果未知；保持内部安全分类和诊断能力。
- **BREAKING（展示格式）**：贴纸 slash 回执从 JSON 改为面向用户的文本，协议信息的英文错误前缀和旧标题不再保留，allowlist 帮助及格式错误布局同步精简。已有合法操作参数及其业务含义保持兼容；共享维护结果、Web JSON 和 Agent Tool 契约保持原样。
- 同步命令注册描述、README、文本契约测试与证据记录，精简 allowlist 布局并保留持久化/运行生效表达。

## Capabilities

### New Capabilities

无；复用已有命令与贴纸维护能力，不另建平行规范。

### Modified Capabilities

- `slash-commands`: 明确插件命令帮助层级、通用文本风格、上下文相关参数错误、协议信息反馈及只读运行状态查询，保留宿主授权、入站路由例外及生命周期边界。
- `hot-chat-allowlist`: 精简帮助与就近参数错误，保留全部目标、别名、授权及持久化/运行生效语义。
- `qq-sticker-maintenance`: 将 slash 回执改为统一中文文本，增加静态帮助和删除别名，细化列表、批次与 dry-run 的用户可见结果表达。

## Impact

- 涉及根注册描述、`slash_commands.py`、`stickers/maintenance.py` 和 `management/allowlist.py` 的展示边界，以及 adapter.py、milky/event_stream.py 中为 status 提供状态观察的生命周期边界；还涉及 README、相关 slash/allowlist/贴纸测试；实现时可共享静态文案约定，但不迁移业务状态所有权。
- `tests/test_sticker_maintenance.py`、`tests/test_sticker_search.py` 和 `tests/test_sticker_send.py` 当前把 slash JSON 用作业务测试输入，需迁移到已有结构化维护结果，并单独验证面向用户的命令文本。已有 Web 维护依赖不得改为解析中文文本。
- 现有 `hot-chat-allowlist` 明确要求旧帮助分段，本案通过对应 delta 调整布局及参数错误，保留标题、删除别名、中文状态和业务语义。`slash-commands` 与贴纸主规范中“返回固定分类”的表述需明确为语义分类，而非要求用户看到英文前缀或 JSON。
- 现有 adapter 在初始同步后标记就绪，早于 SSE 连接完成，SSE 内部重连也不等价于 adapter 停止；目前未暴露满足 status 的完整状态快照及本次运行计时，需要补齐本地观察能力，不能从日志或 client 数量推断健康。
- 本案只交付规划。源码和既有测试证明上述当前差异存在，尚未实施或完成真实 Hermes/QQ 新文案验收。
- 非目标：修改 Hermes 内置 slash 命令、Tool 原始返回、Web 页面文案、群管/关系/自动贴纸等未交付 change、授权规则、白名单外路由范围、贴纸算法/存储格式/限制/副作用。保留既有发送与长消息处理，不增加交互式确认、分页或任意 Action 调用。
