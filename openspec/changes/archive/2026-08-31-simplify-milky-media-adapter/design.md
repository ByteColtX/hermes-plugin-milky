## Context

See `proposal.md` for the motivation and externally visible scope. 当前 Hermes 宿主的
`send_multiple_images()` 已经负责批量图片的 pacing、GIF 分流和逐项错误隔离：本地图片路径
调用 `send_image_file()`，动画 URI 调用 `send_animation()`，其他图片 URI 调用 `send_image()`。
Hermes 的 `MEDIA:<path>` 资源分流也直接调用图片、语音、视频和文档媒体入口。

当前 Milky 插件为了覆盖这些宿主入口，在 adapter 和 outbound sender 中重复实现了
`send_animation()`、`send_image_file()` 和 `send_file()`。其中 Milky wire 层没有独立的
animation segment，文件也已经有正式的 `send_document()` upload 路径。

## Goals / Non-Goals

**Goals:**

- 收敛插件自有媒体实现，保留 Hermes 实际调用所需的最小 adapter 边界。
- 保持 Agent 资源的既有 `MEDIA:<path>`、Markdown 图片和结构化消息输入语义不变。
- 保持 Milky 的 image/record/video message segment、文件独立 upload、错误分类和单次 Action
  约束不变。

**Non-Goals:**

- 不修改 Hermes core，也不删除 Hermes 基类的 `send_multiple_images()`、`send_animation()` 或
  `send_image_file()`。
- 不把 `send_image()` 改成多图片批量 API，不复制 Hermes 的批量调度逻辑。
- 不把 `MEDIA:<path>` 资源强制改写成 CQ 码，不新增 Agent-callable 媒体工具，也不改变 CQ
  compatible 语法。
- 不为 Milky 发明独立的 animation wire segment，不根据 GIF 扩展名改变图片语义。
- 不改变文件必须走 `upload_group_file` / `upload_private_file` 的协议边界。

## Decisions

### 1. 保留宿主兼容桥，删除插件重复入口

adapter 保留 `send()`、`send_image()`、`send_image_file()`、`send_voice()`、`send_video()` 和
`send_document()`。其中 `send_image_file()` 只接受 Hermes 的本地图片路径并直接复用
`send_image()` 的图片 materialization，不在 sender 中保留同名重复实现；这样 Hermes 基类的
本地图片分支仍能进入 Milky native image segment。

删除 Milky adapter 和 sender 自定义的 `send_animation()`。Hermes 基类默认实现会把动画语义
转交给 `send_image()`，而 Milky 继续生成 `image` segment。删除 adapter 和 sender 的
`send_file()`，文件统一从正式的 `send_document()` 进入独立 upload。

保留 `send_multiple_images()` 的宿主实现，不在插件中覆盖。这样单图入口、批量入口和
`MEDIA:<path>` 分流的所有权仍然清晰，且不会因合并为一次多图发送而丢失单项 caption、GIF
判断、pacing 或部分失败结果。

### 2. 维持两条 Milky wire boundary

图片、语音和视频继续使用 `send_group_message` / `send_private_message`，分别生成 `image`、
`record` 和 `video` segment。普通文件和文档继续使用对应的独立 upload Action，不进入
message segment。入口收缩不改变任何远端 Action、远端结果 ID 或失败分类。

### 3. 用宿主 dispatch 和结构化 fixture 验证边界

测试应从 Hermes 实际媒体 dispatch 入口验证：本地图片仍经兼容桥进入 image segment，动画仍
经宿主默认逻辑落到 image，文档只进入 upload。另用 sender fixture 验证本地路径、远程 URI、
文件上传和既有错误边界。
所有失败场景必须在网络访问前拒绝或保留原始安全错误，不得触发文本 fallback、重复 Action
或敏感路径输出。

## Risks / Trade-offs

- [宿主基类仍暴露已删除的 `send_animation()` 和 `send_image_file()` 名称] → 这是刻意保留的
  宿主兼容契约；只删除插件重复覆盖，文档区分“继承入口”和“插件自有实现”。
- [删除 `send_file()` 可能影响旧的插件内部调用方] → 全仓检索并迁移到 `send_document()`；
  不为没有宿主依据的旧别名继续扩大公开 API。
- [后续 CQ 资源处理 change 与本次接口重构混淆] → 本 change 不改变 CQ parser、image subtype
  或资源 materialization；相关行为单独规划和验证。
- [批量图片行为因接口收缩而回归] → 使用真实宿主基类 dispatch fixture 覆盖本地图片、GIF、
  普通远程图片、caption 顺序和逐项调用。

## Migration Plan

1. 先补充接口解析、既有媒体资源边界和删除自定义入口后的宿主 dispatch fixture。
2. 将 adapter 的本地图片入口改为薄桥，并移除 sender 的重复 `send_image_file()`、两处
   `send_animation()` 和两处 `send_file()` 实现。
3. 更新测试和必要的接口所有权说明；不修改 CQ parser、skill 或资源语义。
4. 运行定向媒体/formatter/adapter 集成测试，再运行 pytest、Ruff、format、build、diff 和
   OpenSpec strict validation。回滚时恢复插件覆盖实现即可，不改变 Hermes core 或远端协议。

## Open Questions

无。本 change 只涉及既有媒体入口的委托收敛和兼容层重构。
