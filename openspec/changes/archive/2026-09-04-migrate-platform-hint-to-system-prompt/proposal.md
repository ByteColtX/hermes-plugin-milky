## Why

当前 Milky 的完整操作指引全部作为静态 `platform_hint` 注入，无法携带连接后才确认的 QQ
账号身份，也让平台提示与长期 system prompt 的职责混在一起。Hermes 已提供有界的系统提示
section 扩展点，因此应把稳定的 Milky 操作指引迁移到该扩展点，并在连接完成后补入真实账号信息。

## What Changes

- 将 `PLATFORM_HINT` 收敛为首句 `You are communicating via Hermes's Milky QQ platform.`。
- 新增 Milky 专属 system prompt section，完整承载原 `PLATFORM_HINT` 的其余文案，并以
  `Your QQ uid is {self_id}, and your nickname is {nickname}.` 作为首行。
- 让 section 从 `connect()` 完成初始登录同步后缓存的 `self_id` 和 `nickname` 读取身份，
  不在 prompt 渲染期间发起 Milky 网络请求或猜测身份。
- 通过根插件注册边界登记 section，并让同一注册实例创建的 Milky adapter 更新该缓存；不修改
  Hermes core，也不影响其他平台的 prompt 或 hint。
- 补充注册、迁移完整性、动态身份、连接时序、未连接降级和宿主无 section API 时的测试。

## Capabilities

### New Capabilities

- `milky-platform-prompt-guidance`: 定义 Milky platform hint 与动态系统提示 section 的内容、
  身份来源、生命周期和安全降级行为。

### Modified Capabilities

无。现有生命周期规范中的注册与连接门槛保持不变；本 change 新增对平台提示呈现方式的独立
可观察契约。

## Impact

- 影响根入口 `__init__.py`、`MilkyAdapter` 的连接后身份缓存交接，以及入口和生命周期测试。
- 依赖已存在的 Hermes `register_system_prompt_section` 宿主 API；不新增 Python 依赖、不修改
  Hermes core、不增加 Milky Action/SSE 调用。
- system prompt section 受 Hermes 自身的 section ID、渲染和字符预算约束；旧宿主不具备该
  API 时保留首句 platform hint，并安全跳过无法登记的动态 section。
