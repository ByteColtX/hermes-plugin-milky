## Why

当前 Milky adapter 和 outbound sender 同时暴露多个 Hermes 媒体入口，其中部分只是重复委托
或旧式别名，容易把 Hermes 的宿主兼容契约、Milky 消息 segment 和文件 upload 混为一谈。
需要在不改变现有出站行为的前提下收敛插件自有实现。

## What Changes

- 删除 Milky adapter 和 outbound sender 自定义的 `send_animation()` 实现；动画继续由 Hermes
  基类语义入口转发到普通 `send_image()`，Milky wire 层仍使用 `image` segment。
- 删除 `send_file()` 旧式兼容别名；普通文件统一使用正式的 `send_document()`，并继续走独立
  `upload_group_file` / `upload_private_file` Action。
- 保留 adapter 层的 `send_image_file()` 作为 Hermes `send_multiple_images()` 本地图片路径
  dispatch 所需的薄兼容桥，但删除 outbound sender 中重复的同名实现，让桥直接复用图片发送路径。
- 保持 `send_multiple_images()` 由 Hermes 基类负责批量编排，不把单图 `send_image()` 改造成多图
  API，也不在插件中复制批量 pacing、GIF 分流和逐项失败隔离。
- 补充接口解析、宿主媒体 dispatch、group/dm 路由、文件 upload、错误分类和资源安全回归，
  确认重构不改变可观察的出站行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。本 change 只重构插件内部委托和兼容层，不改变规范级行为。

## Impact

- 影响 `adapter.py`、`outbound/sender.py` 及相关单元/集成测试；文档只需记录接口所有权变化。
- 不修改 Hermes core；不能删除 Hermes 基类的 `send_multiple_images()`、`send_animation()`
  或 `send_image_file()`，只能删除插件不必要的覆盖实现。
- 不改变 Milky HTTP Action、Bearer 认证、媒体 materialization、group/dm 路由、
  文件独立 upload、SendResult 错误分类或未知结果不重试边界。
- 不新增 Agent-callable 媒体工具，也不在本 change 中改变 CQ-compatible 语法或资源处理行为。
