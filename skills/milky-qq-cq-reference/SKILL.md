---
name: milky-qq-cq-reference
description: Reference for Milky QQ Agent's CQ-compatible at, reply, face, and local sticker image syntax, including face ID to Chinese-name lookup. Use when composing or explaining outbound QQ messages or interpreting Milky face placeholders; do not use as a OneBot v11 or arbitrary Action reference.
metadata:
  short-description: Milky QQ CQ 消息格式与表情映射
  keywords: "Milky, QQ, CQ, at, reply, face, 表情, 中文名称, sticker"
---

# Milky QQ CQ message reference

本 skill 只说明 Milky QQ Agent 出站可用的 CQ-compatible `at`、`reply`、`face` 和本地贴纸
图片语法，并提供入站 `face` placeholder 的中文名称索引。它不是 OneBot v11 协议，也不是
Milky Action 清单；不要据此调用 Action、猜测 ID 或扩大其他 CQ 类型的能力。

## at

`[CQ:at,qq=<uid>]`

- `qq` 必填，使用当前消息或 `channel_context` 消息头中的真实 `uid`。
- 填写真实的十进制 QQ 号；不支持 `qq=all`。不要把昵称、群名或其他显示文本当作 QQ 号。
- 没有真实 `uid` 时不要从昵称、正文或模糊描述猜测，也不要自动 @ 用户。

## reply

`[CQ:reply,id=<msg_id>]`

- `id` 必填，使用当前消息或 `channel_context` 消息头中的真实 `msg_id`。
- 使用消息头中的原始十进制消息序号；不要补前导零，也不要改用时间戳、随机数或其他消息字段。
- 没有真实且可转换为数字的 `msg_id` 时不要调用；不会自动引用当前消息。

## face

`[CQ:face,id=<face_id>]` 或 `[CQ:face,id=<超级表情face_id>,large=1]`

- `id` 必填，使用当前消息、`channel_context` 或用户明确提供的真实 face ID。当前 catalog
  中的 face ID 通常是小整数，例如 `14`；不要人为构造大数。
- `id` 需要是无前导零的十进制数值；不要把中文名称或 `[face:/微笑]` 直接填入 `id`。
- `large` 可省略；只有“超级表情”条目的 `face_id` 才能使用 `large=1`。其他表情省略该
  字段或使用 `large=0`；这里的 `large=1` 表示协议中的“超级表情”，不是通用放大开关。
- 当前 catalog 的“超级表情”共有 59 个条目；`478 /对的对的` 虽然也出现在“QQ黄脸”，但
  同时属于“超级表情”，因此可以使用 `large=1`。
- face ID 到中文名称的映射只用于理解入站正文中的 `[face:<名称>]`；它不提供由名称反查
  ID 的能力，也不改变出站 `face` segment 的 typed 字段。
- 没有来自当前消息、上下文或明确用户输入的可靠 ID 时，不要猜测或发送 face。

常用 face ID（名称按 catalog 的 `qDes` 原值保留，包括前导 `/`；备注只是语境提示，不能替代上下文判断）：

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

完整 `face_id → 中文名称` 目录见 [references/face-id-to-chinese-name.md](references/face-id-to-chinese-name.md)。
目录只提供可读名称，不授权发送；

## image

如需单独发送本地贴纸（sticker），使用如下 CQ 格式：

`[CQ:image,file=file:///path/to/sticker.ext,type=sticker]`

- `image` 类型的 CQ 码不得与正文或其他 CQ 码混合使用。
- 普通图片使用 `MEDIA:<local_path>` 方式发送，不要使用 CQ `image`。

## 组合与 fallback

`at`、`reply` 和 `face` 可以组合并保留顺序，例如：

`[CQ:reply,id=9001][CQ:at,qq=10001]正文`

当前支持的 CQ 转换失败时，只把该 CQ 片段原样作为 text；其他或格式错误的 CQ 片段不会在本
参考中获得额外能力。每个可能产生副作用的操作仍以实际注册的 Hermes ToolSpec 和发送入口为准。
