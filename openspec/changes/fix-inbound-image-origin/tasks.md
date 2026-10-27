# Tasks

## 1. 实现

- [x] 1.1 在历史渲染路径为含 image placeholder 且有稳定 `message_seq` 的记录追加 `[images_from_msg_seq=<message_seq>]`；验证纯文本历史与缺失序号时不追加。
- [x] 1.2 保持 image placeholder 语法、`media_urls` 顺序与去重语义不变；验证既有资源与去重测试全部通过。

## 2. 测试

- [x] 2.1 新增历史图片来源标记的正向用例，断言标记位于该条正文的 placeholder 之后。
- [x] 2.2 新增无图片历史不产生标记的用例。
- [x] 2.3 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`。

## 3. 文档

- [x] 3.1 更新 `openspec/specs/message-segments` 与 `CHANGELOG.md`。

## 4. 真实环境

- [ ] 4.1 在 `hermes-dev` 验证群聊多图消息的模型输出能正确指认图片来源；在此之前不宣称线上已验证。

## Workflow follow-up

- 运行 `openspec validate --changes --strict`。
- 通过审阅后再归档该 change。
