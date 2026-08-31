## 1. 契约与安全 fixture

- [x] 1.1 根据当前 Hermes `BasePlatformAdapter` 和 Milky adapter 源码建立媒体入口矩阵，验证正式入口、继承入口、兼容桥和删除别名的所有权关系
- [x] 1.2 建立普通图片、远程图片、本地图片、GIF、语音、视频和文档的合成出站 fixture，验证 fixture 不含真实身份、凭证、敏感正文、真实路径或完整媒体内容
- [x] 1.3 建立 adapter 方法解析和断开门禁测试，验证本地图片兼容桥仍可用、删除的插件覆盖不被调用、未连接时不读取资源或访问网络

## 2. Adapter 与 sender 接口重构

- [x] 2.1 删除 outbound sender 的 `send_animation()`、`send_image_file()` 和 `send_file()` 重复实现，迁移内部调用到正式路径，并通过 sender 定向测试验证请求次数与结果分类不变
- [x] 2.2 将 adapter 的 `send_image_file()` 收敛为直接复用普通图片发送的 Hermes 兼容桥，删除 adapter 自定义 `send_animation()` 与 `send_file()`，并通过方法解析和委托测试
- [x] 2.3 保持 `send_multiple_images()` 由 Hermes 基类负责，验证插件不复制批量 pacing、GIF 分流、caption 顺序和逐项失败隔离
- [x] 2.4 保持 `send_image()`、`send_voice()`、`send_video()`、`send_document()` 的既有签名兼容性、materialization、group/dm 路由和文件独立 upload，并通过相关单元测试

## 3. 回归与边界验证

- [x] 3.1 用当前 Hermes 基类真实 dispatch 验证本地图片、GIF URI 和普通远程图片的入口解析，无法加载宿主时记录测试基础设施原因，不伪造通过证据
- [x] 3.2 验证 `MEDIA:<path>` 的本地图片、语音、视频和文档分别进入正确 native/upload 边界，用户可见内容不包含路径，且每个可能产生副作用的 Action 最多调用一次
- [x] 3.3 验证普通 `send()` 的文本、结构化 segment、CQ parser 和既有 `image.sub_type` 行为未被接口重构改变，不新增 CQ 资源 materialization 行为
- [x] 3.4 验证 group/dm 路由、临时/非法目标、协议拒绝、transport_unknown、malformed、取消和群失败刷新行为不回归
- [x] 3.5 全仓检索并清理插件内部对已删除 sender `send_animation()`/`send_image_file()`/`send_file()` 的直接调用，验证只保留 adapter 的 Hermes 兼容桥

## 4. 质量门禁与交付证据

- [x] 4.1 运行多媒体、sender、adapter 生命周期、Hermes dispatch 和相关回归测试，并记录失败属于协议字段/路径、Hermes API、媒体资源、并发顺序、权限安全或测试基础设施哪一类
- [x] 4.2 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build` 和 `git diff --check`，将真实结果写入本台账，不把未执行命令标记为通过
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`，验证本 change 的纯重构标记和既有规范一致
- [x] 4.4 仅在取得独立明确授权后运行真实 Milky 写入/上传 smoke；否则记录未执行原因，并确认 fake transport 已覆盖普通图片、媒体 segment、文件 upload 和未知结果边界

## Evidence ledger

| 阶段 | 命令/证据 | 结果 | 反馈分类与下一步 |
|---|---|---|---|
| 规划 | 已读取 `AGENTS.md`、`ARCHITECTURE.md`、既有多媒体/模型控制 change artifacts、Hermes `BasePlatformAdapter` 媒体 dispatch 源码及本 change 的 proposal/design | 已完成 | 范围收敛为插件接口精简和委托重构；不改变 CQ parser、`image.sub_type` 或资源 materialization 语义 |
| fixture/实现 | `uv run pytest tests/test_multimedia_outbound.py tests/test_milky_local_integration.py -q`；`uv run ruff check ...` | 通过；定向多媒体测试覆盖合成 URI、入口矩阵、图片/语音/视频 native segment、文档 upload、断开门禁和错误分类 | 已删除 sender 重复入口；adapter 仅保留 `send_image_file()` 到 `send_image()` 的 Hermes 兼容桥；无 CQ 代码或 fixture 行为变更 |
| 回归 | `uv run pytest tests/test_cq_formatter.py tests/test_outbound.py tests/test_unknown_send_outcomes.py tests/test_adapter_lifecycle.py tests/test_milky_local_integration.py tests/test_multimedia_outbound.py -q`；Hermes 3.13 host 基类 dispatch 复核 | 134 passed, 17 skipped；host 复核通过。默认插件环境的 host dispatch 测试按基础设施缺失跳过 | 失败分类无协议字段/路径、媒体资源或权限安全回归；默认环境 host 不在 import path 时保留明确 skip，不伪造通过 |
| 质量门禁 | `uv run ruff check .`；`uv run ruff format --check .`；`uv build`；`git diff --check`；`npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；`uv run pytest -q` | Ruff、format、build、diff 和 OpenSpec 均通过；全仓 pytest 为 462 passed, 22 skipped, 1 failed | 唯一失败分类为既有测试/skill 文案不一致：`tests/test_plugin_entry.py` 期待 `skills/qq-tools/SKILL.md` 含“文字说明不注册”，该文件未在本 change 修改；未将全仓 pytest 宣称为通过 |
| 真实环境 | 未执行真实 Milky Action | 按当前授权边界跳过；本地 HTTP fake 与 fake client 已覆盖普通图片、媒体 segment、独立文件 upload、单次调用和未知结果 | 未取得独立明确授权，不执行真实 Milky 写入或上传；CQ 资源 materialization 保持为后续独立 change |
