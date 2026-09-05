---
name: milky-qq-cq-reference
description: Reference for Milky QQ Agent's CQ-compatible at, reply, face, and local sticker image syntax, including face ID to Chinese-name lookup. Use when composing or explaining outbound QQ messages or interpreting Milky face placeholders; do not use as a OneBot v11 or arbitrary Action reference.
metadata:
  short-description: Milky QQ CQ 消息格式与表情映射
  keywords: "Milky, QQ, CQ, at, reply, face, 表情, 中文名称, sticker"
---

# Milky QQ CQ message reference

本 skill 只覆盖 Milky QQ Agent 的 CQ-compatible `at`、`reply`、`face`、本地贴纸图片语法和
入站 `face` 名称显示。它不是 OneBot v11 协议或 Milky Action 清单。

## 通用约束

- `at` 的 `uid`、`reply` 的 `msg_id`：使用当前消息或 `channel_context` 消息头中的真实值。
- `face_id`：使用当前消息、`channel_context` 或用户明确提供的真实值。
- ID 必须是无前导零的十进制值；不要从昵称、群名、正文、时间戳、随机数或其他字段推断。
- 缺少可靠 ID 时不要自动 @、引用或发送 face；`at` 不支持 `qq=all`。

## at

`[CQ:at,qq=<uid>]`

`qq` 填真实 `uid`，不能填昵称、群名或其他显示文本。

## reply

`[CQ:reply,id=<msg_id>]`

`id` 填消息头中的原始 `msg_id`；缺失或不可转为数字时不要调用，也不会自动引用当前消息。

## face

普通表情：`[CQ:face,id=<face_id>]`

超级表情：`[CQ:face,id=<超级表情face_id>,large=1]`

`large` 可省略；只有“超级表情”条目的 `face_id` 才能使用 `large=1`，其他表情省略或使用
`large=0`。`large=1` 表示协议类型，不是通用放大开关；`478 /对的对的` 虽也在“QQ黄脸”中，
但同时属于超级表情。

常用 face ID（名称保留 catalog 原值，包括前导 `/`）：

| face ID | 中文名称 | 备注 |
| ---: | --- | --- |
| 14 | /微笑 | 现代聊天中常用于阴阳、讽刺或表达不满，可能带攻击性；不要按字面理解为友善微笑。 |
| 22 | /白眼 | 常表达不耐烦、无语或轻微鄙视，仍需结合上下文。 |
| 318 | /崇拜 | — |
| 395 | /略略略 | — |
| 319 | /比心 | — |
| 311 | /打call | — |
| 324 | /吃糖 | — |
| 480 | /散味儿 | 梗：你很臭喵。通常表示嫌弃 |
| 325 | /惊吓 | — |
| 478 | /对的对的 | — |
| 479 | /不对不对 | — |
| 484 | /比爱心 | — |
| 384 | /晚安 | — |
| 386 | /呜呜呜 | — |
| 403 | /出去玩 | — |

完整目录见 [references/face-id-to-chinese-name.md](references/face-id-to-chinese-name.md)

### 关于 context 中的标签

本地 catalog 只将非 `emoji 表情` pack 的 `qSid` 映射为原始 `qDes`，用于理解
`[face:<名称>]`；emoji pack 保留原始 `face_id`。未命中、目录不可用或映射冲突时回退
`face_id`，缺少 ID 时使用 `NOT SUPPORTED`。该映射不提供名称反查，不改变出站 typed 字段，也不
授权发送。

## image

单独发送本地贴纸（sticker）：

`[CQ:image,file=file:///path/to/sticker.ext,type=sticker]`

`image` CQ 码不得与正文或其他 CQ 码混合。普通图片使用 `MEDIA:<local_path>`，不要使用 CQ `image`。

## 组合与 fallback

`at`、`reply`、`face` 可组合并保持顺序：

`[CQ:reply,id=9001][CQ:at,qq=10001]正文`

支持的 CQ 转换失败时，只将该片段原样保留为 text；格式错误或其他 CQ 片段不会因此获得额外
能力。可能产生副作用的操作仍以实际注册的 Hermes ToolSpec 和发送入口为准。
