## 1. 资源结果与受限摘要边界

- [x] 1.1 为图片 materialization 保留 occurrence 与展示面之间的结构化关联，并让 batch finalization 能返回代表路径、basename、MIME 和保留/合并结果；用资源解析单元测试验证 history/current 的顺序和 reply 展示面的关联
- [x] 1.2 实现只针对 Hermes helper 已成功返回路径的受限流式 SHA-256 读取：非空常规文件、非跟随符号链接、大小不超过 8 MiB、读取失败安全降级且同一 path 在 batch 内最多读取一次；用空文件、超限文件、目录、符号链接、不可读/读取变化和 hash 异常 fixture 验证
- [x] 1.3 保留 hash 失败时的 exact path fallback，并确保等价判断不读取或记录 URL、完整路径、文件内容、异常正文、summary、resource_id 或文件名；用安全诊断断言和敏感值不出现在结果/日志的测试验证

## 2. Batch 图片代表选择与正文改写

- [x] 2.1 在 trigger batch 资源解析完成后按“可见历史直接图片 → 当前消息及可见 reply 图片”的顺序建立临时内容 registry；用不同 resource_id、不同随机路径和相同 bytes 的 history/current fixture 验证首次 occurrence 优先且不跨 batch 复用
- [x] 2.2 将内容重复的可见 image occurrence 改写为首次代表 basename，并同步处理当前正文、历史正文和当前实际使用的 reply 文本；用重复图片、不同图片、MIME 不同和重复 marker 场景验证 occurrence 数量/顺序不变且 placeholder 一致
- [x] 2.3 排除未展示的历史嵌套 reply 图片、forward 展开内容和非图片附件的代表竞争及历史媒体提升；用嵌套 reply fixture 验证其既不抢占代表也不进入历史 `media_urls`
- [x] 2.4 在代表选择后同步更新历史可见图片集合和当前 materialization 集合，保留 current 非图片附件既有行为；用 resolver 结果测试验证重复代表只保留一次、失败图片仍使用固定失败 placeholder

## 3. Hermes MessageEvent 映射与 pipeline 交接

- [x] 3.1 让 pipeline 仅使用 finalization 后的 resolved history/current 重建 `channel_context` 和当前正文，禁止回读 canonical 临时正文或从文本反解析路径；用 fake Hermes 集成测试验证历史和当前 placeholder 与媒体代表一致
- [x] 3.2 更新 MessageEvent 媒体合并逻辑，使 `media_urls`/`media_types` 只输出最终代表并逐项配对，同时保留 exact path 作为最后防线；用历史优先、当前重复、hash 失败和 MIME 配对测试验证数组等长、顺序一致且不含远端引用
- [x] 3.3 保持既有 pipeline 顺序、Gate/Will 语义、Agent turn 解耦和 wait 零资源 I/O；用 wait、Gate deny、重复 canonical、`handle_message()` 提交及并发 chat 回归测试验证 hash 逻辑不会提前执行或等待 Agent

## 4. 回归与质量门禁

- [x] 4.1 补齐资源 resolver、mapper、pipeline 的脱敏 fixture 覆盖，包含 helper 失败、无效本地路径、hash 失败、8 MiB 边界、内容重复、不同 MIME、历史顺序、可见 reply 和隐藏嵌套 reply；运行聚焦测试并确认现有场景不回归
- [x] 4.2 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，记录每项命令结果；失败项先分类并补最小复现
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，核对 change 状态和所有 artifacts 均完成，并将实现/测试/外部 Hermes host 未确认项写入对应 evidence ledger
