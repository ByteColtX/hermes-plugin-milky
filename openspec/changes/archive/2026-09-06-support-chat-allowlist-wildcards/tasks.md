## 1. 配置规则解析

- [x] 1.1 在现有 chat key 身份校验边界中增加仅允许 `dm:*` 和 `group:*` 的规则校验，并保持 `MILKY_HOME_CHANNEL` 只接受具体 chat key；用配置单元测试验证合法规则、空白裁剪、规范化去重和非法格式拒绝
- [x] 1.2 扩展 `MILKY_ALLOWED_CHATS` 解析与配置快照，使具体条目和命名空间通配符可混用且不展开外部会话；用 `tests/test_config.py` 验证 `dm:*`、`group:*`、混合配置、重复项、空值及安全错误分类

## 2. 入站白名单 Gate

- [x] 2.1 扩展白名单判断，使完整 chat key 精确命中或对应的 `dm:*` / `group:*` 命中时放行，并保持 `chat_not_allowed`、Gate 固定顺序及其他 Gate 语义；用 `tests/test_gate_registry.py` 验证 friend/group 命名空间隔离和具体规则与通配符混用
- [x] 2.2 验证通配符不会改变 canonical chat key、temp 忽略、per-chat 状态或出站目标；用相关 pipeline、identity 和 outbound 测试确认未产生跨边界授权或下游副作用

## 3. 文档、契约与质量门禁

- [x] 3.1 更新 `README.md`、`plugin.yaml` 和 `ARCHITECTURE.md`，说明四种允许条目、`dm:*` / `group:*` 的命名空间范围、空值语义和旧版本回滚限制；用文档搜索确认描述与 delta spec 一致
- [x] 3.2 运行 `uv run pytest -q tests/test_config.py tests/test_gate_registry.py tests/test_canonical.py tests/test_hermes_pipeline.py`，确认 focused 回归通过
- [x] 3.3 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，确认完整质量门禁通过
- [x] 3.4 运行 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，确认 change artifacts、主 spec 引用和实现前契约一致

## Evidence Ledger

- 当前状态：运行时代码、测试、配置提示和架构文档已完成实现；两个 delta spec 已同步到主 spec，change 已归档。
- 已通过：`uv run pytest -q`（781 passed, 2 skipped）；focused pytest（118 passed）；`uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check`。
- 已通过：`openspec validate --specs`（24 passed, 0 failed）；`npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`（2 passed, 0 failed）。
- 外部环境：本 change 不需要真实 Milky 网络 smoke；若后续执行 smoke，必须遵守 `MILKY_ALLOWED_CHATS` 和 `--allow-write` 约束。
