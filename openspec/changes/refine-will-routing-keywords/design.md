## Context

See `proposal.md` for the motivation and scope. 当前 routing engine 已经从规范化的
`WillInput` 消费 friend/group 场景、self/all mention、quote 和普通消息信号；现有实现
使用固定优先级短路，配置仍保留 `group`、`image` 和 `mentionHere`。本 change 只调整
本地确定性策略和配置 schema，不新增 Milky Action、Hermes API 或外部依赖。

## Goals / Non-Goals

**Goals:**

- 让所有适用 routing 规则同时参与决策，使用“任一 trigger 即 trigger”的 OR 语义。
- 让 `allMessage` 成为每条普通 `message_receive` 都会命中的规则。
- 让关键词成为独立的确定性 trigger 条件，并明确空数组不产生关键词命中。
- 通过配置校验阻止旧字段继续产生歧义，并保留可预测的错误分类。

**Non-Goals:**

- 不修改 inbound image segment 的解析、资源补全或 Hermes media 所有权。
- 不删除 willingness 的 `imageGain`、willingness 关键词 multiplier 或其概率算法；
  routing keywords 与 willingness keywords 是两个不同配置层次。
- 不把 `mentionHere` 从底层安全 raw/扩展保留能力中删除，也不为 Milky v1.3 猜测 here
  信号。
- 不让 poke/nudge 绕过 observe-only 系统事件边界。
- 不在本 change 中实现代码；apply 阶段才执行实现和测试。

## Decisions

### 1. 使用命中规则的 OR 合并，而不是优先级短路

对普通 `message_receive` 计算所有适用规则：friend 消息适用 direct，self/all mention、
quote 和关键词按信号适用，allMessage 始终适用。最终结果为：

```text
任一适用规则 == trigger  -> trigger
否则                     -> wait
```

这样 direct 为 wait 不会阻止关键词或 allMessage 的 trigger，mention/quote 之间也不会
互相覆盖。继续采用旧优先级短路会使“只要命中一项即可触发”无法成立，因此不采用该
替代方案。

### 2. 将 allMessage 定义为全消息规则

`allMessage` 不再是 `group` 的别名，也不只是没有特殊信号时的 fallback；它对每条普通
`message_receive` 产生一次命中。配置为 wait 时提供默认等待行为，配置为 trigger 时
提供全消息触发行为。其动作仍通过 OR 合并，因此不能抵消其他规则的 trigger。

### 3. 关键词使用规范化正文的直接匹配

`routing.keywords` 只接受非空字符串数组。规范化正文包含任意一项时产生一个确定性的
trigger 命中；不计算出现次数，不使用概率，不读取 raw、媒体 URL 或其他 metadata。
空数组等同于没有关键词命中，消息是否最终 wait 由 allMessage 及其他适用规则决定。

采用直接子串匹配是为了保持协议边界简单、可测试并与现有安全正文输入一致；词法分词、
大小写折叠、正则表达式和语义兴趣判断均不纳入本 change。

### 4. 以 breaking schema 迁移替代隐式别名

配置解析器、默认配置和公开示例统一使用 `allMessage` 与 `keywords`，并删除 `group`、
`image`、`mentionHere`。不保留旧字段别名，避免同一消息同时产生旧新两种规则或让部署者
误以为 image/here routing 仍受支持。

## Risks / Trade-offs

- [风险] `allMessage: trigger` 会使每条普通消息触发。→ 在配置示例和测试中明确其全局
  语义，默认值保持 `wait`。
- [风险] 直接子串匹配可能产生兴趣关键词误命中。→ 保持关键词是显式确定性规则，不
  承诺分词或语义匹配，并用边界测试固定行为。
- [风险] 旧配置因 breaking 字段被拒绝而无法启动。→ 提供迁移说明和配置校验测试，
  部署前将 `group` 改为 `allMessage` 并移除两个废弃字段。
- [风险] 删除 image 专用 route 后，图片消息的动作可能与旧配置不同。→ 保留 image
  segment 与 willingness 信号，仅将 routing 决策交给其他命中规则和 allMessage。
- [风险] 本 change 的 delta spec 与主 spec 暂时并存。→ 实现并验证完成后，再按归档
  流程同步 `will-routing` 与 `configuration` 的主 spec；在此之前不宣称能力已交付。

## Migration Plan

1. 将现有 `routing.group` 改为 `routing.allMessage`。
2. 删除 `routing.image` 与 `routing.mentionHere`。
3. 按需填写 `routing.keywords`；空数组不产生关键词 trigger。
4. 根据需要选择 `allMessage: wait` 或 `allMessage: trigger`，再确认 direct、mention、
   mentionAll 和 quote 的 OR 组合结果。
5. apply 阶段完成实现、回归测试和质量门禁后，再同步主 spec；若需回滚，恢复上一版
   完整配置 schema 与已验证的旧实现版本。

## Open Questions

无。本设计采用用户补充确认的“无优先级、任一 trigger 即触发”语义；未命中关键词时，
仍由其他适用规则（尤其 allMessage）参与最终 OR 结果。
