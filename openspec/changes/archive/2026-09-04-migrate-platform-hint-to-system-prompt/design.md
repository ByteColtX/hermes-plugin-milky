## Context

See `proposal.md` for the motivation and `specs/milky-platform-prompt-guidance/spec.md` for the
observable contract. 当前根入口把整段操作指引作为静态 `platform_hint` 注册；`MilkyAdapter`
在既有 `MuteTracker.initialize()` 完成后已经持有 `self_id` 与 `nickname`，但注册阶段尚未
创建 adapter，不能在注册时读取账号信息。

Hermes 的 `register_system_prompt_section` 接受静态字符串或只读 session-info 回调，section
固定在 `after_memory`，并按新 session 渲染后冻结。该扩展点属于 Hermes 已有宿主 API；本 change
只在 Milky 插件内调用它，不改 Hermes core、Agent 队列或 prompt 组装逻辑。

## Goals / Non-Goals

**Goals:**

- 保证静态 `PLATFORM_HINT` 与动态 system prompt section 的文案来源单一，避免迁移后重复或漏句。
- 让 section 首行使用连接成功后确认的账号 UID 和昵称，并在渲染时保持无网络、只读和可重入。
- 保持现有 `connect()` 初始化顺序、SSE 开放门槛及连接失败的 fail-closed 行为。
- 在支持和不支持 section API 的 fake host 上覆盖注册、内容完整性、动态身份和降级路径。

**Non-Goals:**

- 不增加 Milky Action、SSE 请求、缓存持久化、账号重扫描或每轮动态 prompt hook。
- 不修改 Hermes core、其他 platform plugin、全局 platform hint 解析或 Agent session 冻结机制。
- 不改变 QQ ToolSpec、媒体发送、CQ-compatible 语义、Will、Gate、出站路由或消息生命周期。
- 不为尚未完成连接的 adapter 生成 `unknown`、默认 UID/昵称或从消息/配置推断身份。

## Decisions

### 1. 将静态文案拆成首句和 section 正文两个常量

`PLATFORM_HINT` 只保留既有首句；迁移正文保留原有英文句子、标点、顺序和占位符，并由
section renderer 在其前面拼接动态身份行。测试将逐项断言首句严格相等、正文不再出现在
platform hint 中、section 正文完整保留，避免以“包含若干关键词”掩盖文案丢失。

选择在插件内维护这两个常量，而不是在运行时切片当前 hint，是为了让迁移后的边界稳定、
可审计，并防止后续修改首句时误把正文重新带回静态 hint。备选方案是继续把完整 hint 传给
Hermes 再追加 section；该方案会重复注入长期指引，故不采用。

### 2. 由注册实例持有共享的账号身份快照

根入口在组装 Milky platform 工厂时创建一个小型进程内身份快照，并把同一个快照同时交给：

- system prompt section 的回调，用于无副作用地读取；
- 该注册实例创建的 `MilkyAdapter`，在 `_initialize_state()` 成功完成既有初始同步后写入。

快照只保存已校验的 UID 和昵称，并使用同步保护提供不可变读取；回调不持有 adapter、不访问
client，也不调用任何异步方法。只有完成连接所需状态同步后才发布快照，初始同步失败时回调
返回空内容，使 Hermes 跳过 section 而不是注入占位身份。选择注册级快照是因为 Hermes 回调
只提供 session metadata，不提供 adapter；备选方案是从回调访问全局 client 或重新查询登录
信息，都会越过插件生命周期边界并产生网络副作用。

快照在成功连接后保持最近一次确认的身份，断开时不主动伪造或重新读取账号；Hermes 对同一
session 的 section 冻结/恢复仍由 core 按既有契约负责。

### 3. 在根注册边界按能力探测登记 section

当上下文提供可调用的 `register_system_prompt_section` 时，注册一个稳定的
`hermes-plugin-milky.qq-platform-guidance` section，使用 `after_memory` 位置和宿主默认的
有界字符策略；section 以回调形式登记。`register_platform` 仍只接收首句 `PLATFORM_HINT`，
并将同一身份快照闭包传给 adapter factory。

当旧宿主没有该方法时，只跳过 section 登记并继续平台注册。这里仅做能力探测，不尝试 monkey
patch、导入 Hermes 内部实现或把正文恢复到 `platform_hint`；因此兼容降级不会改变注册阶段
的无网络、无 SSE 和无长期任务约束。备选方案是强制要求新宿主并让注册失败，但这会破坏已有
轻量 fake/旧宿主的安全平台注册边界。

### 4. 依赖既有连接时序，不改变 prompt 生命周期

身份快照更新放在登录信息和群禁言初始同步成功、adapter 已具备可开放普通消息条件之后，
不新增一次登录 Action。section 依赖 Hermes 新 session 的首次 prompt 渲染；若宿主在连接
前就创建并冻结 session，插件不会在之后强行重建或注入 prompt，这是 Hermes section 冻结语义
的边界，静态首句仍可用。测试会验证 renderer 重复调用只读取同一快照，不增加 fake client
调用，也不影响 event stream、pipeline 或 sender。

## Risks / Trade-offs

- [宿主版本缺少 section API] → 旧宿主只能得到首句，完整操作指引不会回退到旧 hint；保留安全
  注册并覆盖该分支，实际支持 section 的 Hermes host 通过集成 fake context 验证。
- [prompt 在连接前被冻结] → 该 session 不会获得动态身份行；不伪造身份、不强行修改 Hermes
  core，依赖现有“初始化完成后才开放普通消息”的时序，并记录为兼容边界。
- [昵称包含换行或其他异常格式] → renderer 保持身份首行的单行结构，只使用已解析的字符串
  字段并按实现中的安全单行规则处理；不把原始响应、URL、token 或消息正文带入 section。
- [注册级快照被多个 adapter 共享] → 使用同一注册实例的最新成功连接身份，符合 Milky 单一
  platform 生命周期假设；不引入跨实例持久化或隐藏的全局账号选择逻辑。
- [Hermes section 字符预算或冻结规则变化] → 使用稳定 ID、宿主规定的 `after_memory` 和
  默认预算，并以真实可调用的宿主 API 测试注册及渲染结果；超限仍交给 Hermes 的既有安全
  跳过策略。

## Migration Plan

1. 先补充静态文案契约和 fake host，再实现身份快照、section 注册和 adapter 更新。
2. 运行聚焦 pytest、完整 pytest、Ruff、format、build、diff 检查，并运行严格 OpenSpec
   校验；必要时只做不写入真实聊天的本地 smoke。
3. 发布后由 Hermes 在新 session 中使用 section；无需数据迁移或配置迁移。
4. 若需回滚，移除 section 注册和快照交接，并恢复原 `PLATFORM_HINT` 文案；该回滚不触及
   Hermes core 或 Milky 远端状态。

未来仅在实现、自动化测试和真实宿主兼容性证据齐备后归档本 change；未确认的旧宿主支持和
连接前 session 行为保持在本 change 的降级边界内，不通过归档宣称已验证。

## Open Questions

无。宿主缺失 API 和连接前 prompt 的行为已按安全降级写入规范，后续不应改变本 change 的
验收标准。
