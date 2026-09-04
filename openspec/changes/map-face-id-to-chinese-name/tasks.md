## 1. Catalog 契约与测试 fixture

- [ ] 1.1 校验并固定 `milky/face_catalog.json` 的 `packs[].emojis[]` 数据边界，验证文件为合法 JSON、非 `emoji 表情` 条目使用非空字符串 `qSid`/`qDes`，且当前目录中的重复 ID 描述一致
- [ ] 1.2 增加合成 catalog 解析 fixture，覆盖已知 ID、`emoji 表情` pack、未知/空白字段、顶层结构错误、重复相同描述和冲突描述，并验证 fixture 不含 token、Authorization、真实身份、媒体 URL、路径或敏感正文

## 2. 本地映射与入站 placeholder 实现

- [ ] 2.1 增加从插件自身目录一次性读取 catalog 的解析边界，生成只读 `qSid` → `qDes` 映射，跳过 `emoji 表情` pack；验证文件缺失、JSON/结构错误、无效条目和冲突 ID 不阻止导入，并按契约返回可用映射或空/排除项
- [ ] 2.2 将入站 `face` placeholder 的显示值接入预加载映射，验证非 emoji pack 命中时使用原始 `qDes`（包括前导 `/`）、emoji pack 保留原 emoji、未命中回退原 `face_id`、缺失 ID 继续显示 `NOT SUPPORTED`
- [ ] 2.3 保持映射只影响正文 placeholder，验证 `FaceSegment` typed 字段、原始 `face_id`、segment 顺序、Will/strategy text、未知 segment、其他 placeholder 和出站 face formatter 均不发生额外变化

## 3. 入站回归与副作用边界

- [ ] 3.1 更新 `tests/test_normalizer.py` 和 `tests/test_inbound_context_rendering.py` 的 face 断言，验证真实 catalog 示例、合成未命中、emoji 和缺失 ID 在普通及复合消息中的最终正文符合 `message-segments` delta spec
- [ ] 3.2 增加 catalog 解析单元测试和 normalizer 集成测试，验证重复相同 `qDes` 可稳定命中、冲突 `qDes` 安全回退、坏目录不泄露异常正文/完整路径/敏感数据
- [ ] 3.3 通过源码或 monkeypatch 边界测试验证每条消息规范化不重新读取 catalog、不执行网络/Action/时钟/随机操作，并验证 catalog 不可用时其他消息 segment 仍照常处理

## 4. 质量门禁与交付证据

- [ ] 4.1 运行 `uv run pytest -q tests/test_normalizer.py tests/test_inbound_context_rendering.py tests/test_protocol_fixtures.py`，验证 face 映射、placeholder 顺序、协议 fixture 和既有上下文渲染全部通过
- [ ] 4.2 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，验证全量回归、Python 质量、构建和差异检查通过；失败必须按协议字段/路径、Hermes API、权限/安全、测试基础设施或真实环境差异分类
- [ ] 4.3 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，验证本 change 的 proposal、delta spec、design、tasks 与既有 `message-segments` 契约一致；未执行的真实 Milky smoke 明确记录为不适用，因为本 change 不新增网络或写入行为

## Evidence ledger

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `AGENTS.md`、`ARCHITECTURE.md`、`README.md`、`inbound/extractor.py`、相关 parser/DTO/测试、现行 `openspec/specs/message-segments/spec.md` 和本 change 的全部 planning artifacts；检查 `milky/face_catalog.json` 的结构、条目数与重复 ID | 已完成；当前仅创建规划 artifacts，未修改实现代码或用户提供的 catalog | 范围限定为入站 face placeholder；`emoji 表情` pack 不映射，出站/网络边界不变 |
| 实现与测试 | 待执行：任务 1–3 的定向测试与源码副作用检查 | 待实现阶段补充，不提前标记通过 | 若失败，先建立最小复现并按任务 3.2/3.3 补回归 |
| 质量门禁 | 待执行：任务 4.1–4.3 的 pytest、Ruff、format、build、diff 和 OpenSpec strict validation | 待实现阶段补充；本 change 不需要真实 Milky smoke | 未执行的命令不得宣称通过；若环境缺失依赖，使用项目规定的 `uv` 路径并记录阻塞 |
