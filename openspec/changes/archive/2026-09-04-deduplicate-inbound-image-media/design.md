## Context

当前 resolver 会先分别完成 history 和 current 的资源解析。Hermes image helper 返回的本地路径
可能因随机命名而不同；随后 pipeline 用解析后的正文渲染 `channel_context`，mapper 再按
本地 path 合并 `media_urls`。因此不同 `resource_id`、不同路径但相同 bytes 的图片无法被识别
为同一输入，且只修改媒体数组会留下与数组不一致的正文 basename。

本 change 只在插件侧补齐一次 trigger batch 的图片内容去重。Hermes core 的 helper、下载、缓存、
SSRF、权限和生命周期边界保持不变；Milky v1.3 image segment 也不提供可用的 content hash。

## Goals / Non-Goals

**Goals:**

- 在所有资源 helper 完成后，为当前 `ResolvedTriggerBatch` 建立临时的图片内容等价关系。
- 按历史可见图片优先、当前消息随后、原始 occurrence 顺序选择代表。
- 让代表路径、basename、MIME、`media_urls`、`media_types`、历史正文和当前正文保持一致。
- 让 `channel_context` 使用最终改写后的 history，而不是 canonical 的临时 placeholder。
- 在插件读取边界内限制 hash 的文件类型、大小、读取次数和错误降级，并保持敏感信息脱敏。

**Non-Goals:**

- 不修改 Hermes core、Hermes image helper 或 Hermes 的下载/缓存/SSRF 实现。
- 不新增 Milky Action，不使用 `resource_id`、URL、summary、文件名或 `file_hash` 作为 image identity。
- 不建立跨 batch、chat、session 或进程的图片缓存，不改变 wait 阶段的零资源 I/O。
- 不把 file、record、video、forward 或未展示的嵌套 reply 图片纳入历史图片媒体列表。
- 不改变相同图片 occurrence 在正文中的数量、顺序或原有 reply/header 语义。

## Decisions

### 1. 在 batch 完成资源解析后做一次插件侧 finalization

`resolve_batch` 继续先等待 history 和 current 的 Hermes helper，之后才执行图片代表选择。代表
registry 只存在于本次 batch；resolver 的独立单消息调用不得把结果写入长期状态。mapper 只消费
finalization 产出的代表结果，不再自行猜测内容相同。

候选顺序固定为：

1. history 中按上下文顺序出现且实际可见的直接 image occurrence；
2. current 中按消息和可见 reply 内容顺序出现的 image occurrence。

history 嵌套 reply 的 image 即使已经被 helper materialize，也不进入 history 的可见候选集合，
不能抢占代表或提升为本次历史 `media_urls`。当前 reply 只按最终 MessageEvent 会展示的 reply
内容纳入候选；forward 不自动展开，因而没有新增图片候选。

### 2. 只使用受限 SHA-256，失败时保守降级

helper 返回本地字符串后，插件先检查它是否为非空本地路径，再以不跟随符号链接的方式打开并
检查常规文件、非空、大小不超过 8 MiB 和读取过程稳定。通过检查后以固定小块流式更新
SHA-256；不复制文件、不创建目录、不把 bytes 放入事件或日志。相同本地 path 在本 batch 内
只读取一次并复用读取结果。

hash 失败、文件不可读、状态不安全、为空或超过上限时，不把该 occurrence 与任何其他 path
合并；同一路径仍由现有 exact path 防线去重。错误只形成固定安全分类，不记录 path、URL、
异常正文、文件内容或 hash 值。该边界是插件的等价性判断，不替代 Hermes 对 helper 返回路径
和下载资源的安全管理。

### 3. 首次代表决定路径、MIME 和媒体位置

registry 以 SHA-256 为 key；hash 成功的 occurrence 首次出现时登记其完整 materialization，
包括 path、MIME 和 kind。后续相同 digest 的 occurrence 不再产生 `media_urls` 项，也不改变
首次代表 MIME。hash 不可用的 occurrence 使用独立的 path identity，不因协议字段相似而合并。

