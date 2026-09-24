# Proposal

## Why

Milky 当前依赖环境配置和命令维护表情包，复杂 Will 策略、图片筛选与批量修正缺少直观入口。利用 Hermes core 已提供的 Dashboard 扩展和配置机制，可在同一宿主内完成配置、上传、预览与维护，并让保存来源、任务结果和运行生效状态可核实。

## What Changes

- 新增宿主原生发现的 Milky QQ Dashboard 页面及受宿主保护的插件 API，复用宿主组件、主题与认证请求能力；首次未配置或配置错误时仍能访问配置页。
- 普通配置写入插件 settings，读取遵循 settings → legacy config → 当前 profile 的 MILKY_* → 内置默认值；凭证继续由 core 管理。保留旧环境部署，显式值非法时拒绝而非静默回退，界面区分有效来源、保存结果与待重启状态。
- 声明与运行时一致的配置 schema，提供结构化 Will 编辑、完整候选校验和凭证替换；消除仅凭环境变量判断配置完整的旧发现条件，使 YAML 中的有效地址也能启动。
- 增加表情包分页筛选、认证图片预览、字段来源展示、单项和批量编辑、删除、重新分析，以及清理预览和索引修复。
- 支持浏览器上传到受控暂存区，复用现有图片校验、去重、辅助视觉分析和入库语义；上传批次只处理明确提交的文件，不顺带导入其他 inbox 内容。
- 为长操作提供有界维护任务、逐项结果、重复提交保护和中断可辨识状态；协调 Dashboard 与命令维护、发送之间的文件和存储一致性。
- 明确 profile 隔离、宿主停用后的访问限制、资源释放和隐私边界；图片预览作为认证媒体响应交付，不进入日志或命令/任务摘要。
- 不引入独立 Web 服务、第二套登录、任意 QQ Action 控制台、Web 试发、自动收藏或消息触发维护，不修改 Hermes core；本次不承诺配置热更新或原生 Desktop 专属页面。

## Capabilities

### New Capabilities

- `milky-web-dashboard`: 定义 Dashboard 发现、认证与 profile 归属、配置编辑、图库上传/浏览/预览、批量操作和维护任务的用户可见行为。

### Modified Capabilities

- `configuration`: 从仅环境启动配置扩展为 core 插件设置优先、旧环境回退和独立凭证来源；对齐 manifest、启动校验及配置来源展示。
- `plugin-lifecycle`: 明确唯一平台注册入口与宿主声明式 Dashboard 扩展的关系，保持导入无副作用，隔离维护任务与 QQ 连接生命周期。
- `qq-sticker-maintenance`: 在保留原维护命令语义的前提下补充显式 Web 维护入口、受控上传/预览例外与跨进程一致性。

## Impact

- 影响插件 manifest、配置层、根平台注册、表情包维护/存储边界及相关测试；新增 Dashboard 资源、后端适配与前端构建/交付检查。前端运行使用宿主提供的能力，开发构建依赖独立锁定，普通 Gateway 加载不引入 Web 依赖或后台任务。
- 普通设置与凭证使用 core 的 profile 和托管策略；图库及任务属于同一 profile 的插件持久目录，不复制 Hermes 会话或入站资源存储。
- 同步 README、ARCHITECTURE、相关主规范的 delta 和实施证据；现有声明“只有环境配置”“唯一公开入口”需按本 change 明确修订，不能留下文档与行为冲突。
- 基于 Hermes core `b3a1900e72a16da450ff637aaa37cc23f68992a6` 的文档与源码核对，Dashboard SDK、独立发现、认证请求、插件设置和持久存储接口存在；当前实现的真实宿主、profile 切换、任务关闭、代理前缀和视觉导入证据记录在 `evidence.md`，最低发行版本仍待映射。
- 依赖当前已实现的人工共享图库，不依赖 `add-qq-sticker-library` 的自动收藏/会话隔离规划，也不合入 `redesign-sticker-search-fallback`；`add-sticker-search-and-id-send` 的未完成真实集成证据仍独立保留。本目录仍是未归档 change；Dashboard 实现和证据已在当前工作树中，主规范同步仍按归档流程处理。
