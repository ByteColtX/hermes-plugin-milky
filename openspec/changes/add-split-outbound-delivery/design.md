## Context

See `proposal.md` and the four delta specs for the requested behavior. 当前普通出站文本先进入
Milky 的统一 formatter，再按既有长度边界形成发送单元；Hermes 的 `MEDIA:` 提取和附件派发
位于插件普通文本交接之外，现行边界是先完成文本投递，再逐项调用媒体或文件入口。根入口的
`PLATFORM_GUIDANCE` 通过 Milky system prompt section 提供给 Agent，`[SILENT]` 的语义属于
Hermes core。

本 change 只扩展插件管理的文本投递边界。它不改变 Hermes core 的回复解析、`MEDIA:` 提取、
媒体路径安全策略、附件派发顺序、Milky Action、ToolSpec、Gate/Will 或出站目标路由。

## Goals / Non-Goals

**Goals:**

- 在进入 CQ-compatible formatter 和 Milky Action 前识别严格的独立 `[SPLIT]` 行。
- 保留有效分段的可见内容和顺序，并在所有网络调用前确定最多三条文本消息是否可满足。
- 让文本、图片、语音、视频和文档附件的当前先文本后附件顺序成为可测试且对 Agent 明确的契约。
- 让 `PLATFORM_GUIDANCE` 同时说明 `[SPLIT]`、当前媒体顺序和由 Hermes core 处理的 `[SILENT]`。

**Non-Goals:**

- 不在 Milky plugin 中解析、删除或拦截 `[SILENT]`；不复制 Hermes core 的 silent 处理。
- 不把 `MEDIA:` 解析为 plugin 内部的有序事件，也不根据原始回复中的标签位置猜测附件顺序。
- 不支持文本段和附件交错、不保证包含附件的整次 Agent 回复总共只有三条 QQ 消息；三条上限只约束 plugin 管理的文本消息。
- 不改变未包含有效 `[SPLIT]` 的普通长文本既有多条分块行为。

## Decisions

### 1. 在普通文本 formatter 前增加独立分段解析

把 `[SPLIT]` 作为出站文本控制语法，而不是 CQ-compatible 片段。解析器按 LF/CRLF 行边界
检查整行，只有字节级内容恰好为 `[SPLIT]` 的行才命中；不做大小写折叠、空白 trim 或
包含匹配。这样 `[SPLIT]` 作为自然文本的一部分时不会意外触发控制流，且解析职责与
CQ formatter 保持分离。

命中后移除标记行及其行结束符，并以相邻文本构成逻辑段。只含空白的逻辑段被丢弃；非空段
不做全局 trim，避免改变 Agent 有意保留的文本空白。所有剩余段随后仍经过既有 CQ 解析、
媒体 materialization 和长度检查。

备选方案是先调用现有 `format_message()` 再在 text segment 中寻找标记，但该方案会让控制
语法依赖 CQ segment 合并方式，无法可靠保留行边界，也容易把标记混入 formatter fallback，
因此不采用。另一个备选方案是让 Hermes core 统一解析，该方案会扩大跨仓库变更并违反本插件
只在自身出站边界完成 Milky 语法识别的范围。

### 2. 先形成逻辑段，再进行长度分块和总数预检

只有回复中出现有效 `[SPLIT]` 行时才进入三条上限路径。先过滤空段；若剩余段超过三个，
保留前两段，把第三段及其后的内容按原顺序合并为第三段，并在合并边界保留单个换行分隔。
然后逐个逻辑段执行既有 `chunk_text` 规则。实现必须在任何发送 Action 前完成全部逻辑段、
格式化和长度分块，若最终物理文本单元超过三条则返回本地边界错误，避免已发前序消息后才
发现无法满足上限。

选择“合并后再按长度分块”而不是简单丢弃第四段，是为了同时满足三条上限和内容不丢失；
选择整体拒绝而不是截断，是为了不让用户收到缺少尾部的半个回复。未出现有效标记时，继续
使用既有普通长文本分块，不引入全局三条限制。

