# 验证证据

## 实现与合成库 / fake host 证据

- 搜索只接受 mode、intent、emotion、tags、limit；默认有查询为 strict，无查询为 browse。
  fallback 必须显式提供 intent 和 emotion 或 tags，忽略 intent 并保留情绪精确筛选、标签 OR 条件。
- strict 保留原相关性排序；fallback 按请求 tag 命中数降序、ID 升序；browse 按 ID 升序。
  三者都遵守默认 5、最多 10 的 limit，strict 无匹配不兜底。12 条合成库验证上限、稳定顺序与去重。
- 搜索结果只含 status、match_mode、items，候选只含 sticker_id、emotion、tags、description。
  缺失文件、无效双索引、越界描述、非法情绪和归一化重复标签被过滤，序列化器拒绝越界与重复候选。
- 严格查询发送无匹配时返回 alternatives；满足 fallback 输入条件时最多 5 条，否则为空。
  工具级测试确认回执与 fallback 搜索一致、不调用发送、不改变全局或 chat 统计；显式 ID 后才执行一次发送。
- 搜索使用 mode=ro SQLite 连接，不调用写入 factory、不创建默认宿主 plugin-data 目录、不迁移旧 schema，
  不读取完整图片或调用视觉服务。发送在匹配和文件验证后才打开写连接，no_match 也不迁移或写入。
  旧 schema 尚无会话统计表时，并列候选仍能选择、随后迁移并 claim 一次。
- 非法参数在会话/存储访问前失败；非法上下文、服务解绑和 sender 解绑 fail closed。
  缺失/不兼容库为 unsupported，访问故障为 storage_error。日志仅记录固定工具名、分类和耗时。
- http_error、malformed、transport_unknown 均最多调用一次发送；精确 ID 的 not_found、missing_file
  及原有统计 claim、文件完整性和生命周期边界继续通过测试。
- README、ARCHITECTURE、QQ bundled skill 与 Tool definition 已同步三模式、备选、显式 ID 与结果语义。
  按用户要求移除个性化决策、调用顺序、搜索次数及回复策略；这些偏好由用户自行写入 SOUL 或 memory。

## 本地检查（2026-09-24）

- 聚焦检查：
  uv run pytest -q -rs tests/test_sticker_fallback.py tests/test_sticker_search.py tests/test_sticker_send.py tests/test_sticker_maintenance.py tests/test_qq_tools.py tests/test_adapter_lifecycle.py tests/test_plugin_entry.py tests/test_outbound.py tests/test_tool_result_passthrough.py
  结果为 308 passed、1 skipped。skip 为 adapter_lifecycle 的独立测试进程中 Hermes host unavailable。
- 全量 uv run pytest -q -rs：1075 passed、3 skipped。
  - adapter_lifecycle：Hermes host is unavailable。
  - hermes_prompt_integration：未显式设置 RUN_HERMES_INTEGRATION=1；该检查针对 prompt 生命周期。
  - multimedia_outbound：Hermes host unavailable in the current test environment。
- uv run ruff check .、uv run ruff format --check .、git diff --check：通过。
- openspec validate --changes --strict：9 个未归档 change 全部通过。
- uv build：source distribution 和 wheel 构建成功。

## 真实 Hermes 组件验证（与 fake host 分开）

- 本机真实 Hermes 源码可用，原有虚拟环境是 Python 3.11，未直接用其加载要求 Python 3.13+ 的插件。
  使用项目 uv 的 Python 3.13.5，通过临时依赖覆盖加载真实宿主源码；未修改宿主源码或其虚拟环境。
- 命令：uv run --with pyyaml --with python-dotenv scripts/hermes_sticker_integration.py。
  可用 HERMES_SOURCE_ROOT 指定宿主 checkout。
- 通过真实 PluginContext、PluginManager 和插件根 register 入口注册；真实 registry 在两个独立
  task-local session 中重新发现含 mode 的 definitions；真实注册 handler 与 registry 结果规范化器
  交付 strict/fallback/browse 结果及 no_match alternatives，字段未丢失。
- 验证在临时 HERMES_HOME 中使用合成贴纸和合成视觉结果，未创建真实用户库，未建立 Milky 连接。
  本证据覆盖任务 4.3 的宿主组件契约，不覆盖在线模型决策、完整 Agent turn 或实际 QQ 投递。

## 真实 Milky 写入授权状态

任务 4.4 仍为 blocked / 未验证：本次没有明确的真实目标及单次发送授权，未执行真实 Milky ID 发送。
搜索与 no_match 不发送的行为已由本地及真实宿主组件探针验证，不能据此声称真实 QQ 发送成功。
继续此项需要明确目标 chat key 与发送授权，并在运行时 MILKY_ALLOWED_CHATS 内确认该目标。
2026-09-24：用户明确接受任务 4.4 未完成，授权同步本次规范并以当前代码为准后归档。真实 Milky ID 发送仍为 blocked / 未验证，任务 4.4 保持未勾选；归档不代表该项验证通过。

## 合入 main 后的兼容验证

- 与图库管理面板合并时，保留发送候选选择、文件读取和统计 claim 外层的图库协调锁；
  只读候选选择与延迟打开写连接均在锁内，网络发送仍在释放锁后执行。
- 合并后全量 uv run pytest -q -rs：1163 passed、3 skipped；跳过原因与上述三项一致。
- Ruff、格式检查、暂存差异检查、OpenSpec 严格校验（6 个未归档 change）和 uv build 均通过。

## 归档检查（2026-09-24）

- 本次两个 delta 的所有 requirement 和 scenario 已逐块核对并同步到主规范。
- 根据当前发送参数解析、ID 查找和文件校验代码，修正主规范中禁止显式 ID 的旧限制。
- 前置 change add-sticker-search-and-id-send 的结果分类 delta 保留本次新增场景，避免未来同步回退。
- 聚焦测试：uv run pytest -q -rs tests/test_sticker_search.py tests/test_sticker_fallback.py tests/test_sticker_send.py，101 passed，无 skip。
- openspec validate --specs --strict：28 passed；openspec validate --changes --strict：6 passed；git diff --check：通过。
- 任务 4.4 仍未完成，未执行真实 Milky 发送。
