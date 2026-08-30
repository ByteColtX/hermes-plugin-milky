## Why

当前 Milky 适配器会把 Hermes 自动传入的当前消息 `reply_to` 交给出站 sender，导致每次
回复都可能被固定引用，模型无法自行决定只 @、只引用、同时执行或两者都不执行。同时，
模型输出中的 QQ 消息控制语法还没有被解析为 Milky segment，无法安全表达这些选择。

## What Changes

- 新增 Agent-facing 的 CQ-compatible 消息语法，识别 NapCat 消息格式文档列出的全部 CQ
  类型，并逐项尝试转换为 Milky segment。
- 在 `platform_hint` 中提供最小、稳定的 @/引用说明；实际每轮 uid 和 msg_id 继续从
  当前消息和 `channel_context` 的真实消息头读取，不写入静态提示。
- 将可以确认映射的 CQ-compatible 控制码解析为对应 Milky segment；未知 CQ 码、已知但
  没有 Milky 等价 segment 的类型或转换失败的单个 CQ 码，均原样保留为 text segment。
  CQ 码只作为 Agent 出站语法，不作为 Milky 或 OneBot 网络协议实现。
- **BREAKING**：Milky adapter 的 `_send_with_retry()` 不再使用 Hermes 自动传入的隐式
  `reply_to` 强制引用；是否引用由模型输出的 CQ-compatible 控制码决定。
- CQ 解析必须保持原始片段、参数和顺序；未知或未成功转换不返回 CQ 专用错误，也不静默
  丢弃内容，而是继续以普通文本发送。
- 在插件中打包一个只读的 `qq-reference` skill 模板，后续逐步补充更多 CQ 码和 QQ 工具
  说明；skill 标注每个 CQ 码的转换状态和 fallback 行为，不替代实际 ToolSpec。
- 补充 platform hint、完整 CQ 类型矩阵、原样 fallback、真实 ID、隐式引用取消、skill
  注册和安全降级测试。

## Capabilities

### New Capabilities

- `agent-facing-message-controls`: 定义 Agent 可见的 Milky QQ @/引用提示、真实 ID 来源、
  CQ-compatible 语法和缺失 ID 时的安全行为。

### Modified Capabilities

- `outbound-messaging`: 增加 CQ-compatible 文本到 Milky segment 的映射，并取消自动引用当前
  入站消息的出站行为。
- `plugin-lifecycle`: 增加插件 bundled skill 的只读注册和 `qq-reference` skill 可发现边界。

## Impact

- 影响 `__init__.py` 的 `platform_hint` 和 bundled skill 注册、`outbound/formatter.py` 的
  CQ 类型解析/转换、`adapter.py` 的 `_send_with_retry()` 以及出站测试和 OpenSpec 契约。
- 不改变 Milky HTTP Action、SSE、canonical、Gate/Will、`channel_context` 的历史消息格式、
  Hermes 媒体所有权或三个现有 QQ ToolSpec 的参数契约。
- 需要为插件增加 `skills/qq-reference/SKILL.md`；插件 skill 通过 Hermes 的
  `ctx.register_skill()` 以命名空间名称按需加载，不复制到用户全局 skills 目录。
