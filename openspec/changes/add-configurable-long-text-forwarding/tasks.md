## 1. 配置契约与生命周期接入

- [x] 1.1 在启动配置模型中增加 `MILKY_LONG_TEXT_FORWARD_THRESHOLD`，实现默认 `0`、`0..4096` 十进制整数校验、错误分类和安全配置摘要，并用配置单测覆盖缺省值、`0`、`1`、`4096`、空值、负数、非数字和越界值
- [x] 1.2 将该配置接入 live adapter、standalone sender 和 `plugin.yaml`/配置文档，验证未配置时 sender 行为与现有版本一致且启动阶段不会提前建立额外网络连接
- [x] 1.3 为 live adapter 复用连接初始同步确认的 Bot `self_id`/昵称，为 standalone 在阈值触发时使用 `get_login_info` 的 `{}` 请求读取身份；真实身份缺失、协议拒绝、timeout、malformed、传输未知或昵称为空/含控制字符时 fallback 到固定 `user_id=10001`、`sender_name=QQ用户`，并用测试验证普通消息不增加身份请求

## 2. Forward 节点组装与发送

- [x] 2.1 增加按可见规范化文本长度选择普通路径或 forward 路径的组装逻辑，验证阈值严格大于判断、`[[SPLIT]]` 计入可见长度、有效 `[SPLIT]` 标记和空段不计入长度
- [x] 2.2 让 forward 路径保留全部非空 `[SPLIT]` 逻辑段，不应用普通路径的三条顶层限制，并按既有安全边界将每个逻辑段拆成有序文本节点；验证超过三个逻辑段不会尾部合并且所有节点内容可逆拼接
- [x] 2.3 将文本节点和 native `image`/`record`/`video` segment 转换为真实或固定 fallback 身份的 Milky `forward.messages`，复用 CQ-compatible segment 转换和嵌套校验，验证 fallback 只使用 `10001`/`QQ用户`，不从正文、forward ID 或异常正文推断身份，也不伪造 `time` 等字段
- [x] 2.4 扩展 forward 节点的出站物化和本地预检，验证 nested image/record/video 遵守既有本地文件大小、读取次数和 URI 边界；文档/文件不构造成 forward segment，继续走现有独立 upload，任一 forward 节点失败时不发起消息 Action
- [x] 2.5 让 forward 选择只产生一个目标消息 Action并返回单一远端 `data.message_seq` 对应的 `message_id`，验证 group/dm 请求体、`forward.messages` 必填字段、成功 envelope、协议拒绝、transport unknown、timeout 和 malformed 结果均不自动 fallback 或重试

## 3. 回归与集成测试

- [x] 3.1 增加 forward request fixture 和 sender 单测，覆盖普通超长文本、阈值边界、关闭配置、多个 `[SPLIT]`、超过三段、4096 字符分块、CQ segment、确认身份、固定 fallback 身份和内容顺序
- [x] 3.2 增加 fake adapter/standalone 集成测试，验证有序批次中的文本和 native media 全部进入同一 forward、`get_login_info({})` 成功时复用真实身份、身份失败时使用 `10001`/`QQ用户`、文档/文件不进入 forward 且继续走现有独立 upload，以及 forward 预检失败时没有部分发送；若 Hermes 只提供分离的 `MEDIA:` 调用，验证系统记录前置能力边界而不猜测合并
- [x] 3.3 保留并回归现有普通分块、普通 `[SPLIT]` 三条预检、部分成功结果、群禁言刷新和私聊失败不查询群状态的测试，验证阈值为 `0` 时行为不变

## 4. 文档与质量门禁

- [x] 4.1 更新 `README.md`、`ARCHITECTURE.md` 和插件 manifest，说明配置范围、默认关闭、严格大于阈值、`send_*_message`/`forward.messages` 入参、确认身份失败时固定 fallback 为 `10001`/`QQ用户`、`data.message_seq` 出参、native media 与文档/文件（本 change 非目标、继续独立 upload）边界和回滚方式，并核对文档没有宣称未验证的服务端总大小上限
- [x] 4.2 运行 `uv run pytest -q tests/test_config.py tests/test_outbound.py tests/test_outbound_splitting.py tests/test_unknown_send_outcomes.py`，确认聚焦测试通过
- [x] 4.3 运行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.12.0 validate --changes --strict`，记录失败分类和必要回归修复
- [x] 4.4 在获得明确写入授权且配置命中运行时 allowlist 后，使用 `uv run scripts/milky_smoke.py` 做受控 forward smoke；未具备真实服务条件时记录 skip，不把 fake/fixture 结果当作真实协议通过