最终媒体序列由历史可见图片代表和 current 既有 materialization 按既定顺序构成；图片内容代表
替换只影响重复的 image occurrence，current 中原有的非图片 materialization 保持既有行为。
生成 `media_urls` 与 `media_types` 时逐项构造配对，最终数组必须等长。

### 4. 保留 occurrence 与展示面的结构化关联

资源解析结果需要在图片 occurrence、对应 materialization、正文或可见 reply body 之间保留
结构化关联。finalization 根据这个关联把每个可见 occurrence 指向代表 basename，并同步过滤
媒体候选；不得从已经拼接好的任意正文中用 basename、文件名或正则反解析图片 identity。

最终需要覆盖的展示面是 history 的顶层正文、current 的正文，以及 current MessageEvent 实际
使用的 reply 文本。未进入 `channel_context` 或 MessageEvent 的嵌套内容不改变其内部展示，
但不得影响代表选择或媒体列表。

### 5. 在映射前重建上下文，保留既有 pipeline 顺序

pipeline 仍遵循 Gate、Will、drain、资源解析、mapper、`handle_message()` 的顺序。resolver 返回
的 `ResolvedTriggerBatch` 已经包含最终 history/current；pipeline 以该对象重新渲染
`channel_context`，mapper 以同一对象构造 current `text` 和媒体数组。不得从 canonical 临时正文
或原始 `channel_context` 再次生成上下文，也不得为 hash 增加等待 Agent turn 的行为。

### 6. 只在插件中增加最小可测试边界

实现可通过 batch finalization 的内部 registry、materialization 的可选摘要状态或等价的
occurrence 结果表达，但不得暴露新的 Milky 协议字段或依赖 Hermes 未确认的 API。所有测试使用
脱敏临时文件和合成 helper 路径；不得把真实媒体、token、完整路径或远端 URL 写入 fixture、
日志或 snapshot。

## Risks / Trade-offs

- [同一图片在 batch 内被读取多次] → 按本地 path 缓存一次 hash 结果，并以 occurrence 关联避免
  重复打开同一 materialization。
- [文件在 helper 返回后发生 TOCTOU 变化] → 以已打开文件的 descriptor 做状态和单次流式读取，
  读取前后校验稳定性；异常时放弃 hash，回退 exact path，不宣称相等。
- [8 MiB 上限导致大图无法内容去重] → 保留各自有效 materialization 和 basename，只牺牲本次
  batch 的内容合并，不改变 Hermes 原有媒体交付。
- [同一 bytes 的图片 MIME 不同] → 首次代表的 MIME 随代表路径保留，避免产生第二个媒体项；该
  取舍由“首次出现优先”决定并用测试固定。
- [hash 失败图片与可 hash 图片实际相同] → 不作跨状态猜测；失败项仅按 path 去重，确保未知
  状态不会导致媒体误删。
- [正文和媒体代表更新不一致] → finalization 一次性更新 occurrence 展示和 materialization
  集合，pipeline 只消费 finalization 结果，并增加 `channel_context` 与数组配对测试。
- [改动误触 wait 阶段] → hash 入口只挂在 trigger batch 的 resolver 完成路径；normalizer、
  canonical、buffer 和 Will 测试继续断言没有文件读取或资源 I/O。

## Migration Plan

该 change 不改变协议、持久化格式、配置或 Hermes core。发布插件版本后，新 trigger batch 使用
内容代表选择；helper 或 hash 不可用时自动沿用现有安全降级和 exact path 去重。若需回滚，只需
恢复插件版本；不会留下插件侧图片缓存或需要迁移的数据，回滚后的唯一影响是相同 bytes 可能
再次作为多个媒体项交给 Hermes。

实现完成后，在归档前必须用脱敏 fixture 验证 OpenSpec 场景、聚焦资源/pipeline 测试、fake
Hermes 集成、Ruff/format、`git diff --check`、构建和严格 OpenSpec 校验；真实 Hermes host
能力仍以受控 smoke 或实机证据为准，不能由 fake helper 单独宣称。
