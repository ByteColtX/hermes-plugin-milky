# 群文件下载

这份说明只讲手动下载。当前插件的 `get_group_file_download_url` 只查询 URL，不执行
`curl`/`wget`，也不会把文件自动写入 Hermes cache。

## 先确定引用从哪里来

不必固定从 `get_group_files` 开始。入站文件样文已经给出 `file_id` 时，直接使用它；只有
上下文里没有文件 ID，才去查列表。比如：

```text
[file:file_id=fixture-group-file,file_name=report.pdf,file_hash=NOT SUPPORTED]
```

这是 group 会话中的文件，可以直接调用 `get_group_file_download_url`：

```json
{
  "group_id": 700000001,
  "file_id": "fixture-group-file"
}
```

如果当前是 dm 会话，改用 `get_private_file_download_url`，并同时提供 `user_id`、`file_id`
和可用的 `file_hash`。`file_hash=NOT SUPPORTED` 时不要猜 hash，也不要调用私聊文件接口。

只有在入站样文没有 `file_id` 时，才调用 `get_group_files` 找到并核对文件 ID。文件名只能帮
你人工确认，不能代替 `file_id`。

成功结果会保留完整 envelope，里面应有 `data.download_url`：

```json
{
  "status": "ok",
  "retcode": 0,
  "data": {
    "download_url": "<temporary-download-url>"
  }
}
```

这个 URL 可能很快失效，也可能带预签名参数。不要把它写进日志、shell 历史、issue、提交或
普通聊天正文，不要打印响应头，也不要从 URL 猜文件名。

## 手动下载

先确认目标、文件名和保存目录。把工具结果放进当前 shell 的 `QQ_DOWNLOAD_URL` 变量，
再给 `QQ_TARGET` 一个专用目录中的明确文件名。不要使用 URL 的 basename。

### curl

```bash
QQ_TARGET="/tmp/hermes-qq-downloads/report.pdf"

curl --fail --silent --show-error --location \
  --connect-timeout 10 --max-time 30 --max-filesize 8388608 \
  --output "$QQ_TARGET" "$QQ_DOWNLOAD_URL"
```

### wget

```bash
QQ_TARGET="/tmp/hermes-qq-downloads/report.pdf"

wget --no-verbose --max-redirect=5 --timeout=30 --tries=1 \
  --output-document="$QQ_TARGET" "$QQ_DOWNLOAD_URL"
```

命令里的 8 MiB 是示例上限，实际值要看文件用途和已确认的业务限制。下载前应保证目标目录
已经存在，并在下载后检查文件是否为空、类型是否符合预期。

## 安全边界

- 不要使用 `--insecure` 或 `--remote-name`，也不要把未经检查的 URL 拼进 shell 字符串。
- `curl` 和 `wget` 不等同于 Hermes core 的安全下载器。它们不会替插件完成 SSRF、重定向、
  大小和 MIME 控制。
- 对来源不明、可能跳转到内网，或要交给 Agent 继续读取的文件，使用 Hermes core 已确认的
  安全下载入口。当前没有通用文件 URL 入口时，返回 `unsupported`，不要从插件里绕到 shell。
- `get_group_files` 和 `get_group_file_download_url` 都是查询工具，不建立本地缓存，也不改变
  群状态。
