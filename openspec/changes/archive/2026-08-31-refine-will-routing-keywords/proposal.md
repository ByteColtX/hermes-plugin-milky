## Why

当前 routing 配置把 `group` 同时当作群聊类别和普通消息兜底，语义不清；`image` 与
`mentionHere` 在当前 Milky v1.3 入站信号中没有稳定、必要的 routing 入口。同时，兴趣
关键词只能出现在 willingness 的分数算法中，无法表达“命中即触发”的确定性路由。

## What Changes

- **BREAKING** 从 routing 配置和决策分支移除 `image`。
- **BREAKING** 从 routing 配置和决策分支移除 `mentionHere`；不影响底层未知 segment
  保留或未来协议扩展的安全边界。
- **BREAKING** 将 `routing.group` 重命名为 `routing.allMessage`，表示每条普通
  `message_receive` 消息都匹配的统一规则，而不再暗示仅适用于群聊。
- **BREAKING** routing 不再按规则优先级短路；所有命中的 direct、mention、mentionAll、
  quote、keywords 和 allMessage 规则都参与合并，任一命中规则为 `trigger` 即返回
  `trigger`，否则返回 `wait`。
- 新增 `routing.keywords` 字符串数组；规范化正文包含任意配置关键词时视为一个必定
  `trigger` 的命中项，不把关键词当作 willingness 的概率增益或 force 配置。
- 空关键词数组不产生关键词命中；若没有其他规则产生 `trigger`，消息返回 `wait`。
- 保留 direct、mention、mentionAll、quote 和 poke 的既有配置与系统事件边界；不改变
  inbound 的 image segment 解析、资源延迟补全或 willingness 的 `imageGain`。
- 更新默认配置、配置校验、routing 合并规则、公开示例和回归测试，拒绝旧字段而不静默兼容。

## Capabilities

### New Capabilities

无。该 change 扩展并调整已有 Will routing capability。

### Modified Capabilities

- `will-routing`: 移除 image/here 路由，增加 allMessage 兜底和确定性关键词触发。
- `configuration`: 更新 `MILKY_WILL_POLICY.routing` 的字段集合、默认值和非法旧字段行为。

## Impact

- 影响 `MILKY_WILL_POLICY.routing` 的公开 JSON schema，属于兼容性变更。
- 影响 routing engine、启动配置默认值和相关测试/文档；不需要新的 Milky Action 或
  Hermes API。
- 关键词只消费 normalizer 已生成的安全正文，不读取 raw、媒体 URL、凭证或执行外部 I/O。
- 本 change 只生成规划 artifacts；当前仓库的 Python 实现仍需后续 apply change 才会改变。
