# Evidence ledger

记录日期：2026-09-08（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_config.py tests/test_outbound.py tests/test_outbound_splitting.py tests/test_unknown_send_outcomes.py`：通过，188 passed。
- `uv run pytest -q tests/test_long_text_forwarding.py tests/test_adapter_lifecycle.py tests/test_milky_client.py`：通过，84 passed、1 skipped；覆盖配置、sender、standalone、live adapter 身份绑定、HTTP 空 JSON body 和生命周期回归。
- `uv run pytest -q -rs`：通过，836 passed、2 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，355 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，3 passed、0 failed。

## 行为证据

- 配置单测覆盖缺省值、`0`、`1`、`4096`、空值、负数、非数字和越界值；安全摘要只增加阈值数值，不包含凭证或聊天目标。
- sender 单测覆盖严格大于阈值、字面量 `[[SPLIT]]`、全部非空 `[SPLIT]` 逻辑段、超过三段、4096 字符边界、CQ/native image/record/video、group/dm 单一 Action、固定 fallback 身份和 forward 失败不重试。
- live adapter fake 生命周期测试证明初始同步确认的 Bot 身份绑定到 sender；普通消息和 forward 均不重复调用登录信息。standalone 只在阈值触发时读取身份，客户端 `get_login_info` 使用 `{}` 请求体。
- 本地 native media 预检失败时消息 Action 数为零；现有独立文件 upload 和“文本后附件”的分离 handoff 回归仍通过。插件不猜测分离的 `MEDIA:` 调用属于同一 forward 批次。

## 未覆盖与 skip

- 未执行真实 Milky forward 写入 smoke：当前没有用户明确写入授权、运行时 `MILKY_ALLOWED_CHATS` 和可用真实服务条件；未使用 `--allow-write`，不把 fake/fixture 结果当作真实协议通过。
- 全量 pytest 的 2 个 skip 是既有 Hermes host 不可用测试（`tests/test_adapter_lifecycle.py:541`、`tests/test_multimedia_outbound.py:625`），不代表真实 Hermes host 集成通过。
- 测试使用合成身份、目标、正文和媒体引用；证据不记录 token、Authorization、真实 QQ、完整响应、媒体 URL、文件内容或本地路径。
