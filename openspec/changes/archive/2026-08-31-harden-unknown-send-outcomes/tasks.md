## 1. 结果契约与可复现 fixture

- [x] 1.1 审查实际运行版本的 Hermes Gateway fallback 调用点、SendResult 字段和 plugin adapter 分派边界，形成不含路径、凭证、真实 ID 或正文的兼容性记录；用源码定位和最小 fake host 验证 `transport_unknown` 是否会落入 fallback，并记录可验证的 plugin-local delivery hook 或 blocked 结论，不修改或依赖 Hermes core
- [x] 1.2 建立脱敏的延迟响应/响应路径中断 fake transport 或本地 HTTP fixture，记录请求已到达服务端、服务端延迟完成而客户端未获得成功 envelope 的场景；验证客户端结果为 `transport_unknown` 且 fixture 不保存 live 消息、token 或响应正文
- [x] 1.3 建立连接建立、请求写入、响应读取、连接池、超时和取消边界的安全诊断 fixture；验证每类诊断只包含固定 phase/reason、耗时和脱敏关联字段，不包含原始异常、URL、Authorization、请求 body 或响应 body

## 2. Milky Action 结果与诊断

- [x] 2.1 调整 Milky HTTP transport 与 Action 调用边界，在保留顶层 `transport_unknown` 语义的同时输出有限的传输阶段诊断；验证已进入 HTTP 边界但响应路径中断时不返回成功、不生成本地消息 ID，并保持 client 关闭/取消行为
- [x] 2.2 为 Action client 增加“未知结果不可重入”的回归测试，覆盖延迟响应、读取异常、连接异常和超时；验证每个可能产生副作用的 POST 最多只发出一次，且 `transport_unknown` 不触发 client 内部重试
- [x] 2.3 复核成功、协议拒绝、malformed、unsupported 和本地参数错误的边界测试；验证只有带远端 `message_seq` 的成功 envelope 才能生成 SendResult，其他结果不被降级为假成功

## 3. 出站与 Hermes Gateway 兼容边界

- [x] 3.1 收紧 plugin 出站发送结果的终态和 `retryable` 语义，确保群聊和私聊的 `transport_unknown` 原样返回；用 fake outbound client 验证 sender 不调用第二次 send Action、不改变消息内容、不生成 plain-text fallback
- [x] 3.2 建立 fake Hermes Gateway fallback contract，覆盖本地格式化失败、远端明确拒绝、传输未知和成功四类输入；将其限定为目标语义辅助证据，实际宿主分派必须由 adapter 边界回归验证
- [x] 3.3 审查实际 Hermes Gateway 的 adapter 分派；若存在可验证 delivery hook，则用集成 fixture 证明 Milky adapter 不进入通用 fallback；若不存在则记录 blocked，plugin 不通过吞异常、假成功、文本匹配或自建 host 逻辑规避
- [x] 3.4 补充本地格式化失败与结构化消息测试，验证非法/空内容在网络访问前结束，且不会发送带诊断前缀的用户可见 fallback 文本

## 4. MuteTracker 刷新解耦

- [x] 4.1 将群发送失败后的 MuteTracker 刷新改为独立的受控只读维护，不等待刷新结果来决定发送返回值或 fallback；验证原始 `transport_unknown` 在刷新成功、失败和超时后均保持不变
- [x] 4.2 保持每群锁、冷却和全局并发上限，并将刷新任务纳入 adapter 停止清理；验证同群并发失败不会产生无界 `get_group_member_info(no_cache=true)` 请求，私聊失败仍不会查询群成员
- [x] 4.3 增加刷新时序回归，模拟第一次群消息已被服务端接受、客户端结果未知、随后刷新成员状态的完整顺序；验证最多一次状态刷新且绝不触发第二次消息发送

## 5. 端到端回归与观测

