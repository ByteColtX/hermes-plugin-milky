# Design

## Context

见 [proposal.md](proposal.md) 的 Why。当前 `MilkyAdapter.send()` 在连接检查后将普通文本直接委托给 outbound sender；媒体和文件使用独立入口。Hermes 在 `gateway/run_turn.py` 中声明 `_UNEXPECTED_SILENCE_REPLY`，普通 turn 和 queued follow-up 都会用该文案替换不应面向用户的 silence marker。

实现受限于“不修改 Hermes core”：Gateway 在 adapter 调用前写入投递 obligation，且以发送结果的 `success` 标志终结 obligation。Gateway 没有与插件协商的独立“已过滤”状态。

## Goals / Non-Goals

**Goals:**

- 让普通文本入口可复用精确文本拦截逻辑，并只登记本次要求屏蔽的兜底文案。
- 精确匹配后不触发 Milky 网络 Action，也不进入 Hermes 自动重试；不匹配文本保持原有处理。
- 在匹配项旁注明 Hermes 上游常量位置，并提醒维护者随上游文案变更同步更新。

**Non-Goals:**

- 不修改 Hermes core、Silence 判定、回复持久化或其他平台投递。
- 不做模糊匹配、子串匹配、关键词拦截、配置项或管理界面。
- 不清除会话中已保存的文本，也不拦截媒体或文件。

## Decisions

### 拦截位置与范围

在 adapter 的普通文本出站边界、调用现有 sender 之前执行拦截。保留连接状态检查在前，使断开状态继续返回既有 unsupported 结果。媒体和文件入口不经过该拦截器；拦截逻辑不读文件、不物化媒体、不创建后台任务。

### 通用机制使用登记值的完整相等比较

建立可复用的文本拦截器，接收登记的完整字符串值；本次只登记 Hermes 的 silence-marker fallback 文案。比较不做 trim、大小写折叠、Unicode 归一化或分词，避免扩大屏蔽范围。初版不引入配置，未来新拦截值通过明确登记加入。

匹配项旁的中文注释应指向外部仓库 `hermes-agent/gateway/run_turn.py::_UNEXPECTED_SILENCE_REPLY`，注明它是上游提示文案，修改上游文案时须同步更新本地精确匹配值和对应测试。

### 过滤作为终止处理返回

若把命中结果作为失败返回，Gateway 可能执行重试、失败 obligation 重投或用户可见失败通知；因此 adapter 将拦截视为已处理的终止 no-op，结束重试流程，并且不调用消息 Action。结果不得包含伪造的远端 `message_id`。这不能表达真实的 Milky 投递成功：在不改 Hermes core 的前提下，Gateway 仍会按既有 `success` 语义把 obligation 记为 delivered。该账本语义是已知取舍，不能通过伪造远端 ID 或修改 Gateway 规避。

替代方案是返回失败/unsupported，但它可能使 Hermes 的重试或 delivery-ledger 重投再次调用拦截器，且依赖 core 对错误的处理；因此不作为本次方案。

## Risks / Trade-offs

- [Gateway ledger 将本地过滤记为 delivered] → 在插件不改 core 的约束下无法准确区分 filtered 与 remote-delivered；明确保留该 limitation，不伪造 message ID。若未来要求账本反映真实平台投递状态，需要 Hermes core 提供显式 filtered/no-op 结果契约。
- [上游修改文案后精确匹配失效] → 在匹配值旁保留源码位置和更新提醒，并用完整字符串匹配测试锁定当前约定。
- [拦截范围配置错误导致误屏蔽] → 禁止子串和规范化比较，并覆盖完整匹配、嵌入较长正文及细微字符差异用例。

## Migration Plan

无需数据迁移或运行时配置变更。回滚时移除普通文本出站拦截器及对应登记值，恢复原有 adapter-to-sender 委托；不涉及 Hermes core 状态。
