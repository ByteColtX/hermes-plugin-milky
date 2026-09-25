# Proposal

## Why

当前入站白名单只在启动时解析，管理员无法通过 QQ 指令立即启停会话，而且未放行会话中的管理命令会在分发前被拒绝。需要提供由 Hermes core 授权、跨重启保留的热白名单管理入口，并把空白名单统一改为全部阻止，避免删除最后一项意外扩大入站范围。

## What Changes

- **BREAKING**：`MILKY_ALLOWED_CHATS` 未配置或为空、对应原生设置 `allowed_chats: []`，均表示阻止全部普通入站；全部放行必须显式使用 `group:*` 和 `dm:*`，不增加模式或黑名单字段。
- 新增纯文本 `/milky allowlist list`、`/milky allowlist add [目标]`、`/milky allowlist del [目标]`；remove 作为 del 的等价别名；增减省略目标时使用可信消息来源中的当前会话。显式目标接受具体 chat key 或已有命名空间通配符。
- 所有 slash 指令的权限统一由 Hermes core 管理，包括白名单的 list/add/del；插件不读取或解释管理员名单、不自行判断角色、不为子命令增设权限。allow_admin_from、group_allow_admin_from、普通用户命令许可及未配置时的行为均服从 core。当前 core 按顶层 /milky 授权，其允许结果同样适用于 allowlist 子命令。
- 为白名单管理指令设置不依赖发送者角色的路由例外，允许从未放行会话进入 Hermes core 命令分发；core 拒绝时不执行插件管理读写或群状态准备。保留 canonical、自身消息和去重；管理读写不检查来源或目标群状态，回执遵守既有发送边界。其他命令及普通正文不享有该路由例外。
- 指令修改通过宿主设置持久化到当前 profile 的 `plugins.entries.hermes-plugin-milky.settings.allowed_chats`，读回核验后发布完整运行快照；保持原配置来源优先级，不写环境文件、不另建存储。
- 新授权群首次收到获准入站的消息时按需准备群身份与 Bot 成员状态；查询失败拒绝该消息，不撤销已保存规则。add/del 仅机械增减指定字面规则；通配符与具体条目相互独立，不展开、合并或联动删除，不生成隐式排除项；回执以简洁中文报告条目增减结果；list 完整输出，不分页，保留原配置来源名称，差异提示重启 Gateway。
- 在线生效以提交确认点为界，成功回执后的新消息使用新规则；撤销时丢弃插件尚未交接的旧待处理上下文，阻止失效批次后续交接，不撤销已交给 Hermes 的任务或更改出站授权。
- 修正文档、配置说明、Dashboard 空值提示、初始化扫描契约与测试；Dashboard 保存仍按既有重新加载流程生效，不新增跨进程热更新服务。

## Capabilities

### New Capabilities

- `hot-chat-allowlist`：定义指令语法、core 独占命令授权、默认当前会话、规则操作、持久化与运行状态、并发和撤销边界。

### Modified Capabilities

- `configuration`：空/缺省白名单全部阻止；白名单管理指令作为启动快照的有限在线更新入口。
- `inbound-gates`：空名单拒绝与交由 core 授权的管理命令路由例外。
- `slash-commands`：所有 slash 权限归 core，以及白名单管理指令在未放行会话的分发、可信来源与无群查询的管理边界。
- `mute-tracking`：空名单不扫描成员，新增授权群在首次获准入站时按需准备，保持普通消息禁言约束。
- `plugin-lifecycle`：空名单可完成连接并接收管理事件，动态策略与任务随实例清理、重连恢复持久设置。
- `milky-web-dashboard`：展示空值全部阻止，并区分持久化设置与未确认的在线状态。

## Impact

涉及根 register/adapter_factory 的白名单读取器装配、完整 connect 的重新读取、/milky 参数分发、MuteTracker 未跟踪群准备与扫描诊断，以及配置、Gate、入站命令交接、群状态维护、插件生命周期、设置持久化与 Dashboard 文案，以及对应测试和安装迁移文档。沿用现有 Hermes 命令分发和设置能力，不修改 Hermes Core、不新增 Milky Action 或 Agent Tool，不赋予管理员普通消息自动放行权限。

本地源码已证明当前白名单快照、Gate 前置、群状态初始化筛选、宿主逐键设置保存与按顶层命令授权及无管理员时关闭命令门禁的行为；插件遵从这些 core 决策。可信命令上下文跨宿主分发的保留、实际 QQ 回复、并发持久化与热生效尚未验证，必须通过后续契约测试及真实集成 evidence 区分确认与 unsupported。

与未实现的 `add-idle-session-wakeup` 存在共享白名单依赖：后者落地时需读取最新有效策略，不再依赖启动快照或“普通入站空值放行”的旧假设。本提案记录依赖，不修改其他 change，也不实现主动唤醒。
