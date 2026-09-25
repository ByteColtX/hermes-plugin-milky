# align-slash-command-experience 验证记录

日期：2026-09-26。范围为本 change 的命令展示、只读状态观察、解析别名及既有路由/生命周期回归。
所有本地测试使用合成身份、元数据、fake transport 或 fake host，不等于真实 Hermes/Milky/QQ 验收。

## 本地验证

- 顶层与 allowlist 聚焦：`uv run pytest -q tests/test_slash_commands.py tests/test_hot_allowlist.py`：147 passed。
- 注册、命令、白名单、生命周期、SSE 与状态聚焦：`uv run pytest -q tests/test_plugin_entry.py tests/test_hot_allowlist.py tests/test_slash_commands.py tests/test_adapter_lifecycle.py tests/test_milky_event_stream.py tests/test_runtime_status.py -rs`：232 passed，1 skipped。跳过原因是 Hermes host is unavailable，不能视为真实宿主通过。
- `openspec validate --changes --strict`：5 个活动 change 通过，0 失败。
- 最终完整检查：
  - `uv run pytest -q`：1392 passed，3 skipped，7.76 秒。
  - `uv run ruff check .`：All checks passed。
  - `uv run ruff format --check .`：548 files already formatted。
  - `uv build`：成功生成 1.9.1 sdist 和 wheel；本项目仍为 directory plugin，此检查不代表宿主部署。
  - `git diff --check`：通过，无空白错误。
  - `openspec validate --changes --strict`：5 passed，0 failed。
- 早期聚焦运行暴露旧 JSON/标题断言及测试 fake 视觉签名问题，修正后重新运行；它们没有被记为通过。
  首次最终格式检查指出一个新增测试需格式化，已修正并复查通过。

完整测试的 3 个 skip 已单独用 `-rs` 核实：

1. `test_adapter_lifecycle.py::test_actual_hermes_delivery_hook_returns_unknown_result_once`：Hermes host is unavailable。
2. `test_hermes_prompt_integration.py::test_real_hermes_prompt_lifecycle`：未显式设置 RUN_HERMES_INTEGRATION=1。
3. `test_multimedia_outbound.py` 的真实宿主检查：Hermes host unavailable in the current test environment。

## 行为证据

- `tests/test_slash_commands.py`：顶层/allowlist 静态帮助在零、单、多依赖下不调用工厂；
  已知动词就近错误及敏感输入不回显；实现信息单次 Action、完整字段、安全失败和取消传播；
  状态读取跨解绑重绑失效，README 顶层/allowlist 帮助逐字匹配。
- `tests/test_sticker_text.py`：45 项文本/解析测试，包括图库缺失时静态帮助、全部动词错误、
  del/remove 同状态单次删除、列表顺序与字段来源/统计、混合批次、零候选、两种预览、未知存储结果。
- `tests/test_sticker_maintenance.py`、`test_sticker_search.py`、`test_sticker_send.py`
  已将 slash JSON 数据准备迁移到原有结构化维护方法；与 management/fallback 一同运行：139 passed。
  Web/Tool 原字段和分类仍由完整测试回归，没有改成解析中文。
- `tests/test_runtime_status.py` 及生命周期/SSE 聚焦：66 passed，1 skipped。
  覆盖可控单调时钟、墙钟变化、重连/停止/重启、配置集合比较、版本与归属竞争、未知字段；
  额外验证 connect 返回而 SSE 任务尚未调度时明确显示连接中。
- `tests/test_slash_experience_integration.py`：25 passed，验证普通 Gate/core 分发、allowlist 专属例外、
  管理不查来源群、长帮助/20 条贴纸/70 条完整白名单的分块与合并转发内容不丢失、发送失败不重复删除。
- README 的贴纸帮助、合成列表与导入预览由实际展示入口生成；ARCHITECTURE 记录生命周期状态所有权。

以上是 fixture/fake host/本地 transport 证据，真实 QQ 视觉效果仍为下表 unknown。

## 真实 Hermes / Milky / QQ 验收矩阵

本次没有真实 QQ 收发或图库维护授权，也没有可确认的真实 Hermes 验收环境；不发送命令、
不上传、导入、删除或修改真实条目。以下逐项保留 blocked/unknown，代码和 fake host 证据
只能证明本地契约。无参数查询虽然只读，仍没有经过真实宿主到 QQ 的命令回执验证。

| 验收项 | 状态 | 外部限制 |
| --- | --- | --- |
| 无参数 `/milky` 的实现信息查询和中文失败回执 | blocked / unknown | 缺少真实授权测试链路 |
| status 正常运行、首次连接和 SSE 重连 | blocked / unknown | 缺少真实宿主和可控网络验收 |
| status 配置不同、配置未知、实例归属未知 | blocked / unknown | 缺少真实 profile 配置验收 |
| 顶层、sticker、allowlist 三层帮助 | blocked / unknown | 未经真实 QQ 收发与阅读验收 |
| 就近格式错误和非法输入不回显 | blocked / unknown | 未经真实 QQ 命令分发验收 |
| 贴纸空库与非空有界列表 | blocked / unknown | 缺少授权验收图库及真实收发 |
| add/cleanup dry-run 预览 | blocked / unknown | 无真实图库维护及视觉验收授权 |
| edit/reanalyze/del/remove 单项回执 | blocked / unknown | 无真实图库维护授权 |
| add 混合批次与 cleanup/reindex 分类结果 | blocked / unknown | 无真实图库维护授权 |
| 长帮助、列表、预览的分块和合并转发阅读效果 | blocked / unknown | fake 发送器不证明 QQ 字体和客户端效果 |

## 副作用与交付边界

仅进行本地代码、文档、测试和构建修改；未发起真实 Milky Action、QQ 收发、图库维护、
发布或合并。Web/Tool 和共享维护结果保留结构化接口，slash 纯文本不作为程序接口。
