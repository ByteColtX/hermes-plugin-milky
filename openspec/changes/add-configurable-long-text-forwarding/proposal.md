## Why

当前超长文本按多个普通消息发送，较长回复容易刷屏，也无法在用户侧作为一条可展开的合并转发查看。需要增加一个默认关闭、可在启动时配置的选择，让部署者在确认需要时将一次回复中的全部文本发送单元收纳到同一个 Milky `forward` segment 中，同时保持现有默认分块行为不变。

## What Changes

- 新增 `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 启动配置：默认 `0`；`0` 表示关闭；`1` 至 `4000` 的十进制整数表示启用阈值。
- 当配置为正数且本次规范化文本总长度超过阈值时，系统选择合并转发出站；未超过阈值或配置为 `0` 时继续使用当前普通文本发送路径。
- 合并转发选择一旦成立，本次原本会产生的每个文本发送单元（包括 `[SPLIT]` 逻辑段和既有长度分块）以及可由 Milky `OutgoingSegment` 表示的 native 图片、语音和视频，都必须按原顺序成为同一个 `forward` segment 内的节点；不得部分作为普通消息发送。
- 文档/文件不在本 change 范围内，不进入自动合并转发，继续沿用现有独立 file upload 行为。
- 合并转发节点使用已确认的 Bot 身份字段，完成首个消息 Action 前预检全部节点和结构；远端消息 Action 仍只调用一次。
- 配置值为空、非十进制整数、负数或大于 `4000` 时启动失败，不静默关闭或截断。

## Milky 协议入参与出参

群聊使用 `POST /api/send_group_message`，请求体为 `group_id` 与 `message`；私聊使用
`POST /api/send_private_message`，请求体为 `user_id` 与 `message`。两者的 `message` 都是
`OutgoingSegment[]`。自动合并转发时，顶层 `message` MUST 只包含一个 `forward` segment：

```json
{
  "group_id": "<confirmed_group_id>",
  "message": [
    {
      "type": "forward",
      "data": {
        "messages": [
          {
            "user_id": "<confirmed_self_id>",
            "sender_name": "<confirmed_nickname>",
            "segments": [
              {"type": "text", "data": {"text": "<text_chunk>"}}
            ]
          },
          {
            "user_id": "<confirmed_self_id>",
            "sender_name": "<confirmed_nickname>",
            "segments": [
              {"type": "image", "data": {"uri": "<validated_media_uri>"}}
            ]
          }
        ]
      }
    }
  ]
}
```

私聊请求将 `group_id` 替换为 `user_id`。每个 `forward.data.messages[]` 节点 MUST 包含
`user_id`、`sender_name` 和 `segments`；`segments` 可使用 Milky 已确认的 `text`、`mention`、
`mention_all`、`face`、`reply`、`image`、`record`、`video`、`forward`、`light_app`。`file`
不属于该集合，因此文档/文件不进入自动 forward；它们继续沿用现有独立 file upload 行为，不由本 change 改写。

成功响应使用标准 Milky envelope：`status=ok`、`retcode=0`，`data.message_seq` 是远端消息
序号，`data.time` 是服务端时间。插件将 `data.message_seq` 转为单一 `SendResult.message_id`，
不产生 continuation ID 或独立 `forward_id`。`get_login_info` 使用空对象 `{}` 请求，返回必填的
`data.uin` 和 `data.nickname`，仅用于确认 forward 节点身份。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `configuration`: 增加并校验超长文本合并转发阈值配置，并将其纳入启动配置摘要和配置文档。
- `outbound-messaging`: 定义文本发送单元收纳到单一 Milky `forward` segment 的路由、身份、预检和失败语义。
- `outbound-message-splitting`: 定义合并转发选择后 `[SPLIT]` 段和既有长度分块必须全部转为同一 forward 节点集合的语义。

## Impact

- 影响 `config` 启动配置、`outbound/sender.py` 的文本与 native media 组装、`outbound/formatter.py` 的 forward 节点交接，以及 adapter/standalone 的 Bot 身份传递。
- 影响相关配置、出站、分块和 fake/integration 测试，以及 `README.md`、`ARCHITECTURE.md` 和 Milky OpenSpec 主规范。
- 默认值为 `0`，因此未配置部署的普通文本、`[SPLIT]`、附件顺序和现有失败语义保持不变。
