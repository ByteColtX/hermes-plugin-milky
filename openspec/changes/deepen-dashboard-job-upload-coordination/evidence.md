# Evidence

## 本地合成 provider

- `uv run pytest -q -rs`：1408 passed，3 skipped。
- Dashboard 任务、上传、生命周期和视觉名额专项：29 passed。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check`：通过。
- `openspec validate --changes --strict`：本 change 通过；整体校验仍受其他既有 change 的独立失败影响。
- 这些结果来自本地临时目录、合成上传和合成视觉执行器，不证明真实 Hermes 或真实视觉 provider。

## 真实 Hermes 宿主

- 已尝试运行既有 `scripts/dashboard_plugin_probe.py`，使用隔离合成 profile；当前环境缺少可用宿主依赖，probe 返回 `ModuleNotFoundError`，因此记为 blocked。
- 未连接 Milky、真实视觉 provider 或执行外部写入；没有将该结果计入通过项。
