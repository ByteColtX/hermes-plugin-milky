# Dashboard 实施与验证证据

日期：2026-09-24。状态：30/30 实施任务验收完成，未归档；运行环境限制分别记录。
core：b3a1900e72a16da450ff637aaa37cc23f68992a6；Web SDK 1.1.0；
Python 3.13.5；FastAPI 0.141.1；Starlette 1.7.0；esbuild 0.25.10。

## 实现范围

- 原生配置逐键来源回退、非法高优先级拒绝、Will 整体选源；manifest secret 绑定和启动快照。
- 宿主用户插件 Dashboard 清单、源码、锁定依赖和预构建资源；认证 API 与显式 profile 作用域。
- 配置来源/可写性/版本读取、逐字段写回核验、独立凭证保持/替换/清除。
- 只读图库、认证预览、条目版本、跨进程目录锁与发送本地读取协调。
- 受控流式上传、独立候选批次、配额、活动任务引用与期限回收；复用既有视觉入库语义。
- 持久去重任务、队列限制、逐项进度、取消/关闭与恢复；同步视觉固定名额，迟到不提交。
- 配置、图库、维护任务页面；代理前缀与 profile 切换；README、ARCHITECTURE 更新。

## 真实宿主证据

1. scripts/dashboard_host_probe.py：合成用户插件，真实发现、认证、中间件、并发 profile、停用与 lifespan；全部通过。与当前插件测试分开记录。
2. scripts/dashboard_plugin_probe.py：真实当前 Milky 用户插件安装与路由；21 项检查通过：
   未配置读取、普通配置保存、旧版本拒绝、凭证替换/脱敏/空值保持/清除、profile 隔离、
   伪造范围拒绝、认证预览、未认证/其他 profile 预览拒绝、受控 multipart 流、
   无视觉重复导入、版本编辑、旧版本冲突、删除、清理计划、索引修复、批次丢弃、其他库保持为空。
   图库种子通过明确合成视觉 fixture 创建，未调用真实供应商。
3. 浏览器：真实宿主源码的隔离前端构建、临时用户插件 symlink、临时 default/alpha/beta。
   缺配置页面可访问；SDK 普通保存显示 saved/settings；合成凭证保存显示已配置；
   切换 alpha 显示独立空配置/空库；合成 PNG 上传 ready，导入任务 partial/visual_unavailable；
   维护页显示逐项结果。390×844 视口 document scrollWidth=390。
4. 本地反向代理传递 X-Forwarded-Prefix=/hermes：/hermes/milky 页面、插件资源与 SDK 配置请求正常。

宿主前端完整 npm run build 的 tsc 步骤存在源码依赖与类型错误（shared tests 的 vitest 解析及
vite preset.rolldown.filter 可空）；隔离副本中使用原 vite build 成功生成实际浏览器产物，
未修改 core。该结果不算宿主自身 TypeScript 门禁通过。

## 验证命令

- uv run pytest -q -rs：1092 passed，3 skipped。
- uv run ruff check .：通过。
- uv run ruff format --check .：通过。
- uv build：通过；wheel 不包含 directory plugin，不作为目录资源发布证据。
- npm run build --prefix dashboard、npm run check --prefix dashboard：通过。
- npm test --prefix dashboard：3 passed。
- git diff --check：通过。
- openspec validate --changes --strict：6 changes passed。

三个 skip 为 tests/test_adapter_lifecycle.py 与 tests/test_multimedia_outbound.py 缺少默认测试环境
Hermes host，以及 tests/test_hermes_prompt_integration.py 未设置 RUN_HERMES_INTEGRATION=1。
这些 skip 不算真实集成通过。额外的两个真实宿主脚本使用以下隔离依赖运行：

    uv run --with fastapi --with python-dotenv --with pyyaml --with uvicorn --with python-multipart --with rich --with typer --with psutil --with ruamel.yaml scripts/dashboard_host_probe.py --hermes-source <Hermes checkout>
    uv run --with fastapi --with python-dotenv --with pyyaml --with uvicorn --with python-multipart --with rich --with typer --with psutil --with ruamel.yaml scripts/dashboard_plugin_probe.py --hermes-source <Hermes checkout>

## 运行边界与证据限制

- 真实辅助视觉阻塞已于 Debian 集成解除；详见下节。最初临时 profile 的 visual_unavailable 保留为早期证据。
- 浏览器配置、Will、上传、预览、分页、批量维护、取消、重启已完成；托管/部分保存/expired
  展示采用响应故障注入，后端拒写、过期和部分失败分别由单元/API 验证，不称作真实托管服务故障。
- 专项异常/竞争矩阵已补齐：实际上传边界、配额竞争、移动失败、多引用删除、索引事务失败、
  profile 停用提交竞争及 QQ/Web 双向生命周期；后者使用合成客户端，未启动第二个真实 Gateway。
- 任务和图库分别持久化；进程恰好在图库提交后、逐项确认前退出时，恢复为 unknown，禁止自动重放。
- 同步视觉无法立即取消，固定并发名额及同库锁保留至实际调用结束；关闭后拒绝迟到提交。
- 最低 Hermes 发行版尚未映射；缺失作用域/认证能力不绕过 core。core 不提供跨入口条件事务。

## 规范同步准备

四份 delta 均保持原规划行为。qq-sticker-maintenance delta 的 Purpose 已覆盖人工命令与 Web 的
显式入口、持久任务和一致性语义；归档时再同步主规范。本次不修改其他未归档 change 的进度。

