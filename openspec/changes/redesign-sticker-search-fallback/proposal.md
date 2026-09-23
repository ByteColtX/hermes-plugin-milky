# Proposal

## Why

Milky 插件要让 Agent 能自然参与普通群聊，由 Agent 根据上下文判断贴纸是否有帮助，不要求用户先明确提出“发贴纸”。当前严格发送无匹配后再用相同条件搜索会重复落空；本 change 明确区分严格搜索、显式放宽搜索和浏览，并让发送无匹配回执直接提供有限备选或安全结束。

## What Changes

- **BREAKING** 为 `sticker_search` 增加明确的 `mode`：严格搜索无匹配时返回空结果，不暗中兜底；`fallback` 明确忽略 `intent`、保留显式情绪和标签条件；`browse` 用于无查询浏览。
- **BREAKING** `sticker_send` 严格查询无匹配时返回最多 5 个当前可用备选；备选只供 Agent 判断，不表示匹配，也不会发送消息或更新统计。
- 保留 `sticker_send(sticker_id)` 的精确发送、当前会话目标、文件校验、统计 claim 和单次 Action 边界。Agent 必须明确选择 ID 才能发送；不合适时可不发贴纸并继续普通对话。
- 过期 ID 或本地文件失效时，Agent 可重新搜索一次并重新判断；发送 Action 的 HTTP、malformed 或 transport unknown 等结果不确定时不得盲目重试或换图。
- 同步 ToolSpec、README、ARCHITECTURE、bundled skill、测试和 evidence，验证自然群聊决策、各搜索模式、无匹配备选、只读边界和安全终态。
- 不引入新的 Milky operationId、远程搜索、图片预览、embedding、自动发送、自动换图、任意目标或路径参数。

## Capabilities

### New Capabilities

- `qq-sticker-search`: 定义当前贴纸候选的只读严格搜索、显式 fallback、浏览模式和空库错误边界；该能力承接未归档 `add-sticker-search-and-id-send` 中已有的搜索工具。

### Modified Capabilities

- `qq-sticker-send`: 规定严格查询无匹配时可返回有限备选，但只允许 Agent 后续显式选择 ID；精确 ID 发送和既有副作用边界保持不变。

## Impact

- 影响 `outbound/tools.py`、`stickers/` 中的搜索模式校验、候选筛选和结果封装，以及对应的单元、工具注册和生命周期测试；`sticker_send` 的 `no_match` 回执必须保留备选字段。
- 影响 `README.md`、`ARCHITECTURE.md`、QQ bundled skill 和 OpenSpec evidence；需要同步自然群聊使用方式、严格/放宽/浏览模式、备选和不重试说明。
- 不增加运行时依赖，不改变 SQLite schema、贴纸文件、发送统计或 Milky 协议 Action；实现阶段应保持搜索只读和当前可见条目边界。
- 当前代码已有严格搜索和 ID 发送实现，但真实 Hermes 工具发现与真实 Milky 写入仍未验证；本 change 的验收必须区分 fixture/fake host 证据与真实环境证据。
