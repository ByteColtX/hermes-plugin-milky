# Evidence ledger

记录日期：2026-09-09（Asia/Shanghai）

## 已执行

- `uv run pytest -q tests/test_resources.py tests/test_hermes_pipeline.py tests/test_inbound_context_rendering.py tests/test_normalizer.py`：通过，94 passed。
- `uv run pytest -q -rs`：通过，875 passed，3 skipped。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，所有 Python 文件格式检查通过。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，3 passed、0 failed。

## 语义覆盖

- `record_stt_cases.json` 覆盖纯 record、多 record、record 与文本/图片/文件混合、缺失资源和历史
  `channel_context`；fixture 只使用合成字段，不包含凭证、真实媒体 URL、本地媒体路径或敏感正文。
- resolver 测试验证 `cache_audio_from_url` 的成功/失败 occurrence、audio MIME 配对、失败占位和
  历史 record 不进入当前媒体输入。
- fake Hermes pipeline 验证纯 record 使用 `MessageType.VOICE`，`media_urls`/`media_types` 等长，
  当前正文不重复渲染 record 或 STT 提示；混合消息仍沿用既有类型规则。
- fake host 仅检查交给 core 的事件输入，并覆盖宿主侧成功、禁用、provider 失败和空转录四种状态；
  插件没有读取或改写 STT provider 状态。
- 变更文件只涉及插件入站 extractor/mapper、资源 resolver、Milky 导出、测试和 change artifacts；未修改
  Hermes core。

## Skip 与未覆盖边界

- `tests/test_adapter_lifecycle.py:637` 因 Hermes host unavailable 跳过。
- `tests/test_hermes_prompt_integration.py:17` 需要显式 `RUN_HERMES_INTEGRATION=1`，本次未启用。
- `tests/test_multimedia_outbound.py:625` 因 Hermes host unavailable 跳过。
- 未执行真实 Hermes/Milky 连接，也未验证真实 STT provider 的配置、转录成功、失败或空结果；fake host
  证据不能替代目标部署环境验证。
- 未执行真实消息发送、上传或其他远端写入。本次测试、fixture 和证据未记录 token、Authorization、
  完整响应、媒体 URL、媒体文件路径或敏感正文。

## 用户报告的已知问题

- QQ `.ogg` 语音实际编码为 AMR-NB 时，原始上传到 Groq 会返回 `400 unsupported_audio_format`；
  当前 Hermes core 没有 Groq 转码重试，本地 Whisper 已删除，因此该语音会转写失败。
- 本 change 只负责将本地 audio materialization 以 `VOICE` 交给 Hermes core，不包含音频转码、Groq
  重试或恢复本地 Whisper；上述问题仍需独立 change 处理。
