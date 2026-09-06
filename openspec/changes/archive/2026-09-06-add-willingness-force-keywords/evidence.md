# Evidence ledger

记录日期：2026-09-06（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_config.py tests/test_will_willingness.py tests/test_hermes_pipeline.py tests/test_wait_buffer.py`：通过，114 passed。
- `uv run pytest -q`：通过，795 passed，2 skipped。
- `uv run pytest -q -rs`：通过，795 passed，2 skipped；跳过项为当前环境未提供 Hermes host 的
  `tests/test_adapter_lifecycle.py:457` 和
  `tests/test_multimedia_outbound.py:625` 集成测试。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，299 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，2 passed、0 failed；
  输出包含当前 change 及同时存在的 `charge-willingness-on-trigger`。
- 配置测试覆盖默认空数组、合法/非法关键词数组和旧 `willingness.keywords` 拒绝；willingness
  测试覆盖兴趣增益、强制关键词跳过随机抽样、不额外增加 score 及组合命中；pipeline 测试覆盖
  Gate、temp、命令、系统事件、wait、reply cost 和后续交接失败边界。

## 未覆盖与边界

- 未执行真实 Milky/Hermes host 连接；fake transport、fixture 和 fake Hermes 结果不能替代真实
  服务及宿主能力验证。
- 未执行真实消息发送、文件上传或其他远端写入；本 change 没有新增写入 Action，真实操作仍需
  明确授权和运行时目标校验。
- `forceKeywords` 的直接子串、跳过概率抽样和一次 reply cost 已由本地测试验证，但真实部署中
  的 Hermes turn 接收、资源解析和 QQ 发送链路仍未实机确认。
- 测试只使用合成配置、会话标识、正文和随机源；未记录凭证、Authorization、媒体 URL、真实
  业务身份、完整响应或敏感正文。