### 3. 文本 Action 串行提交，失败保留部分结果

预检通过后，文本单元按顺序逐个提交到已解析的 `group:` 或 `dm:` 目标；不并发提交，避免
远端显示顺序与回复顺序分离。中途 Action 失败时保留已有成功消息 ID、失败位置和首个安全
分类，不自动重试可能已经产生副作用的请求，也不发送纯文本 fallback。该行为沿用现有
SendResult 和 unknown-outcome 边界，仅增加 split 批次的预检。

### 4. 保持 Hermes 媒体交接的文本先行顺序

插件不接管 `MEDIA:`。在当前 Hermes 交接中，清理后的回复文本先进入 adapter；Hermes 随后
按提取顺序把附件交给 `send_image_file`、`send_voice`、`send_video` 或 `send_document`。
因此一条回复中的可观察顺序固定为：文本分段 1、文本分段 2、文本分段 3（如有），再到
附件 1、附件 2（如有）。附件依然分别使用 native message segment 或独立 file upload，
不消耗文本三条上限，也不能因 `MEDIA:` 在原始正文中的位置而插入文本中间。

交错投递需要 Hermes 同时提供带顺序的文本/附件事件流或等价的逐事件回调；当前 plugin
接口只收到清理后的文本或独立附件调用，因此本 change 明确返回/保持 unsupported 边界，
不在插件内伪造交错。

### 5. 仅更新 Agent-facing 文案，不新增 `[SILENT]` 插件逻辑

`PLATFORM_GUIDANCE` 增加严格格式、三条上限、空段和媒体顺序说明，并把旧 `NO_REPLY` 文案
改为 `[SILENT]`。文案明确 `[SILENT]` 由 Hermes core 处理；Milky sender 不搜索该标记、
不删除它、不据此调用 Action。这样标记风格可以统一，同时不会复制 core 的控制流。

## Risks / Trade-offs

- [三条上限与既有长度上限冲突] → 在首个网络 Action 前完成总数预检，超过上限整体拒绝并保留安全分类，不部分发送。
- [多余分段的合并改变视觉分隔] → 仅在第三段之后合并，并保留一个换行作为段边界；所有原始可见文本仍按顺序保留。
- [当前 Hermes 继续把附件放在文本之后] → 在规范、PLATFORM_GUIDANCE 和 fake 交接测试中明确顺序；真正交错列为需要 Hermes core 有序接口的后续变更。
- [模型误写相似标记] → 解析不 trim、不忽略大小写、不做 substring 匹配；相似内容按普通文本发送。
- [附件独立 Action 失败] → 沿用既有 partial result、安全错误分类和不重试边界；不伪造文本/附件整体成功。
- [旧 Hermes 宿主不理解新指引] → `[SILENT]` 仍由 core 处理，Milky plugin 只负责静态提示文案；真实宿主兼容性通过受控集成验证，不以 fake host 结果替代。

## Migration Plan

1. 先新增脱敏 fixture 和 parser/sender 契约测试，覆盖独立行、大小写、空段、三条上限、长度预检和部分失败。
2. 在 formatter 前接入 split 逻辑，并保持无有效标记的普通文本和现有媒体入口回归通过。
3. 更新根入口的 `PLATFORM_GUIDANCE`、system prompt delta、`ARCHITECTURE.md` 与 `README.md`，说明文本先于附件和不支持交错。
4. 运行聚焦测试、fake Hermes/Milky 顺序测试、完整 pytest、Ruff、format、build、diff 检查和严格 OpenSpec 校验；真实 Milky smoke 只在明确授权写入时执行。
5. 回滚时移除 split 解析和文案扩展即可；不涉及配置迁移、Milky 远端数据或 Hermes core 回滚。

## Open Questions

无。三条上限的适用范围、超过三段的合并策略以及媒体先后顺序已在 delta spec 中固定；交错投递只有在 Hermes core 提供有序交接接口后再单独立项。
