## Why

Milky 入站消息目前会被映射为不允许 Hermes gateway control 的普通消息，导致 Hermes
内置斜杠命令不能从 QQ 消息可靠执行，插件也没有可复用的斜杠命令注册入口。需要建立
独立于 Will 和 Agent 正文的命令通道，并先提供 `/milky` 诊断 Milky 实现信息。

## What Changes

- 新增 Milky 斜杠命令 capability：在 canonical、dedup 和 Gate 之后、Will 之前识别命令。
- 将合法的 Hermes 内置命令映射为保留原始斜杠文本的 `MessageEvent`，交由 Hermes 现有
  内置命令分发，不把命令写入 wait buffer、Will 或 Agent 普通正文。
- 通过 Hermes `ctx.register_command()` 预留插件侧斜杠命令，并首批注册 `/milky`。
- `/milky` 无参数时调用 `get_impl_info`，使用 HTTP POST、Bearer 和 `{}` 请求体；成功时将
  服务端返回的完整原始 JSON envelope 直接作为回复正文，不加说明文字、代码围栏或字段摘要。
- `/milky` 带参数、适配器未连接、Action 被拒绝、响应 malformed 或传输结果未知时，返回
  安全且可分类的错误，不回显凭证、完整错误响应或其他敏感内容。
- 复用 Hermes 对内置命令和插件命令的现有冲突、权限和 Agent 忙碌处理；插件不复制
  Hermes busy/follow-up 队列，也不注册任意 Milky Action catalog。
- 增加脱敏协议 fixture、命令路由/生命周期测试，并更新架构和能力矩阵，明确当前实现状态。

## Capabilities

### New Capabilities

- `slash-commands`: Milky 消息中的 Hermes 内置斜杠命令通道、插件侧命令注册以及首批
  `/milky` 实现信息诊断命令。

### Modified Capabilities

无。该 capability 对既有普通消息、Gate、Will、HTTP Action 和系统事件规范增加命令侧
扩展，但不改变其普通消息行为；实现时同步更新相关文档和交接测试。

## Impact

- 影响 `inbound` 的 Hermes `MessageEvent` 映射与命令识别、根插件注册入口、Milky client 的
  `get_impl_info` 原始响应交接，以及相关 fixture、单元/集成测试。
- 影响 Hermes platform adapter 的可观察入站行为：命令仍经过身份、去重和硬性 Gate，之后
  由 Hermes 处理内置命令或插件命令。
- 不修改 Hermes core；当前宿主 `ctx.register_command()` handler 没有显式 source 参数，
  `/milky` 首版使用生命周期绑定的单一活动 Milky client；无活动 client 或活动 client
  不唯一时安全返回 `unsupported`。
- 不新增配置项、manifest 中的任意 Action 工具、Milky WebHook/WebSocket、插件 Agent
  执行队列或新的媒体/持久化所有权。
- 当前仓库仍有未完成的 multimedia active change；本 proposal 只描述斜杠命令增量，不能
  将其他 active change 的目标能力视为已交付。
