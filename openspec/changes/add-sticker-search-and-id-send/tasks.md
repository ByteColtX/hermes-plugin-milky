# Tasks

## 1. 工具契约与发现

- [x] 1.1 新增 sticker_search 定义和 manifest 登记，扩展 sticker_send 的互斥 ID 参数；用 schema/handler 参数化测试验证空输入、null、bool、limit 默认和上下界、ID 格式、混合模式、未知字段在存储和网络访问前失败，并保留原查询调用兼容性。
- [x] 1.2 接入既有活动贴纸服务与只读可用性检查；用注册和生命周期测试验证空库隐藏两工具、不创建存储、不在注册联网，以及上下文缺失、非 Milky、temp、解绑后均安全失败。
- [x] 1.3 将两个工具描述限定为设计中的一句能力说明，参数说明仅保留必要约束；审阅实际 definitions 并验证平台提示未改变，不新增聊天时机、频率、SILENT、SOUL 或记忆内容。

## 2. 只读搜索

- [x] 2.1 复用查询模式的候选与词法证据，实现跨匹配层级排序、并列 ID 稳定排序及 limit 截取；用合成候选测试完整短语/全部 token/部分 token、情绪硬筛选、标签 OR/跨字段 AND、稳定排序、无重复及 no_match。
- [x] 2.2 实现仅含 status/items 和限定元数据的搜索结果；测试默认 5、最大 10、字段白名单、长度异常候选、人工清空字段、失效索引与缺失文件过滤，并验证没有媒体 bytes、路径、URL、hash、统计或匹配解释输出。
- [x] 2.3 实现只读搜索的存储与错误边界；用只读兼容库、缺失库、不兼容库和故障注入验证 unsupported/storage_error/no_match 区分，无目录创建、迁移、修复、视觉分析、发送或使用统计变更，连续搜索不改变发送轮换状态。

## 3. 精确发送

- [x] 3.1 增加按既有 opaque ID 精确选择的路径，绕过匹配及轮换但复用既有发送校验；以另一条目相关性更高、目标贴纸刚使用过、重启后 ID 仍有效的 fixture 验证只发送指定图片，且无需搜索缓存。
- [x] 3.2 明确 ID 不存在/不可见、文件缺失、索引损坏及完整性错误的分类；用搜索后删除、替换、缺失文件和损坏关联测试 not_found/missing_file/storage_error，验证失败无发送、无计数、无静默换图。
- [x] 3.3 验证查询与 ID 两模式复用当前会话目标、大小限制和一次读取/一次 Action 边界；用私聊、群聊、非法上下文、远端 rejected/http_error/malformed/transport_unknown 和统计写入失败的 fixture 证明不回退目标、不重试、claim 计数保持既有语义。
- [x] 3.4 保持发送回执 status/message_id 和安全日志边界，只增加 ID 模式 not_found；用工具级测试验证精确发送成功不暴露内部元数据，日志不包含完整 ID 入参对象、查询、描述、标签、路径或原始结果。

## 4. 文档与集成验证

- [x] 4.1 同步 README、ARCHITECTURE 与 QQ tools bundled skill 的实际接口、只读搜索和错误分类；全文核对“无搜索”“拒绝 sticker_id”等过期陈述，保留简短能力描述，并在 evidence 中记录与未实施 library change 的参数、作用域和统计冲突，不擅自修改其范围。
- [x] 4.2 运行 uv run pytest -q tests/test_sticker_send.py tests/test_sticker_maintenance.py tests/test_qq_tools.py tests/test_plugin_entry.py tests/test_outbound.py，并纳入新增搜索测试；再运行 uv run ruff check .、uv run ruff format --check .、git diff --check、openspec validate --changes --strict，记录命令、结果与失败原因。
- [ ] 4.3 在可用真实 Hermes 环境以合成库验证两工具发现、搜索结果交付、ID 参数调用和新会话定义；证据明确区分真实宿主与 fake host，缺环境则记录 blocked/未验证，不将 skip 当作通过。
- [ ] 4.4 在获得明确目标授权后进行真实 Milky 单次 ID 发送与原查询发送验证，记录限定的分类证据；未获授权或环境不可用则保留未完成并标注阻塞，不将本地 fixture 成功写成真实发送成功。
