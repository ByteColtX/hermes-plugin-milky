# Evidence ledger

记录日期：2026-09-04（Asia/Shanghai）

## 契约与边界

- 当前公开 Milky v1.3 文档未列出 `get_friend_info`；本 change 未把昵称、性别、备注或其他
  未确认字段加入 `FriendEntity`、parser 或好友资料 DTO。
- `get_friend_info` 仅以 `user_id` 作为请求字段，成功只接受非空 JSON object `data`，保留
  完整 envelope 和未知字段；目标服务未确认或不支持时不伪造成功，按 `http_error`、`rejected`
  或 `malformed` 等实际边界返回。
- `set_group_member_special_title` 只接受 `group_id`、`user_id`、`special_title`，空字符串
  原样发送；成功只接受空 object，结果未知不重试且不更新本地群成员状态。

## 已执行

- `uv run pytest -q tests/test_qq_tools.py tests/test_milky_client.py tests/test_config.py tests/test_plugin_entry.py`：通过，221 passed。
- `uv run pytest -q`：通过，721 passed，2 skipped；首次全量运行的 2 个失败是既有 23 项注册
  清单断言，已更新为 25 项后回归通过。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：通过，260 files already formatted。
- `uv build`：通过，生成 source distribution 和 wheel。
- `git diff --check`：通过。
- `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`：通过，5 passed、0 failed；
  输出仅包含其他 active change 的既有 archive 信息提示。
- synthetic `get_friend_info` fixture 测试覆盖 object data、未知 envelope/data 字段、协议拒绝、
  null/array malformed、HTTP 404 错误和 `transport_unknown`，且检查不含凭证、Authorization、
  可访问 URL、路径或完整敏感文本。
- 两个新增工具的 client、sender 和 registered handler 测试覆盖精确 path、单次 POST、精确
  body、空 `special_title`、非法参数网络前拒绝和成功 envelope 保留。
- 新增工具安全日志测试确认好友资料值和完整 `special_title` 不进入日志；群通知和普通事件
  保持 observe-only，不自动提交专属头衔 Action。

## 未覆盖与 skip

- 未执行真实 Milky/Hermes host 连接；`get_friend_info` 的目标服务 operation 契约和真实响应
  字段仍未确认，因此不执行真实只读 smoke。
- 未执行 `set_group_member_special_title` 真实写入 smoke；该操作有远端副作用，必须等待明确
  授权、运行时 `MILKY_ALLOWED_CHATS` 命中和目标服务契约。
- 未执行真实 `get_friend_info` 只读 smoke；当前未获得目标服务 operation 契约，公开文档未列出
  该 operation，fake transport 证据不能替代真实服务确认。
