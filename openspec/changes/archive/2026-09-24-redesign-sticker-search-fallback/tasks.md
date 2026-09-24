# Tasks

## 1. 搜索契约和结果语义

- [x] 1.1 增加 `strict`、`fallback`、`browse` 请求模式及默认推断，校验字段、枚举、长度、重复值、模式条件和未知字段；用 parser/schema 测试验证非法输入在库访问前失败。
- [x] 1.2 实现严格搜索、显式放宽 intent 和显式浏览；验证 strict 零命中不自动兜底、fallback 保留 emotion/tags、browse 稳定有界，并覆盖空库和无命中。
- [x] 1.3 让严格发送无匹配回执携带最多 5 个 fallback 备选，并修改结果序列化以保留该字段；用工具级测试验证无匹配不调用 Action、不更新统计且不隐式选图。
- [x] 1.4 保持 `sticker_send(sticker_id)` 精确发送；用工具级测试验证只有 Agent 显式提供 ID 才会尝试发送。

## 2. 排序、元数据和副作用边界

- [x] 2.1 保留严格相关性排序，为 fallback 使用 tag 命中数和稳定 ID 排序，为 browse 使用稳定 ID 排序；用重复调用测试验证顺序、数量上限和去重。
- [x] 2.2 限制搜索结果和发送备选只包含各自规定的状态字段及白名单元数据，并过滤缺失文件、无效索引和越界字段；用字段审计测试验证不泄露路径、URL、hash、图片内容、统计、轮换历史或匹配解释。
- [x] 2.3 验证搜索只读和当前会话边界：不创建、迁移、修复或写入存储，不改变发送统计，不调用 Milky/视觉服务；用只读库、统计快照、非法上下文、服务解绑和生命周期 fixture/fake host 测试验证固定错误分类。
- [x] 2.4 保持日志安全边界、固定错误分类和不确定 Action 结果不重试边界；用日志断言及 Action 调用次数测试验证不记录敏感参数且每次调用最多执行一次 Action。

## 3. 文档和变更证据

- [x] 3.1 同步 README、ARCHITECTURE、QQ bundled skill 和工具定义说明，仅描述通用接口、模式差异、no_match 备选、显式 ID 发送和结果语义，将使用时机与调用策略留给用户配置；用全文检索清除过期或矛盾描述。
- [x] 3.2 更新本 change 的 evidence，分别记录合成库/fake host 通过项、真实 Hermes 工具发现状态和真实 Milky 写入授权状态；未获得真实环境或授权时标记 blocked/未验证，不把本地测试写成集成成功。

## 4. 验证与集成边界

- [x] 4.1 运行贴纸、出站工具、生命周期和新增搜索测试，验证 strict/fallback/browse、no_match alternatives、空库、ID 发送、失败终态和只读统计边界；记录通过与 skip 的具体原因。
- [x] 4.2 运行 `uv run ruff check .`、`uv run ruff format --check .`、`git diff --check`、`openspec validate --changes --strict` 和 `uv build`，确认代码、格式、OpenSpec 和构建门禁通过。
- [x] 4.3 在可用真实 Hermes 宿主中验证新 Tool definition、三种搜索模式、`no_match` 备选结果交付和新会话重新发现；证据必须与 fake host 分开，缺少宿主时保留 blocked/未验证。
- [ ] 4.4 在获得明确目标授权后验证一次真实 Milky ID 发送，并确认搜索兜底本身不发送；未获授权或环境不可用时保持未完成并说明阻塞，不报告真实发送成功。
