# Design

## Context

当前实现已有两个独立的本地语义工具：`sticker_send` 负责按查询或 opaque ID 选择并发送一张贴纸，`sticker_search` 负责只读返回候选。当前两者的查询匹配条件相同，因此发送无匹配后再执行同条件搜索无法产生新信息；原方案也没有清晰定义全库兜底候选与原意的关系。

本 change 调整搜索模式和发送无匹配回执的可观察契约。Milky 目标仍来自 task-local session context，贴纸库仍由插件拥有，搜索仍然只读；发送的文件校验、统计 claim、单次 Action、ID 精确解析和未知结果不重试语义继续以主 `qq-sticker-send` 规范和实现为准。当前真实 Hermes 工具发现和真实 Milky 写入尚未验证，规划不能把 fixture 或 fake host 结果写成真实集成成功。

## Goals / Non-Goals

**Goals:**

- 让 Agent 在普通群聊中自主判断贴纸是否有帮助，不把工具使用限定为响应用户的显式请求。
- 让搜索模式可辨识：严格搜索不自动兜底，fallback 明确放宽 intent 并保留显式 emotion/tags，browse 明确表示浏览。
- 让严格发送无匹配时直接返回有界备选，避免 Agent 重复相同查询；备选由 Agent 判断，发送仍需显式 ID。
- 保持当前可见文件边界、元数据白名单、稳定排序和无副作用搜索。
- 不改变既有 ID 发送路径，使 Agent 可以在审阅兜底候选后显式发送指定 ID。

**Non-Goals:**

- 不让发送工具自动采用兜底候选，不静默换图，也不增加第二个 Milky Action。
- 不引入远程搜索、embedding、视觉理解、同义词模型、图片预览、分页会话或搜索缓存。
- 不读取或更新发送统计来排序兜底候选，不改变数据库 schema、贴纸作用域或人工维护命令。
- 不接受目标、路径、URL、任意文件或新的 operationId，不修改 Hermes core、平台提示、SOUL 或记忆。

## Decisions

### 1. 让搜索模式显式，而不是遇到零命中就静默兜底

请求未指定模式时，有查询字段默认 `strict`，无查询字段默认 `browse`。`strict` 沿用现有匹配规则；零命中返回空结果，不隐式扩大范围。`fallback` 必须由调用方显式选择，并要求同时提供 intent 与 emotion 或 tags；候选匹配时忽略 intent，但保留 emotion 精确条件和 tags OR 条件。`browse` 不接收查询条件，只按稳定 ID 顺序列出有界当前可用条目。

三种模式都只从当前可见、索引有效且文件可用的条目中选取。结果通过 `match_mode` 标明 `strict`、`fallback` 或 `browse`；strict 零命中不自动变成 fallback，fallback 也不把候选说成满足原 intent。fallback 按匹配请求 tag 数量降序、再按 opaque ID 排序；browse 按 opaque ID 排序。每种模式都由 `limit` 限制数量。

### 2. 在发送无匹配回执中提供同一规则的备选

当 `sticker_send` 严格查询无匹配，且输入同时包含 intent 与 emotion 或 tags 时，回执直接附带最多 5 个 fallback 候选；筛选规则与 `sticker_search(mode=fallback)` 一致。只有 intent 的查询没有可保留的硬条件，回执返回空备选，避免把任意库样本伪装成相关结果。候选只供 Agent 审阅；它不代表已匹配、已授权或已发送。

搜索结果只包含 `status`、`match_mode` 和 `items`；每个 item 只含 `sticker_id`、`emotion`、`tags` 和 `description`。发送 `no_match` 可多一个有界 `alternatives` 字段，但仍不返回路径、URL、hash、图片内容、统计或匹配解释。结果序列化器不得丢弃这份备选字段。

### 3. Agent 负责选择或安全结束，不建立工具重试循环