截图核验补充：宿主主题的 foreground 为透明色，已改用 midground 正文色；重新截图确认标题、profile 和表单可见。截图仅保留在本地验证环境。

最后补充：YAML 启动与共享快照、Gateway 不导入 Web、预览路径伪造拒绝、清理计划引用变化/过期、
中断前逐项确认、刷新恢复保留批次、流式单图/批次实际字节限制均有聚焦测试。
后续增加真实 50 文件、10 MiB 单文件与 100 MiB 批次边界测试（含超限 1 byte），未缩小阈值。


## Debian 真实环境补充（2026-09-24）

- OrbStack milky-dashboard-debian：Debian 13 arm64，Hermes 0.21.4，源码同上固定 commit；
  Python 3.13.13、FastAPI 0.133.1、Starlette 1.3.1。Hermes 使用 VM 内隔离的临时安装和
  profile 根目录，未记录其本地路径。
- 用户明确授权后，从 hermes-dev 复制最小模型提供者和 Milky 配置，文件权限 0600；
  不记录密钥值。插件映射当前工作区，未启动第二个 Gateway。原主机未修改。
- 测试 Dashboard 仅监听 VM 回环端口，通过 SSH 隧道访问浏览器；VM 启动脚本和临时端口均未写入
  证据，使用 uv run --python 3.13 --extra web --with jieba --with typer 运行。
- 浏览器通过真实宿主 SDK 上传合成笑脸，真实自动辅助视觉返回 created；
  认证预览实际解码成功，编辑描述后重新分析成功且人工描述保留，使用次数保持 0。
  明确选择删除、清理计划确认（removed=1）、修复索引均 succeeded。
- Will 高级 JSON 与分组编辑同步，修改 textGain 保存后恢复，返回 will_policy=saved；
  运行态仍 unknown、提示重新加载。两个额外隔离 profile 的空图库和延迟响应切换验证通过。
- 测试服务优雅重启后，任务 ID/状态列表与图库总数和重启前逐项一致，未自动重放。
- Linux 独立插件环境全测试：1075 passed、3 skipped；默认 skip 后，在真实 Hermes 环境
  显式执行三个宿主专项：delivery hook、multiple image dispatch、prompt lifecycle，3 passed。
  曾把整个 multimedia 单元文件放进宿主环境，1 项依赖未注册 Platform 的普通单元 fixture 失败；
  按设计分开独立单元环境与真实宿主专项后通过，未修改 core 或绕过注册。
- Linux 真实 Milky API probe 21 项通过，种子仍明确为 synthetic fixture；与上述真实视觉分开记载。
- 真实只读 Milky smoke：登录、群列表、Bot 禁言同步 accepted；SSE 3 秒窗口无事件且记录
  transport_unknown，单独建立底层 SSE 连接 accepted。完整事件消费尚未通过，不记作成功。
  本轮未发送 QQ 消息或文件。
- 新增取消保护：同步视觉仍持有内核锁时，即使任务已取消，上传输入仍禁止丢弃和期限回收；
  线程真实结束后允许回收。实际边界与取消线程测试通过。
- 多引用删除拒绝、索引修复事务回滚、预览/回收竞争、发送本地读取与网络锁边界补测通过。
- 页面维护任务现显示清理与修复计数，避免只展示空对象。


补充专项：停用前派发/提交拒绝、视觉取消迟到不写回、不同 owner 关闭互不影响，以及
adapter 断开/Web 关闭双向资源独立均经合成依赖测试通过。浏览器真实取消返回 cancelled，
在途结果 unknown。四种图片格式、失败视觉显式重试、非贴纸 junk 排除回收、移动失败、
配额竞争和断线清理均已验证。批量 50/51 目标、原子字段校验、部分成功、覆盖清除通过。
Linux 合成宿主能力 probe 因 Hermes 采用源码快照而没有 Git 元数据，版本探测无法完成；
保留既有 Mac Git checkout 的完整能力 probe 证据，Linux 当前插件 API 和浏览器证据独立有效。


## 最终浏览器与质量门禁

- 独立 alpha profile 使用明确视觉 fixture 创建 21 张合成图片：20/1 分页、筛选空结果、
  翻页清除选择、两项批量编辑 succeeded；不把这 21 张 fixture 计为真实视觉调用。
- 修改返回给浏览器的旧版本，实际后端重新分析返回 partial/conflict，页面逐项显示。
- beta 首次配置先保存普通地址，再保存/清除合成凭证；凭证缺失与存在提示真实核验。
- Will JSON/分组互转；非法数值现在显示对应字段 invalid_input；托管只读、部分保存与 expired
  的页面展示采用受控响应注入，测试后移除拦截。真实后端对应语义由专项测试覆盖。
- 旧范围延迟响应不覆盖新范围；离开图库实际调用 URL.revokeObjectURL；390×844 无横向溢出；
  Tab 从 profile 进入导航按钮。移动端视觉结果仅保留在本地验证环境。
- 本地最终 uv run pytest -q -rs：1092 passed、3 skipped；三个 skip 在 Debian 真实宿主专项中
  分别通过。ruff check / format（498 files）、uv build、npm build/check/test（3 tests）、
  git diff --check、openspec validate --changes --strict（6 changes）均通过。
- Linux 当前插件 API probe 扩展为 22 项，通过停用 profile 读写拒绝检查。
