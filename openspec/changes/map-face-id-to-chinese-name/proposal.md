## Why

当前入站 `face` segment 的正文占位符只显示协议中的 `face_id`，模型难以直接理解该表情的含义。项目已有 `milky/face_catalog.json` 提供 `qSid` 到 `qDes` 的本地目录数据，现在应在无网络的规范化阶段利用该目录改善可读性，并在目录缺失或无法匹配时保留原有 ID 信息。

## What Changes

- 加载并校验 `milky/face_catalog.json`，建立 `qSid` 到中文表情名称的本地映射。
- 将入站 `face` 的正文占位符从 `[face:<face_id>]` 改为使用目录中的中文名称；名称不可用或 ID 未匹配时回退为原 `face_id`。
- 保留现有 placeholder 的顺序、格式、缺失 ID 的 `NOT SUPPORTED` 降级和 `face` segment 的 typed 语义。
- `packName` 不参与名称选择或额外转换，包括 `emoji 表情`；模型可直接读取这些表情目录项的名称。
- 增加目录加载、命中、未命中、异常数据和复合消息顺序的脱敏测试与契约 fixture。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `message-segments`: 入站 `face` placeholder 使用本地 catalog 的中文名称，并定义安全回退和目录失败行为。

## Impact

- 影响 `inbound/extractor.py` 的入站正文生成，以及新增的本地 catalog 读取/解析边界。
- 影响 `tests/test_normalizer.py`、入站上下文渲染测试和相关协议 fixture；不会改变出站 `face` segment、Milky Action、SSE、Will 或网络请求。
- 运行时仅读取随插件发布的 `milky/face_catalog.json`；目录不可用时必须保持可解释的旧 ID/`NOT SUPPORTED` 降级，不引入远程依赖。
