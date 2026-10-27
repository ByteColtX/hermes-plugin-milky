# Tasks

## 1. 错误分类

- [x] 1.1 `ActionError` 增加固定 `reason_code`，在配置不可读、客户端已关闭、Action 未注册三处赋值；验证越界值被忽略。
- [x] 1.2 本地失败结果输出 `reason` 与 `retryable`，`retryable` 只在请求未进入网络时为 true；验证 sender 层不再把原因码折叠成默认值。
- [x] 1.3 全部固定 Action Tool 复用同一路径，逐个确认无独立错误构造分支。

## 2. 参数范围

- [x] 2.1 `send_profile_like` 的 `count` 在 handler、client 与参数校验层统一为 schema 声明的 `1..50`；验证 0、负数、51 在网络前失败，1 与 50 正常发出。

## 3. 技能登记

- [x] 3.1 bundled skill 登记时传入 SKILL.md frontmatter 的 `description`；验证宿主不支持时回退且不抛出。
- [x] 3.2 `register_skill` 缺失或文件缺失时记录固定告警，不再静默跳过。

## 4. 指引

- [x] 4.1 平台指引说明本地失败字段与远端原样响应的读取方式，并明确禁止自动重试有副作用的 Action。

## 5. 验证

- [x] 5.1 运行聚焦测试与全量 `uv run pytest -q`。
- [x] 5.2 运行 `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check`。
- [x] 5.3 运行 `openspec validate --changes --strict`。
- [x] 5.4 在 `hermes-dev` 实测配置不可读、客户端已关闭、远端业务拒绝和 `count` 越界四种结果可区分；确认真实宿主 skill registry 中的两个 bundled skill 已带 frontmatter 描述。
