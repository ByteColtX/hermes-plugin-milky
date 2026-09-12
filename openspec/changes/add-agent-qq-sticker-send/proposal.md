## Why

贴纸维护库已经能够保存经过校验的 QQ 贴纸及其当前生效元数据，但 Agent 仍不能根据当前对话意图安全地选取并发送贴纸，维护库尚未形成发送闭环。现在需要增加一个不接受 Agent 指定贴纸 ID 或会话目标的 Agent 工具，让插件在可信当前会话中完成本地检索、文件校验和一次贴纸发送。

## What Changes

- 新增唯一的 Agent Tool `sticker_send`；`intent`、`emotion`、`tags` 均为可选参数，但至少需要一个非空参数。
- Tool 不接受 `sticker_id`、`emoji_id`、`face_id`、`chat_id`、`session_id`、任意文件路径或远端媒体 URL；发送目标只从可信的 task-local Milky session context 获取。成功回执可以返回被选中的不透明 `sticker_id`，但 Agent 不能指定它。
- 只读取贴纸库当前生效的 `emotion`、`tags`、`description` 字段；字段是人工修正还是视觉生成不改变匹配优先级。
- 使用可选的本地中文分词依赖和无数值阈值的分层词法证据检索，对意图和贴纸元数据进行相关性排序；贴纸库为空时不要求该依赖，也不向 Agent 暴露 `sticker_send`。不新增独立的 `sticker_search`，不调用远程搜索或模型进行发送时匹配。
- `emotion` 在提供时作为严格筛选条件；语义相关性优先于曝光轮换，相关性接近的候选才使用当前会话的使用记录进行软轮换，不因最近发送而硬排除明显更匹配的贴纸。
- 发送前校验库文件、受控路径和 SHA-256；只发送一张 `image` sticker segment。选定贴纸的本地校验失败时返回固定错误，不静默改发另一张。
- 每次 Tool 调用最多向 Milky 发起一次消息 Action，但不限制 Agent 在不同调用中重复调用 Tool；远端结果未知时不自动重试。
- 贴纸发送 Action 进入发送边界时原子更新现有全局使用统计，并记录当前会话的选择历史；Milky 成功、失败或未知均不回滚已接受的统计更新。
- 返回固定的成功、无匹配、缺少会话上下文、存储失败和远端失败分类；成功结果可包含选定的 `sticker_id` 和 `message_id`。
- 明确不新增 `sticker_search`、Agent 贴纸收藏/删除能力、入站图片自动入库、任意文件发送和跨会话目标选择。

## Capabilities

### New Capabilities

- `qq-sticker-send`: 定义 Agent 贴纸发送工具的参数、可信目标、当前元数据检索、相关性优先选择、会话级曝光轮换、文件校验、Milky 发送和错误语义。

### Modified Capabilities

<!-- 现有 qq-sticker-maintenance 已预留发送时使用统计的语义；本 change 通过新 capability 实现该发送入口，不改变维护命令的行为。 -->

## Impact

- 影响 `outbound/tools.py`、贴纸 store/发送服务、`outbound/sender.py` 或其专用 sticker 发送路径、插件 manifest 以及相关测试 fixture。
- 需要使用插件已有的 `stickers.db`、`sticker_items`、`sticker_files` 和 content-addressed library；可能增加受控的当前会话使用历史持久化。
- 需要将中文分词依赖声明为可选 extra 并锁定版本；基础安装不得依赖它。贴纸库为空时不得导入或要求该依赖；库非空但可选依赖不可用时，`sticker_send` 不进入 Agent 可见 Tool definitions，且不影响其他 Tool 和贴纸维护命令。不得假设 Hermes 宿主已经安装该依赖。
- 需要补充 Agent Tool schema、task-local context 校验、中文分层词法检索/部分命中测试、并列候选轮换测试、文件/hash 失败测试、Milky 成功/失败/未知结果测试和 fake Hermes/Milky 集成测试。
- 不修改 Hermes core，不新增 Milky 协议 Action，不改变普通消息、Will、Gate、wait buffer 或入站媒体所有权边界。