Agent 在普通群聊中可自主决定是否调用工具。查询发送严格命中时按既有规则最多发送一张；无匹配时 Agent 可从回执备选中显式选择 ID，也可放弃贴纸继续普通对话。若没有备选但仍认为有用，只有在能从聊天上下文明确给出 emotion 或 tags 时才可调用 fallback 搜索一次；否则可显式 browse 一次，再决定发送或结束。不得重复相同 strict 查询。

ID 模式仍只解析 Agent 显式给出的 opaque ID，发送前重新验证当前条目、文件和目标。若 ID 过期或本地文件失效，Agent 可重新搜索一次并重新判断；不得自动替换下一张。若发送 Action 返回 `http_error`、`malformed` 或 `transport_unknown`，由于副作用可能已经发生，Agent 不得再次发送或换图，可改为普通文本结束。

### 4. 保持搜索的只读和资源所有权

搜索继续在调用范围内打开现有库的只读视图，过滤当前可见且文件索引和文件可用的条目；不创建、迁移、修复或写入库，不读取完整媒体，不调用远端服务，不改变全局或 chat 使用历史。当前 session context 只用于可信会话校验，不改变库的共享可见范围。

工具注册和 definitions discovery 继续使用现有无副作用可用性探测。旧 definition 在搜索服务解绑、上下文非法或库不可用时 fail closed；插件不创建旁路连接或后台检索任务。

### 5. 兼容性和替代方案

这是搜索请求与结果的可观察 breaking change：调用方可显式指定模式，并需读取 `match_mode`；旧调用方必须更新 Tool schema 和 Agent 使用说明。`sticker_send` 的 `no_match` 新增有界备选字段；不需要数据迁移。

考虑过让 strict 搜索零命中时自动返回全库候选，但这种隐式扩张使相同查询总能拿到不相关样本，也容易被误解为匹配；因此 fallback 必须显式选择并保留情绪/标签条件。也考虑过发送无匹配时直接从备选中自动发送，但这会把低相关性素材变成不可逆副作用；因此只由 Agent 明确选择 ID。Agent 没找到合适贴纸时以普通文本继续对话就是成功终态，不要求工具链最终一定发送图片。

## Risks / Trade-offs

- **fallback 候选仍可能与原 intent 不完全一致** → 只忽略 intent 并保留显式 emotion/tags，结果标记 `match_mode=fallback`，限制数量并要求显式 ID；工具不自动发送。
- **只有 intent 的无匹配请求没有可靠的约束来挑选备选** → 返回空备选；Agent 可显式浏览一次或放弃发送，不伪称任意样本相关。
- **旧 definition 仍按旧结果解释** → 更新工具 schema、bundled skill 和文档；真实宿主验证工具重新发现，过期调用继续返回固定错误而不猜测。
- **搜索结果到发送之间条目可能变化** → ID 发送沿用发送前可见性、文件和完整性复核；失效时可重新搜索一次供 Agent 再判断，不自动换图。
- **搜索结果字段仍可能包含外部文本** → 保持既有长度和字段白名单，把元数据作为不可信数据交付，不执行描述内容，也不记录完整结果。

## Migration Plan

1. 更新搜索参数校验和结果封装，加入严格、显式 fallback 和 browse 模式；让 `sticker_send(no_match)` 附带有限备选并由结果序列化器保留。
2. 增加合成库测试，覆盖各模式命中/无命中、fallback 硬条件、空库浏览、稳定排序、备选回执、失效文件过滤、只读统计和错误边界。
3. 同步 README、ARCHITECTURE、bundled skill、OpenSpec evidence 和工具定义快照，说明 Agent 可自然决定是否发贴纸、不得重复相同 strict 查询、不确定发送结果不重试。
4. 运行聚焦测试、完整质量门禁和 `openspec validate --changes --strict`；把 fake host/fixture 结果与真实 Hermes/Milky 验证分开记录，缺少真实环境时标为 blocked/未验证。
5. 回滚时恢复旧搜索和发送回执契约即可；不删除数据库、文件、使用统计或 opaque ID，无数据迁移。