- [x] 5.1 组装 fake Milky server、Action client、MuteTracker、outbound sender 和 fake Hermes Gateway 的端到端场景；验证服务端完成第一次消息、客户端返回 `transport_unknown` 时最终只产生一次用户可见消息，且无 plain-text fallback
- [x] 5.2 覆盖 group/dm、明确协议拒绝、连接/读取异常、客户端取消、发送前格式化失败和第二次独立消息；验证只有未知发送结果禁止重发，独立的新消息仍可按正常流程发送
- [x] 5.3 补充安全日志断言，验证 Action、outbound、MuteTracker 和宿主兼容性诊断能用关联字段重建时序，但不输出凭证、原始异常、请求/响应 body、真实 ID、路径或敏感正文
- [x] 5.4 将用户提供的服务端证据归纳为脱敏时序 fixture 和执行台账，明确“重复发送已证实”和“底层传输异常类型仍待运行时日志确认”两个结论；验证仓库中不出现 live snapshot 或真实返回序号

## 6. 质量门禁与交付

- [x] 6.1 运行相关 Milky client、outbound、MuteTracker、生命周期和集成测试，验证新增未知结果、fallback、刷新时序和安全诊断场景全部通过
- [x] 6.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`；记录依赖缺失、宿主接口阻塞或真实环境差异，不把未执行的检查标记为通过
- [x] 6.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证三个 modified capability 的 requirement、scenario 和 tasks 一致，并在本台账记录最终未解决风险
- [x] 6.4 仅在取得独立明确授权后执行真实 Milky 写入 smoke；否则使用本地延迟 fixture 完成副作用回归，并确认没有发送测试消息、上传文件或修改远端状态

## 7. plugin-only 宿主 fallback 隔离

- [x] 7.1 在实际 `MilkyAdapter` 发送包装边界添加最小回归：注入 `transport_unknown` 的 sender 结果，确认当前实现会缺少一次性边界或进入宿主通用路径；测试不得以 fake Gateway 代替 adapter 分派
- [x] 7.2 在不修改 Hermes core 的前提下，实现经当前宿主动态分派验证的 adapter-local 一次性发送覆盖；确认每个 Milky 发送只调用一次 sender，原样返回成功、拒绝、本地错误或 `transport_unknown`，不调用 retry、失败通知或 plain-text fallback
- [x] 7.3 运行 adapter/outbound/client 相关测试与全量质量门禁，记录本次修复不执行真实 Milky 写入，且底层 transport unknown 的独立环境诊断不影响重复发送已消除的结论

## 执行证据台账

| 任务 | 证据 | 结果与后续 |
|---|---|---|
| 1.1 | 2026-08-30 检查本机 Hermes Gateway 兼容实现：宿主 `SendResult` 暴露 `retryable` 与 `error_kind`，但通用发送决策只按 `retryable`、旧错误字符串模式和 timeout 字符串选择分支；`transport_unknown` 会进入 plain-text fallback。 | 此观察确认通用包装不安全；后续 task 7 在不修改 core 的前提下验证了 `MilkyAdapter._send_with_retry()` 的动态分派覆盖，替代此前“需要 core 配套”的暂定结论。 |
| 1.2/1.3/2.1/2.2/2.3 | 新增 `tests/test_unknown_send_outcomes.py` 的延迟响应、响应路径中断、HTTPX connect/write/read/pool 阶段、脱敏字段和单次请求测试；相关 client/observability 回归 `73 passed, 3 skipped`，HTTPX 补跑 `14 passed`；`ruff check` 通过，format 已修正。 | `transport_unknown` 保持未知语义，阶段只输出固定枚举；异常细节、凭证、请求/响应内容未进入结果或日志。 |
| 3.1/3.2/3.3/3.4 | `outbound/sender.py` 显式为失败结果设置 `retryable=False`，群失败刷新改由 sender 持有的可取消任务独立调度；`adapter.py` 在停止时关闭 sender；`tests/test_unknown_send_outcomes.py` 覆盖 group/dm 单次 Action、原始 segment、四类 fake Gateway contract、显式安全 fallback 标记、格式化前拒绝和刷新清理；新增 `hermes-gateway-compatibility.md` 记录通用宿主 fallback 的风险。定向回归 `44 passed, 7 skipped`，ruff/format 通过。 | fake contract 不足以覆盖真实宿主分派；task 7 改以 `MilkyAdapter` 的一次性 delivery hook 解决，未编辑 core、未伪造成功或改写错误。 |
| 4.1/4.2/4.3 | sender 的刷新任务由 `close()` 统一取消并由 adapter disconnect 调用；`tests/test_unknown_send_outcomes.py` 验证刷新成功、失败、超时不改变未知结果，已接受首条消息只刷新一次；`tests/test_mute_tracker.py` 进一步通过 20 条并发群未知结果验证同群只产生一次 `get_group_member_info(no_cache=true)`，并验证 dm 不刷新。定向回归 `66 passed, 7 skipped`。 | 原始发送结果先返回，刷新为 best-effort 只读维护；停止时不遗留刷新任务，私聊不触发群成员查询。 |
| 5.1/5.2/5.3/5.4 | `tests/test_unknown_send_outcomes.py` 新增 fake Milky 延迟响应、fake Action client、fake MuteTracker、fake Gateway 端到端回归，以及取消、独立消息和证据脱敏断言；新增 `tests/fixtures/unknown_send_outcome_timeline.json`，只保留相对顺序、Action 名称、分类和“重复已证实/异常类型未确认”结论。 | 本地合成场景最终只保留一次可见发送且无 fallback；未执行真实 Milky 写入，用户日志中的底层异常类型仍标记为待运行时确认。 |
| 6.1 | 相关定向测试 `66 passed, 7 skipped`；HTTPX 补跑 `uv run --with httpx==0.28.1 pytest -q` 为 `338 passed`；普通环境全量测试为 `319 passed, 19 skipped`。 | 新增未知结果、出站终态、刷新时序和安全诊断回归均通过；普通环境跳过项仅为未安装宿主提供的 HTTPX。 |
| 6.2/6.3 | `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 全部通过；`npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` 返回 `3 passed, 0 failed`。 | 当时的核心配套风险已由 task 7 的 plugin-local adapter override 取代；本轮会重新执行全部门禁。 |
| 6.4 | 未取得真实 Milky 写入授权，使用 `DelayedResponseLossTransport` 和本地 fake Gateway 完成服务端已接受/客户端未知的副作用回归；未执行真实发送、上传、撤回或状态修改 Action。 | 真实环境差异和安全边界均已保留；本轮不执行真实写入，使用 adapter 边界回归阻止同一 delivery invocation 的 fallback 重发。 |
| 7.1/7.2 | 2026-08-31 先在 `tests/test_adapter_lifecycle.py` 添加真实 `MilkyAdapter._send_with_retry()` 最小回归，初始失败为缺少一次性 hook；随后在 `adapter.py` 覆盖该 hook，只调用一次 `self.send()` 并原样返回。回归覆盖 `transport_unknown`、成功、`invalid_input`、`rejected` 和 `malformed`；未使用错误文本、内容/时间窗去重、假成功或 fake Gateway 代替 adapter 分派。 | 同一 delivery invocation 不再进入宿主的 retry、失败通知或 plain-text fallback。只读核对显示 Gateway 动态调用 adapter hook，且已有平台 adapter 使用同一扩展方式；未修改、提交或要求修改 Hermes core。 |
| 7.3 | adapter/outbound 定向回归为 `71 passed, 7 skipped`；本地 HTTPX 集成为 `47 passed`；完整 plugin 测试为 `324 passed, 20 skipped`，带 HTTPX 为 `343 passed, 1 skipped`。在 Hermes Python 3.13 开发环境运行实际 host hook probe 为 `1 passed`；`ruff check`、format check、`uv build`、`git diff --check` 和 OpenSpec strict validation 均通过。 | 未执行真实 Milky 写入。底层约 6ms `transport_unknown` 的网络/连接池原因仍是独立环境诊断，未改变本次“同一调用 fallback 重复发送已阻断”的结论；跨进程 ledger 重投递不属于本轮可安全消除范围。 |
