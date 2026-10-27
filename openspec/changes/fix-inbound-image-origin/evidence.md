# Evidence ledger

## 根因

`inbound/hermes_mapper.py` 把历史 context 图片与当前消息图片合并成扁平 `media_urls`，按路径去重、
固定 context→current 顺序。正文里每张图仍是各自消息内的 `[img:file_name=<basename>]` 占位符，
两条列表之间没有显式对应。Hermes 侧只按 `media_urls` 顺序生成 `[Image attached at: <path>]`，
不携带来源消息。

线上上下文可见三种错位条件：同一 basename 在多条消息重复、抓取失败产生
`[img:file_name=NOT SUPPORTED]`、一条消息含多张图。

## 实现

`inbound/pipeline.py::_with_image_origin` 在历史渲染时，为含 `[img:file_name=` 且有稳定
`message_seq` 的记录追加独立行 `[images_from_msg_seq=<message_seq>]`。占位符语法、`media_urls`
顺序与去重、图片 hash 代表选择均未改动。

当前 trigger 消息不追加：它的正文已带 `<... msg_seq ...>` 消息头，图片天然归属该消息。

## Verification

- `uv run pytest -q tests/test_inbound_context_rendering.py -k "origin_marker or origin_message_seq"`：2 passed。
- `uv run pytest -q tests/test_hermes_pipeline.py tests/test_inbound_context_rendering.py tests/test_inbound_image_dedup.py tests/test_resources.py`：104 passed, 1 skipped。
- `uv run pytest -q`：1490 passed, 6 skipped。
- `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check`：通过。
- `uv run openspec validate fix-inbound-image-origin --type change --strict`：valid。
- `uv run openspec validate message-segments --type spec`：valid。

## Real environment

- 插件代码已部署到 `hermes-dev` 并重启网关，Milky 重新连接成功。
- 受控输入验证 `_render_resolved_history` 输出：
  - 带图历史：`<... msg_seq 1001> [img:file_name=a.jpg]\n[images_from_msg_seq=1001]`
  - 纯文本历史：`<... msg_seq 1002> 纯文本`（无标记）
- 真实群聊样本一：多条历史消息各带一张图，正文后各追加一条来源标记；纯文本与视频记录不追加。
  `media_urls` 顺序与历史顺序一致，模型据此正确指认两张图分别来自哪条消息。
- 真实群聊样本二：同一张图被多名成员连续转发，正文中多个占位符各自带来源序号，而
  `media_urls` 去重后只保留一个附件；模型仍能按来源序号区分各条转发。
- `sqlite3 quote()` 确认标记前是真实换行，不是字面 `\n`。
- 本文件与任务记录只保留合成序号（如 `1001`），不写入真实群号、QQ 号、消息序号、图片名或路径。

## Retained boundaries

- 图片占位符语法仍由 `message-segments` 规范固定，未扩展。
- `media_urls` 顺序、去重和 hash 代表语义未变。
- 不引入路径、URL、token 或新的可调用能力。
