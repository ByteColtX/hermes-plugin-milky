## Why

当前 `MILKY_ALLOWED_CHATS` 只能逐个列出完整的 `dm:<id>` 或 `group:<id>`，当部署者希望允许某一类全部会话时，需要持续维护不断变化的 QQ 号列表。增加按命名空间限定的通配符，可以表达“所有私聊”或“所有群聊”，同时保留现有白名单的显式授权边界。

## What Changes

- 允许 `MILKY_ALLOWED_CHATS` 使用精确的 `dm:*` 和 `group:*` 条目，分别匹配所有合法 friend 私聊和 group 群聊。
- 保留具体 chat key 与通配符的逗号分隔混用；通配符只匹配对应的 `dm:` 或 `group:` 命名空间，不跨场景、不按数值部分匹配。
- 继续对条目执行空白裁剪、重复项归一化和非法格式拒绝；除上述两个完整通配符外，部分通配符、未知前缀、空条目和非法 ID 仍使启动配置失败。
- 保持空 `MILKY_ALLOWED_CHATS` 放行合法 friend/group 消息、`temp` 在 Gate 前忽略，以及 Gate deny 不进入后续 pipeline 的既有行为。
- 更新配置提示、架构说明、OpenSpec delta 和回归测试，覆盖精确匹配、场景隔离、混合配置与非法通配符。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `configuration`: 扩展 `MILKY_ALLOWED_CHATS` 的可接受条目格式，明确通配符的校验和启动期解析语义。
- `inbound-gates`: 将非空白名单的匹配规则扩展为完整 chat key 精确匹配或对应命名空间通配符匹配。

## Impact

- 影响 `config` 的 `MILKY_ALLOWED_CHATS` 解析与配置表示、`gates` 的 ChatAllowlist 判断，以及相关配置和 Gate 测试。
- 影响 `README.md`、`plugin.yaml` 和 `ARCHITECTURE.md` 中的配置说明；不新增依赖，不改变公开插件入口、Gate 顺序、Will、出站目标或工具授权。
