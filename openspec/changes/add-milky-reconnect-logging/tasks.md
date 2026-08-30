## 1. 契约与脱敏 fixture

- [x] 1.1 新增断连后恢复的脱敏 SSE fixture 或等价 fake transport 输入，使用合成事件和 EOF 边界，并验证 fixture 不含真实身份、凭证、完整正文、媒体 URL 或本地路径
- [x] 1.2 在事件流测试中固定日志事件标签、reason 白名单、attempt/delay_seconds 字段和生命周期顺序，并验证测试只捕获安全日志字段

## 2. 事件流日志实现

- [x] 2.1 在 `milky/event_stream.py` 增加宿主标准日志输出和安全 reason 归一化，验证底层异常文本、响应内容和认证材料不会进入日志或 `StreamDiagnostic`
- [x] 2.2 在 receive loop 的连接状态转移中输出 `milky_event_stream_disconnected`、`milky_event_stream_reconnect_scheduled`、`milky_event_stream_reconnect_attempt` 和 `milky_event_stream_reconnected`，验证 EOF、连接失败、超时、HTTP 错误和协议错误按白名单分类且 attempt 与实际退避值一致
- [x] 2.3 接入取消优先级和 attempt 周期重置，验证停止/取消只输出一次 `milky_event_stream_cancelled`，不误报异常断连、不等待剩余退避、不发起新连接，并继续释放 response、transport、timer 和 handler 资源

## 3. 回归测试与反馈闭环

- [x] 3.1 增加 EOF 后断连—退避—attempt—恢复的 caplog 顺序测试，验证 1-based attempt、`delay_seconds`、reason 和同一 `/event` 端点行为，同时验证成功恢复后下一轮 attempt 从 1 重新开始
- [x] 3.2 增加首次连接失败、连续失败和 max backoff 的日志测试，验证每次 attempt/schedule 均可观察、reason 不泄露原始异常、未知异常安全降级为白名单值，且既有 diagnostics 与重连行为不回归
- [x] 3.3 增加退避期间取消、连接建立期间取消、EOF 与取消竞态及重复 close 测试，验证取消日志不重复、不产生后续 attempt/disconnected 日志，handler/response/transport 仍恰好释放

## 4. 质量门禁与交付证据

- [x] 4.1 运行 `uv run pytest tests/test_milky_event_stream.py -q` 和相关本地 HTTPX SSE 集成测试，验证新日志测试及既有帧解析、非阻塞 handler、重连和资源释放测试全部通过；若宿主缺少 HTTPX，按项目约束使用 `uv run --with httpx==0.28.1` 并在证据台账记录结果
- [x] 4.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，验证全量测试与 Python 质量门禁通过，并将失败按协议字段/路径、并发/顺序、权限/安全、真实环境差异或测试基础设施分类
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证本 change 的 spec、design、tasks 与既有契约一致；若发现失败，先补最小复现或回归测试、修复后重新执行全部相关门禁，并把命令结果和未解决风险写入本文件证据台账

## 5. 证据台账

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `ARCHITECTURE.md`、现有主契约 `milky-event-stream` 及当前 active change 全部 artifacts | 待实现阶段补充 | 规划范围限定为日志可观察性，不改变 SSE 协议和退避算法 |
| 实现与测试 | `uv run pytest tests/test_milky_event_stream.py tests/test_milky_local_integration.py -q`；`uv run --with httpx==0.28.1 pytest tests/test_milky_event_stream.py tests/test_milky_local_integration.py -q`；`uv run pytest`；`uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check` | 普通环境 19 passed/9 skipped；HTTPX 补跑 28 passed；全量 276 passed/12 skipped；其余门禁通过 | 测试基础设施：宿主未提供 HTTPX，使用 uv 临时依赖补跑；未执行真实 Milky Action；未发现协议、并发或安全回归 |
| OpenSpec | `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict` | 3 changes passed，0 failed | 无未解决的规范校验风险 |
