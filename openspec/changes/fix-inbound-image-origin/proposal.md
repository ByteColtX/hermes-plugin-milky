# Proposal

## Why

群聊刷屏时，一次 trigger 的上下文里可能包含来自多条消息的图片：历史消息各自的
`[img:file_name=<basename>]` 占位符留在各自正文中，而 Hermes 只按 `media_urls` 的顺序把
内联图片交给模型。两者没有显式对应关系，模型只能靠文件名猜测哪张图属于哪条消息。

线上可复现的三种错位：同一张图被多人转发（去重后附件数少于占位符数）、抓取失败
（`[img:file_name=NOT SUPPORTED]` 既无文件名也无附件）、一条消息含多张图（只能按顺序猜）。

## What Changes

- 历史上下文正文含 image placeholder 且该消息有稳定 `message_seq` 时，在该条历史记录正文后
  追加独立的 `[images_from_msg_seq=<message_seq>]` 行。
- 该标记只使用消息自身的 `message_seq`；没有 placeholder 或序号缺失时不追加。
- image placeholder 语法保持不变（`message-segments` 规范已锁定），`media_urls` 的顺序与去重
  语义不变。
- 当前 trigger 消息不需要该标记：它本身带有 `msg_seq` 消息头，图片天然归属该消息。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `message-segments`：新增历史图片占位符的来源消息序号标记及其适用条件。

## Impact

- 影响 `inbound/pipeline.py` 的历史渲染路径与 `openspec/specs/message-segments`。
- 不修改 Hermes core、出站、`media_urls` 顺序、去重或图片 hash 语义。
- 不引入路径、URL、token 或新的占位符语法。
