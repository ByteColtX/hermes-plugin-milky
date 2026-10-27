# Design

## 现状

`inbound/pipeline.py::_render_resolved_history` 把历史消息渲染成 `<sender uid ... msg_seq ...> 正文`
的连续文本，交给 Hermes 作为 `channel_context`；`inbound/hermes_mapper.py` 再把
`context_image_materializations` 与当前消息的附件合并成 `media_urls`。

Hermes 侧只按 `media_urls` 的顺序生成 `[Image attached at: <path>]`，不带消息归属。正文里的
`[img:file_name=<basename>]` 分散在各条历史消息中，两条列表之间没有显式对应。

## 决策

在含 image placeholder 的历史记录正文后追加 `[images_from_msg_seq=<message_seq>]`。

理由：

1. **不改占位符语法**。`message-segments` 规范要求 image placeholder 为
   `[img:file_name=<basename>]` 且 basename 必须与 `media_urls` 一致；改语法会破坏既有契约
   和全部相关测试。
2. **来源信息由插件唯一持有**。`media_urls` 是扁平列表，Hermes 不携带来源；只有插件知道
   哪个 occurrence 来自哪条 canonical 消息。
3. **可逆、低风险**。标记是独立行，不进入 `media_urls`，不影响去重与 hash 代表选择。

## 边界

- 只在 `message_seq` 是稳定字符串时追加；缺失时保持原正文，不猜测序号。
- 只在正文含 `[img:file_name=` 时追加，纯文本历史不产生噪声。
- 当前 trigger 消息不追加：它的正文已经带 `<... msg_seq ...>` 消息头。

## 备选方案

- **在占位符里加序号**（如 `[img:1:file_name=...]`）：违反 `message-segments` 现有契约，且
  需要同步 mapper、resolver、全部 fixture 与规范，收益不抵成本。
- **在 `metadata` 里传映射**：模型看不到 `MessageEvent.metadata`，无法据此对齐。
- **修改 Hermes core 输出带来源的附件说明**：超出本仓库边界，且线上 core 版本不可控。

## 风险

- [风险] 标记增加少量 prompt 体积。→ 仅在含图片的历史消息上出现，单行且不含路径。
- [风险] 模型可能把标记当成可复用语法。→ 平台提示已声明「消息头是 metadata，不要复制进回复」，
  该标记同样属于 metadata 行。
