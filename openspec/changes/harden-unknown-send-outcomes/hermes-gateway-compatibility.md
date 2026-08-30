# Hermes Gateway 兼容性记录

## 当前观察

Milky plugin 可以把一次已经进入 HTTP 边界、但没有收到可确认 envelope 的发送结果表达为：

```text
success=False
error_kind="transport_unknown"
retryable=False
```

该结果不能证明远端未执行，因此 plugin 不能吞掉异常、伪造成功或再次提交相同消息。

当前 Hermes Gateway 的发送决策先读取 `retryable`，再按错误文本匹配旧的网络错误和 timeout
模式。`transport_unknown` 且 `retryable=False` 的结果不满足这些分支，随后会进入 plain-text
fallback。于是宿主可能在第一次 POST 已被远端处理、但响应丢失时再次调用 plugin sender。

## plugin-only 兼容边界

Hermes core 只能只读诊断，不能修改或作为 Milky plugin 正确性的前提。当前 Gateway 会通过
adapter 实例动态调用 `_send_with_retry()`；MilkyAdapter 在这个已验证的分派边界覆盖该方法：

```text
return await self.send(chat_id, content, reply_to, metadata)
```

该覆盖只调用一次 Milky sender，原样返回成功、明确拒绝、本地拒绝或 `transport_unknown`；不调用
`super()`，不根据错误文本、正文或时间窗作判断，也不改变核心代码。Milky POST 有副作用，因此
不允许宿主通用 retry、失败通知或 plain-text fallback 再次提交任何 Milky 消息。

## plugin 侧验证和阻塞边界

fake Gateway contract 只用于说明目标语义，不能作为真实宿主已修复的证据。回归必须直接覆盖
MilkyAdapter 的一次性发送覆盖：确认未知结果原样返回、`retryable=False`、消息内容不改变，且
没有第二次 sender 调用或 plain-text fallback。本仓库不得用 monkey patch、错误文本、吞异常、
假成功或消息内容去重规避这一限制。
