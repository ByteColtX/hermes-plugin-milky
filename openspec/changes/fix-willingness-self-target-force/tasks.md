## 1. 回归测试

- [x] 1.1 扩展 `tests/test_will_willingness.py` 的输入构造和 force 测试，覆盖 Bot direct mention、他人/全体/`here` mention、引用 Bot、引用他人、目标未知及多个 reply 中任一引用 Bot；验证对应场景分别符合 `will-willingness` delta spec，且 force 场景不会调用随机源
- [x] 1.2 扩展 willingness gain 回归测试，覆盖 self/non-self/unknown mention、self/non-self/unknown quote、多 reply 中任一 self quote、self/non-self/unknown poke；验证 `mentionGain`、`quoteGain`、`pokeGain` 只对 Bot 目标生效且每条消息或事件最多计算一次

## 2. Force 决策实现

- [x] 2.1 调整 `will/willingness.py` 的 force 判定，使 `mentionForce` 只消费 self mention，使 `quoteForce` 只消费 self quote，并保持 direct、mention、quote、forceKeywords 的顺序及概率回退；验证 `uv run pytest -q tests/test_will_willingness.py`
- [x] 2.2 检查 inbound 到 `WillInput` 的目标特征传递，确认不需要新增网络请求、raw 重解析或协议字段；验证 normalizer 相关测试及 force 目标矩阵通过
- [x] 2.3 调整 `will/willingness.py` 的 gain 判定，使 `mentionGain` 只消费 self mention、`quoteGain` 只消费 self quote、`pokeGain` 只消费 self-poke；保留 `has_reply` 上下文事实和非 self poke 的既有观察流程，并验证聚焦 willingness 测试

## 3. 契约与文档同步

- [x] 3.1 更新 `README.md`，明确 `mentionGain`、`quoteGain`、`pokeGain` 以及对应 force 只针对 Bot 目标，并说明 `has_reply` 不单独产生 `quoteGain`；验证文档中的旧宽泛描述已消除
- [x] 3.2 在归档前依据本 change 的 delta spec 同步 `openspec/specs/will-willingness/spec.md`；验证主 spec 与实现、测试和 README 使用一致的 gain/force 目标语义

## 4. 质量门禁

- [x] 4.1 运行完整 `uv run pytest -q`，确认既有 routing、normalizer、pipeline 和 willingness 回归通过
- [x] 4.2 运行 `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，记录结果并确认无凭证、敏感正文或真实媒体路径进入变更
- [x] 4.3 在 gain 目标实现和文档同步后重新运行完整 `uv run pytest -q`、Ruff、format、build、diff check 和 OpenSpec strict validation，并记录 gain 目标矩阵及安全边界证据

## Evidence ledger

记录日期：2026-09-06（Asia/Shanghai）

### 已执行

- `uv run pytest -q tests/test_will_willingness.py tests/test_normalizer.py`：通过，45 passed。
- `uv run pytest -q -rs`：通过，821 passed，2 skipped；skip 为当前环境没有 Hermes host 的
  `tests/test_adapter_lifecycle.py:485` 和 `tests/test_multimedia_outbound.py:625` 集成测试。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，319 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，1 passed、0 failed。
- 变更 diff 与当前 change artifacts 已检查；未新增凭证、Authorization、敏感正文、真实媒体 URL
  或本地媒体路径。

### 本次 gain 目标实现后的证据

- `uv run pytest -q tests/test_will_willingness.py`：通过，34 passed；目标矩阵覆盖 self/non-self/unknown
  mention、self/non-self/unknown quote、多 reply 中任一 self quote，以及 self/non-self/unknown poke，
  并验证 self mention/self quote 在一条消息内只计算一次。
- 完整 `uv run pytest -q -rs`：通过，833 passed，2 skipped；skip 仍为当前环境没有 Hermes host 的
  `tests/test_adapter_lifecycle.py:485` 和 `tests/test_multimedia_outbound.py:625` 集成测试。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`：全部通过；
  format 检查为 319 files already formatted。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，1 passed、0 failed。
- 安全边界复核：gain 实现只消费既有 `WillInput.mention_self`、`is_self_quote` 和 `is_self_poke`；
  未新增网络请求、raw 重解析、协议字段、日志正文、凭证、Authorization、真实媒体 URL 或本地媒体路径。

### 未覆盖与边界

- 未执行真实 Milky/Hermes host 连接；当前证据来自 fake host、typed fixture 和本地单元测试，不能
  替代真实服务及宿主能力验证。
- 未执行真实消息发送、文件上传或其他远端写入；本 change 不涉及远端写入路径。
