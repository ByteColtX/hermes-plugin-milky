## 1. 依赖、schema 和贴纸检索基础

- [x] 1.1 按 Hermes plugin manifest 依赖约定和项目运行时依赖声明提供 `Pillow>=12.3.0`、`jieba>=0.42.1`；不使用 optional extra 或按需导入，并验证 Python 3.13 下依赖导入、Unicode 归一化和同一输入的稳定分词结果
- [x] 1.2 将贴纸数据库 schema 从当前版本迁移到发送版本，增加按 `(chat_key, sticker_id)` 保存最近使用时间和计数的受控表及索引；用旧库迁移、未知 schema、回滚和重载测试验证不覆盖既有 `sticker_items`、library 或全局统计
- [x] 1.3 实现只读取当前生效 `emotion`、`tags`、`description` 和有效 `sticker_files` 关联的本地候选读取边界；用人工字段修改、缺失索引、孤儿文件和不可见条目 fixture 验证 source 不改变匹配输入且不读取路径外文件
- [x] 1.4 实现统一的文本归一化、`jieba` 分词和无数值分数的固定相关性层级：完整短语命中、全部 token 命中、部分 token 命中；用合成 query/library fixture 验证无远程调用、部分命中可召回、零证据返回 `no_match`、唯一有证据候选不因阈值被拒绝，且内部层级不出现在 Tool 回执中

## 2. Tool 契约、上下文和生命周期

- [x] 2.1 在 `outbound/tools.py` 和 manifest 中注册独立 `sticker_send` ToolSpec 及只读可用性检查：空库或无可用条目时不进入 Agent definitions，正常运行时依赖由 manifest 和项目依赖提供且不按需导入；二者均不影响其他 Tool 和维护命令；保持既有 Milky operationId 工具不变，并验证就绪时只暴露 `intent`、`emotion`、`tags`，没有 `sticker_search` 或任意 Action catalog
- [x] 2.2 实现参数校验和可信 session context 校验：至少一个非空查询参数、固定 emotion 枚举、intent 长度上限、1–5 个去重 tags 及单 tag 长度上限、`HERMES_SESSION_PLATFORM=milky`、合法 `dm:/group:` chat key；用缺失/冲突/非 Milky/temp context、额外字段、路径、URL、`sticker_id`、`emoji_id`、`face_id` 和 `session_id` fixture 验证网络和文件访问均未发生
- [x] 2.3 将 Tool handler、发送 service 和 store 生命周期绑定到当前活动 sender；用 register、connect、SSE、普通 Agent 输出、Tool discovery、disconnect/reload 测试验证正常运行时依赖由宿主依赖环境提供、注册/import/connect 阶段不创建数据库，空库可用性检查不打开 store，且不建立后台检索任务；未连接或过期 definition 调用时安全失败

## 3. 相关性优先和候选选择

- [x] 3.1 实现 emotion 严格筛选、tags 至少一个精确命中且多个 tags 为 OR、intent 短语/全部 token/部分 token 的固定层级以及多参数 AND 语义；用单参数、全参数、部分命中、零证据、人工/视觉 source、情绪不匹配、空库和唯一有证据候选测试验证 `no_match` 与不使用数值阈值
- [x] 3.2 实现“语义相关性优先、完全并列候选才软轮换”的选择器：明显更优候选不得被最近使用记录压过，并列池内允许随机并偏向较久未用但不得硬 cooldown；用最近发送的最佳候选、完全并列候选、池外较差候选和唯一合格候选 fixture 验证选择不变量
- [x] 3.3 实现选择 claim、全局 `use_count`/`last_used_at` 和 per-chat 使用记录的短事务更新；用并发调用、同一次 invocation 去重、统计 claim 失败不触网、Milky 成功/拒绝/失败/未知测试验证一次调用只计一次、统计不因远端失败回滚且不因补写统计重发

## 4. 受控文件读取和 Milky 发送

- [x] 4.1 实现选定 library 文件的 containment、regular-file、格式/大小、双索引 SHA-256 校验和一次性 materialization 边界；用缺失、越界、hash 不一致、格式错误、文件替换和成功图片 fixture 验证失败不触网且不静默换图
- [x] 4.2 增加专用 sticker 发送路径，构造单一 `image` segment 且 `sub_type="sticker"`，按 `dm:`/`group:` 选择对应 Milky Action；用私聊、群聊、segment 精确 body、无 caption、无文本拆分和一次 Action 断言验证出站协议
- [x] 4.3 统一转换成功、rejected、HTTP 错误、malformed、timeout 和 transport unknown；用真实形状的 fake Milky envelope 验证成功只返回 `message_id`、不暴露内部 `sticker_id`，未知结果不重试、不文本 fallback、不追加第二个发送 Action

## 5. 集成、文档和质量门禁

- [x] 5.1 补充 fake Hermes/Milky 集成 fixture，覆盖实际 Agent Tool definitions 发现（空库隐藏、就绪时出现）、task-local target、维护库读取、分层词法匹配、并列软轮换、文件/hash 校验、统计 claim、重复显式调用、普通消息隔离和真实发送调用次数；运行贴纸、工具、出站和未知结果聚焦测试
- [x] 5.2 更新 `ARCHITECTURE.md`、`README.md`、`plugin.yaml` 及相关主规范，记录 `sticker_send` 参数/目标边界、`Pillow>=12.3.0`/`jieba>=0.42.1` 运行时依赖、无按需 tokenizer 和空库隐藏规则、无分数分层词法检索、无 `sticker_search`、语义优先轮换、统计和错误分类；用文档搜索验证没有写入 Agent 传入会话 ID、任意路径或 turn 调用上限
- [x] 5.3 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`；按契约、实现、fake host 或环境问题分类失败并记录 evidence

## Evidence ledger

- `uv run pytest -q -rs`: 951 passed, 3 skipped；3 个 skip 分别是 Hermes host unavailable、显式开启 `RUN_HERMES_INTEGRATION=1` 的真实 Hermes 集成，以及当前环境缺少 Hermes host；覆盖本地 fake Hermes、fake Milky、SQLite、Tool discovery、生命周期和出站协议，未证明真实生产 Hermes/Milky 已部署支持该能力。
- `uv run pytest -q tests/test_sticker_send.py tests/test_sticker_maintenance.py tests/test_qq_tools.py tests/test_outbound.py`: 177 passed；贴纸发送、维护、ToolSpec 和出站边界聚焦回归通过。
- `uv lock`：已将 `jieba>=0.42.1` 和 `pillow>=12.3.0` 写入项目正式运行时依赖；未保留 `sticker-send` optional extra。
- `uv run ruff check .`: 通过。
- `uv run ruff format --check .`: 通过。
- `uv build`: 通过，生成的构建产物未纳入提交范围。
- `git diff --check`: 通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`: 5 changes passed, 0 failed。
- 未执行真实 Milky 发送或上传 smoke；该操作需要用户明确授权和命中运行时 `MILKY_ALLOWED_CHATS`，本 change 仅使用脱敏 fake transport 验证一次 Action、错误分类和不重试边界。
