# 真实宿主能力前置证据

验证日期：2026-09-24。宿主源码版本：`b3a1900e72a16da450ff637aaa37cc23f68992a6`。
Dashboard SDK 源码声明：`1.1.0`；FastAPI `0.133.1`，Starlette `1.3.1`。

## 证据范围

`real_host_asgi_synthetic_plugin`：在独立临时 Hermes 根目录安装、显式启用合成用户插件，
直接导入真实 Hermes Dashboard 应用，执行真实发现、路由挂载、中间件和应用 lifespan。
没有替换宿主函数、修改 core、读取已有用户配置或调用 Milky/视觉服务。

执行的是宿主现有 Python `3.11.15`，并未加载要求 Python 3.13+ 的 Milky 平台实现。
该检查证明宿主后端接入能力，不能代替最终 Milky 插件安装、浏览器 SDK 或完整维护流程验收。

## 能力矩阵

| 能力 | 结果 | 已执行检查 |
| --- | --- | --- |
| 用户插件声明式发现 | passed | 临时用户插件被识别为 `user` 来源 |
| 命名空间 API 挂载 | passed | 真实宿主挂载并响应合成媒体路由 |
| 已认证二进制响应 | passed | 合成图片响应 bytes 与 `no-store` 一致 |
| 未认证二进制拒绝 | passed | 同一路由返回 401 |
| 安装目录静态资源 | passed | 已启用插件资源返回 200 |
| 并发 profile 配置及凭证隔离 | passed | alpha / beta / alpha 并发请求各读自己的配置和合成凭证 |
| 非法 profile 拒绝 | passed | 路径样式 profile 返回 400 |
| 插件停用后的新请求 | passed | 通过 core 写入临时停用配置后原路由返回 404 |
| 路由启动与正常停止 | passed | 用户插件 APIRouter lifespan 的进入和退出均执行 |
| SDK 认证客户端浏览器请求 | passed | 当前 Milky 插件的真实浏览器流程通过 SDK 读取/保存配置、凭证、profile、上传和任务轮询 |
| Milky 实际插件目录安装 | passed | 当前 Milky 用户插件在真实宿主中加载并通过插件 API 探针 |
| 宿主代理前缀资源加载 | passed | `/hermes` 反向代理前缀下页面、资源和 SDK 配置请求通过 |
| 真实辅助视觉服务 | passed（完整流程证据） | 当前插件在 Debian 真实宿主中的视觉请求返回 `created`；本前置探针未单独发起请求，详见 `evidence.md` |

## 可重复执行

```text
uv run --no-project --python <Hermes 已安装解释器> scripts/dashboard_host_probe.py --hermes-source <Hermes 源码目录>
```

脚本在子进程清理环境来源，只保留基础进程环境和合成凭证；临时配置、profile、插件和宿主产生的
数据库随检查结束删除。输出只有版本和固定检查状态，不复制宿主日志、响应正文、凭证或媒体。
宿主进程超时或失败时输出 `blocked` 及安全异常类别。

## 实现约束

- 用户插件后端需要显式启用，项目目录下发现页面不代表其 Python API 会被挂载。
- 后端 profile 范围需要显式进入宿主 `_config_profile_scope`；SDK 不自动补充插件 API 的 profile。
- `_config_profile_scope` 为现有宿主内部接口，正式适配层应检查能力；缺失时返回 `unsupported`。
- 初始合成探针只证明宿主后端能力；当前插件的真实浏览器和代理前缀证据见 `evidence.md`，不把该探针单独当作完整视觉或 Milky 写入验收。

## 2026-09-24 Python 3.13 与当前插件补充验证

再次运行同一探针：Python 3.13.5、FastAPI 0.141.1、Starlette 1.7.0，上述全部 ASGI 检查通过。
当前 Milky 用户插件经真实浏览器加载，SDK 的配置读取、普通保存、凭证替换、profile 切换、
上传和任务轮询均执行；/hermes 反向代理前缀下页面、插件资源和配置读取通过。
真实 Milky API 的认证预览由 dashboard_plugin_probe.py 验证，图库种子使用合成视觉 fixture。
这些补充完成任务 1.1 的宿主能力前置检查；真实视觉与完整维护流程的结果以 `evidence.md` 的 Debian 补充为准，临时 alpha profile 的 `visual_unavailable` 仍作为早期 blocked 证据保留。
完整证据与剩余范围见 evidence.md。
