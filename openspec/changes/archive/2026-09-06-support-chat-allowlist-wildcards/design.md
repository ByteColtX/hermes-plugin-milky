## Context

当前实现由 `config` 解析逗号分隔的 `MILKY_ALLOWED_CHATS`，把每一项规范化为具体
`group:<数字>` 或 `dm:<数字>`；`gates` 随后对规范化后的完整 chat key 做精确匹配。
因此当前代码尚未支持本 change 的 `dm:*` 和 `group:*` 规则。规范目标和边界见本 change
的 proposal 及两个 delta spec；本设计只说明跨配置解析和 Gate 判断的衔接方式。

## Goals / Non-Goals

**Goals:**

- 在启动期区分具体 chat key 与两个受支持的命名空间通配符，并以不可变规则集合交给入站 Gate。
- 让 Gate 对具体 key 做精确匹配，对通配符做固定前缀匹配，同时保持 `group`/`dm` 隔离。
- 让现有具体白名单、空白名单、重复条目、配置错误分类和 Gate 固定顺序继续成立。
- 通过配置测试和 Gate 测试覆盖混合授权、跨命名空间拒绝及非法通配符。

**Non-Goals:**

- 不把 `*` 扩展成当前已知群列表或好友列表，不在运行时联网补全或刷新白名单。
- 不把通配符当作 canonical chat key；canonical、dedup、per-chat admission、`MILKY_HOME_CHANNEL`
  和出站目标仍只接受具体 `group:<id>` / `dm:<id>`。
- 不改变 SelfMessage、MutedGroup 的判断、Gate 顺序、Will、系统事件、temp 忽略或 ToolSpec 授权。
- 不支持任意 glob、正则、前缀匹配或跨命名空间的单个 `*` 规则。

## Decisions

### 保留规则文本，使用显式的两种匹配分支

解析后继续使用不可变的字符串规则集合：具体规则保留现有规范化结果，`dm:*` 和 `group:*`
作为仅有的两个特殊字面值保留。Gate 先检查完整 chat key 的精确命中，再根据 chat key 的
命名空间检查对应的特殊字面值；不把用户输入编译成正则或通用 glob。

这样可以兼容现有配置结构和 `allowed_chats` 快照，避免枚举外部会话，也能保证一个通配符
不会因为数值部分相同而匹配另一种场景。替代方案是为每个已知群/好友展开具体集合，但会
引入过期状态、额外网络依赖和不必要的内存增长；通用 glob 则会扩大授权语法和误匹配面。

### 由共享的 chat-rule 校验边界处理构造和解析

配置解析与直接构造 Gate registry 都必须接受同一组规则格式。实现应将“具体 chat key 或
完整命名空间通配符”的校验和具体 key 规范化集中到现有身份边界，避免配置路径允许的规则
在测试或其他调用路径被 Gate 重新解释成另一种语义。`MILKY_HOME_CHANNEL` 继续调用只允许
具体 chat key 的校验，不复用通配符规则校验。

非法规则只返回安全的配置错误类别，不回显原始条目；空条目仍按当前配置契约拒绝。规则
去重发生在规范化后，因此重复具体 key 或重复通配符只保留一条。

### 通配符只影响入站 allowlist

规则只在 ChatAllowlist gate 的白名单判断中消费。消息在此之前仍通过已有 canonical 身份
流程生成具体 chat key；temp 消息仍在该流程前被忽略。命中后继续按原顺序进入 MutedGroup
和 Will，未命中则沿用 `chat_not_allowed` 并停止后续处理。

### 文档和测试保持同一可观察契约

README 和 manifest 配置提示应同时列出四种条目形式，并说明空值与场景隔离；ARCHITECTURE
中的 Gate 和配置表应使用同一表述。测试应分别验证解析后的规则、Gate 对 friend/group 的
命中结果、精确规则与通配符的混用、非法形式，以及拒绝不触发下游副作用；不需要新增
fixture、依赖或真实 Milky 网络调用。

## Risks / Trade-offs

- [通配符会扩大允许的入站会话范围] → 配置提示明确说明 `dm:*` / `group:*` 的全量授权含义，
  并保持空白名单与显式白名单的安全边界不变。
- [规则表示同时包含具体 key 和特殊字面值] → 通过集中校验、不可变快照和只允许两个完整
  通配符的匹配分支限制语义，禁止任意 glob 扩展。
- [直接构造 Gate 的调用方可能传入非法规则] → Gate 构造路径复用同一规则校验，非法值在
  进入判断前失败，不静默放宽授权。

## Migration Plan

无需数据迁移。升级后，原有具体白名单保持相同含义；部署者可在重启时将配置改为
`dm:*`、`group:*` 或与具体条目混用。回滚到旧版本前应移除通配符条目，否则旧版本会按
非法配置拒绝启动。实现和测试完成后，将 delta spec 与主 spec 合并并归档；在此之前主
`openspec/specs/` 仍记录旧的完整 key-only 契约。
