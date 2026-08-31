## Why

当前 Milky plugin 明确拒绝 `MILKY_HOME_CHANNEL`，因此 Hermes 的网关启动通知、cron 结果和其他系统级消息无法把 `milky` 作为稳定的默认投递平台。Hermes 已提供插件级 home-channel 与 standalone delivery 扩展点，现在需要为 Milky 补齐目标校验、运行时注册和两种 cron 执行形态的可观察契约。

## What Changes

- 新增可选的 `MILKY_HOME_CHANNEL` 配置，使用完整的 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>` chat key；启动时校验，未配置时不产生默认目标。
- 将 Milky plugin 注册为 Hermes 的 home-channel/cron delivery 平台，并通过 env enablement 将配置暴露给网关的 home-channel 状态与系统通知路径。
- 复用现有 Milky outbound sender 发送网关系统消息、cron 结果和其他受 Hermes 授权的非会话消息；不经过入站 Gate、Will、wait buffer 或 Hermes Agent turn。
- 支持网关内 live adapter 投递和独立 cron 进程的 standalone sender；两者都必须经过相同的目标、文本、分块、附件和错误分类边界。
- 明确 home channel 不能回退到默认频道、私聊或 origin；空配置、临时目标和非法目标必须在网络访问前失败。
- 更新配置、出站、生命周期、系统事件安全契约及 README/架构说明，移除“永不支持 `MILKY_HOME_CHANNEL`”这一过期边界；不修改 Hermes core，不新增任意 Milky Action catalog。

## Capabilities

### New Capabilities

- `home-channel-delivery`: 定义 Milky home channel 的系统/cron 消息投递、目标隔离、live/standalone 执行和失败降级。

### Modified Capabilities

- `configuration`: 将 `MILKY_HOME_CHANNEL` 纳入可选启动配置、manifest 声明和安全摘要契约。
- `outbound-messaging`: 规定 home channel 作为显式系统消息目标复用标准 Milky 出站路由，且不绕过目标校验与 SendResult 语义。
- `plugin-lifecycle`: 规定配置的 home channel 在插件注册/网关启动阶段可被 Hermes 识别，并参与既有的 home-channel 生命周期通知。
- `system-events-and-safety`: 区分 Hermes core 产生的受信系统投递与 Milky 入站系统事件；home channel 不得成为入站正文或未知事件授予的权限。

## Impact

- 影响 `config/`、`plugin.yaml`、根 `__init__.py`、`adapter.py`、`outbound/` 及 standalone cron 投递辅助代码，并新增配置、注册、出站和 cron fixture 测试。
- 影响 Hermes plugin registry 的可选扩展点使用：`cron_deliver_env_var`、`env_enablement_fn` 和 `standalone_sender_fn`；Hermes core 代码保持只读，不作为本仓库的提交内容。
- 影响 `ARCHITECTURE.md`、`README.md` 和相关 OpenSpec 主/变更 spec 的能力矩阵，但不改变 SSE、canonical/dedup、Gate/Will、媒体所有权或 Milky Action 协议。
- `MILKY_HOME_CHANNEL` 是新增可选配置，不会改变未配置 home channel 时普通 friend/group 收发的现有语义；凭证、真实 ID、正文、媒体路径和 live 响应仍不得进入日志、fixture 或提交。
