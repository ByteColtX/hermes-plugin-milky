# Design

## Context

详见 proposal.md 的 Why。当前发送 Action 在通用 envelope 校验阶段先按 `status`/`retcode` 抛出错误，发送结果序号尚未进入发送结果解析；普通分段 sender 会在任一段失败时停止，并保留已发送序号，但 Hermes 只收到整体失败结果。主规范同时要求 HTTP 200 不得单独代表成功、可能产生副作用的未知结果不得自动重发，因此修复必须把“协议状态”“副作用证据”和“整体聚合”分开。

## Goals / Non-Goals

**Goals:**

- 在插件内部建立发送专用的结果归一化边界，明确区分 confirmed success、confirmed failure、unknown 和 malformed。
- 只使用经过确认的 Milky 发送契约或可验证关联证据将异常状态升级为成功；证据不足时保持未知/失败，不猜测。
- 让普通多段消息在逐段发送后按所有段的归一化状态聚合，最终段只提供整体成功时的最终消息 ID。
- 保持现有目标校验、`[SPLIT]` 顺序、最多三条、宿主 `SendResult` 映射和安全日志边界。

**Non-Goals:**

- 不修改 Hermes core、delivery ledger、恢复提示、宿主重试策略或任何 Hermes 公共类型。
- 不把 HTTP 200、非零/零 retcode、正文、关键词、Will 或时间顺序单独当作发送成功证据。
- 不改变普通多段消息的展示形式，不改成 forward，不为未知结果增加第二次 Action。
- 不在本 change 顺带解决 HTTPX 跨事件循环连接池问题；该问题已有独立 change。

## Decisions

### 1. 在发送边界保留原始协议状态，再进行专用归一化

通用 Action 调用继续负责 HTTP、JSON、envelope 结构和非发送 Action 的既有分类。发送 Action 需要额外保留足以判断副作用的安全字段，交给发送专用归一化器；该归一化器不得被其他 Action 复用。这样既避免全局放宽协议校验，也避免在通用层过早丢失发送证据。

备选方案是直接把所有 HTTP 200 当成功，因会把真实拒绝报告成成功而放弃；或只读取最终段状态，因会掩盖前段内容缺失而放弃。

### 2. 使用显式证据矩阵，不凭单字段猜测

每个发送调用先被映射到四态结果。只有发送契约明确声明可证明远端已接受/落地的证据组合，才允许进入 confirmed success；标准成功 envelope 仍必须包含有效远端 `message_seq`。协议拒绝且没有该证据保持 confirmed failure；请求已进入副作用边界但结果未确认保持 unknown；无法安全解析响应保持 malformed。

在 Milky 实际异常响应契约尚未确认前，新增 fixture 只记录脱敏字段形状和分类，不把猜测的 retcode、message 或扩展字段写成成功规则。若后续证据表明某类异常 envelope 带有可验证序号，则只为该发送 Action 和该明确形状增加规则。

### 3. 多段 sender 使用全量聚合，状态不可被最终段覆盖

sender 保留每个已发送段的顺序结果和远端序号。所有段为 confirmed success 时返回 Hermes success，最终段序号映射为 `message_id`，之前序号映射为 continuation；任一 confirmed failure 或 unknown 则返回首个安全失败分类，并保留已确认序号及失败位置。预检失败仍在首个 Action 前整体失败。

该设计不尝试让 Hermes core 理解 partial outcome；插件只交付它现有结果接口能表达的最诚实整体状态。

### 4. 日志分别记录 Action 证据分类和出站聚合分类

Action 日志记录发送专用归一化结果及必要的状态码/耗时；出站日志记录最终聚合分类和段数。日志不记录响应正文、消息正文、token、URL、路径或异常正文。对“协议状态异常但确认发送”的情况使用稳定的 accepted/confirmed-send 分类，避免底层和上层输出相互矛盾的 rejected 终态。

## Risks / Trade-offs

- [远端异常响应契约仍不完整] → 在协议证据确认前保持 unknown 或既有 rejected，不放宽成功条件；增加脱敏 fixture 和真实只读/受控验证记录。
- [已发送副作用无法被完全证明] → 不自动重发；保留安全序号和失败位置供宿主现有结果处理，避免重复发送扩大影响。
- [插件结果接口无法表达部分成功] → 继续使用现有 `message_id`、continuation 和安全分类字段；不伪造新的 Hermes core API。
- [日志分类与历史数据不一致] → 只在归一化边界统一分类，并增加 Action/出站日志断言，保留旧分类的兼容读取范围。

## Migration Plan

先以 fake transport 和脱敏协议 fixture 验证四态归一化、分段聚合和日志；再在 hermes-dev 执行只读或明确授权的受控发送验证，比较 Action 结果、出站结果和群内实际消息序号。部署仅替换插件代码并重启 Gateway；发现异常时回滚插件版本即可，不需要迁移 Hermes ledger 或修改宿主数据。

## Open Questions

- Milky 服务端在“消息已落地但 envelope 状态异常”时究竟提供哪些稳定字段，目前仍需从服务端协议或受控运行证据确认；该问题只影响发送专用证据矩阵，不改变其他规范。
