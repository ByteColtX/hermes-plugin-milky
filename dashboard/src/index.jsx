import { changedKeys, parseField, selectedTargets } from "./model.mjs";
const sdk = window.__HERMES_PLUGIN_SDK__;
if (sdk && window.__HERMES_PLUGINS__) {
  const React = sdk.React;
  const { useState, useEffect, useRef } = React;
  const { Button, Card, CardContent, Badge } = sdk.components;
  const root = "/api/plugins/hermes-plugin-milky";
  const labels = {
    base_url: "Milky 连接地址",
    allowed_chats: "入站白名单",
    session_buffer_size: "等待消息数量",
    home_channel: "默认投递目标",
    max_local_media_bytes: "本地媒体上限（bytes）",
    long_text_forward_threshold: "长文本转发阈值",
    group_member_event_notifications: "群成员事件通知",
  };
  const emotions = [
    "joy",
    "sadness",
    "anger",
    "surprise",
    "fear",
    "disgust",
    "love",
    "approval",
    "confusion",
    "neutral",
    "mixed",
    "unknown",
  ];
  const terminal = new Set([
    "succeeded",
    "partial",
    "failed",
    "cancelled",
    "interrupted",
  ]);
  async function api(path, profile, method = "GET", body) {
    const response = await sdk.authedFetch(
      root +
        path +
        (path.includes("?") ? "&" : "?") +
        new URLSearchParams({ profile }),
      {
        method,
        ...(body === undefined
          ? {}
          : {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }),
      },
    );
    const result = await response.json();
    if (!response.ok) {
      const failure = new Error();
      const allowed = [
        "invalid_input",
        "conflict",
        "expired",
        "busy",
        "blocked",
        "disabled",
        "unsupported",
        "malformed",
        "storage_error",
        "not_found",
        "too_large",
        "quota_exceeded",
      ];
      const category = allowed.includes(result.status)
        ? result.status
        : "unknown";
      failure.safeMessage =
        (Object.hasOwn(labels, result.field) || result.field === "will_policy"
          ? result.field + ": "
          : "") +
        category +
        "。请刷新核验，操作不会自动重提。";
      throw failure;
    }
    return result;
  }

  function Preview({ profile, id }) {
    const [url, setUrl] = useState("");
    const [status, setStatus] = useState("加载预览…");
    useEffect(() => {
      let active = true,
        objectUrl;
      const controller = new AbortController();
      sdk
        .authedFetch(
          root +
            "/gallery/" +
            encodeURIComponent(id) +
            "/preview?" +
            new URLSearchParams({ profile }),
          { signal: controller.signal },
        )
        .then(async (response) => {
          if (!response.ok) throw new Error();
          const blob = await response.blob();
          if (active) {
            objectUrl = URL.createObjectURL(blob);
            setUrl(objectUrl);
          }
        })
        .catch(() => {
          if (active) setStatus("预览不可用");
        });
      return () => {
        active = false;
        controller.abort();
        if (objectUrl) URL.revokeObjectURL(objectUrl);
      };
    }, [profile, id]);
    return url ? (
      <img src={url} alt="贴纸预览" />
    ) : (
      <p className="milky-meta">{status}</p>
    );
  }
  function WillEditor({ value, onChange }) {
    const [advanced, setAdvanced] = useState(false);
    const [error, setError] = useState("");
    const policy =
      typeof value === "string"
        ? (() => {
            try {
              return JSON.parse(value);
            } catch {
              return {};
            }
          })()
        : value || {};
    function update(section, key, next) {
      onChange({ ...policy, [section]: { ...policy[section], [key]: next } });
    }
    return (
      <section>
        <h2>Will 回复策略</h2>
        <Button
          onClick={() => {
            if (advanced && typeof value === "string") {
              try {
                const parsed = JSON.parse(value);
                if (
                  !parsed ||
                  Array.isArray(parsed) ||
                  typeof parsed !== "object"
                )
                  throw new Error();
                onChange(parsed);
                setError("");
              } catch {
                setError("JSON 格式错误，请修复后切换分组编辑");
                return;
              }
            }
            setAdvanced(!advanced);
          }}
        >
          {advanced ? "分组编辑" : "高级 JSON"}
        </Button>
        {advanced ? (
          <label className="milky-field">
            策略 JSON
            <textarea
              aria-label="Will JSON"
              value={
                typeof value === "string"
                  ? value
                  : JSON.stringify(value, null, 2)
              }
              onChange={(e) => onChange(e.target.value)}
            />
          </label>
        ) : (
          <>
            <label className="milky-field">
              引擎
              <select
                value={policy.engine || "routing"}
                onChange={(e) =>
                  onChange({ ...policy, engine: e.target.value })
                }
              >
                <option value="routing">routing</option>
                <option value="willingness">willingness</option>
              </select>
            </label>
            {["routing", "willingness"].map((section) => (
              <details key={section} open={policy.engine === section}>
                <summary>{section}</summary>
                {Object.entries(policy[section] || {}).map(([key, current]) => (
                  <label className="milky-field" key={key}>
                    {key}
                    {typeof current === "boolean" ? (
                      <input
                        type="checkbox"
                        checked={current}
                        onChange={(e) => update(section, key, e.target.checked)}
                      />
                    ) : (
                      <input
                        value={
                          typeof current === "object"
                            ? JSON.stringify(current)
                            : current
                        }
                        onChange={(e) => {
                          try {
                            const next =
                              typeof current === "number"
                                ? Number(e.target.value)
                                : typeof current === "object"
                                  ? JSON.parse(e.target.value)
                                  : e.target.value;
                            update(section, key, next);
                            setError("");
                          } catch {
                            setError(key + ": JSON 格式错误");
                          }
                        }}
                      />
                    )}
                  </label>
                ))}
              </details>
            ))}
            <label className="milky-field">
              priority
              <input
                type="number"
                value={policy.priority ?? 1000}
                onChange={(e) =>
                  onChange({ ...policy, priority: Number(e.target.value) })
                }
              />
            </label>
          </>
        )}
        {error && <p role="alert">{error}</p>}
      </section>
    );
  }
  function App() {
    const [choices, setChoices] = useState([]),
      [profile, setProfile] = useState(""),
      [tab, setTab] = useState("config");
    const [config, setConfig] = useState(null),
      [form, setForm] = useState({}),
      [token, setToken] = useState("");
    const [error, setError] = useState(""),
      [notice, setNotice] = useState(""),
      [busy, setBusy] = useState(false);
    const [gallery, setGallery] = useState({ items: [], total: 0 }),
      [page, setPage] = useState(1),
      [selected, setSelected] = useState([]);
    const [filter, setFilter] = useState({
        emotion: "",
        tag: "",
        description: "",
      }),
      [jobs, setJobs] = useState([]),
      [batch, setBatch] = useState(null),
      [batches, setBatches] = useState([]),
      [plan, setPlan] = useState(null);
    const [edit, setEdit] = useState({
      emotion: "",
      tags: "",
      description: "",
      clear: "",
    });
    const epoch = useRef(0),
      submission = useRef(false),
      original = useRef({});
    const dirty = Object.keys(changedKeys(original.current, form)).length > 0;
    async function guarded(fn) {
      const current = epoch.current;
      setBusy(true);
      setError("");
      try {
        await fn(() => current === epoch.current);
      } catch (failure) {
        if (current === epoch.current)
          setError(
            failure.safeMessage ||
              "请求失败。请刷新查看实际结果，尚未确认的操作不会自动重提。",
          );
      } finally {
        if (current === epoch.current) setBusy(false);
      }
    }
    async function loadConfig() {
      const current = epoch.current;
      const result = await api("/config", profile);
      if (current !== epoch.current) return;
      setConfig(result);
      original.current = result.effective || {};
      setForm({ ...original.current });
    }
    async function loadGallery() {
      const current = epoch.current;
      const query = new URLSearchParams({
        page: String(page),
        ...Object.fromEntries(Object.entries(filter).filter(([, v]) => v)),
      });
      const result = await api("/gallery?" + query, profile);
      if (current === epoch.current) {
        setGallery(result);
        setSelected([]);
      }
    }
    async function loadUploads() {
      const current = epoch.current;
      const result = await api("/uploads", profile);
      if (current === epoch.current) setBatches(result.items || []);
    }
    async function loadJobs() {
      const current = epoch.current;
      const result = await api("/jobs", profile);
      if (current === epoch.current) {
        setJobs(result.items || []);
        setBatch((previous) => {
          if (!previous) return previous;
          const done = new Set(
            (result.items || [])
              .flatMap((job) => job.items || [])
              .filter((item) =>
                ["created", "duplicate", "junk"].includes(item.status),
              )
              .map((item) => item.file_id),
          );
          return {
            ...previous,
            file_ids: previous.file_ids.filter((id) => !done.has(id)),
          };
        });
      }
    }
    useEffect(() => {
      if (!sdk.authedFetch || !sdk.fetchJSON) {
        setError("unsupported：宿主缺少认证客户端");
        return;
      }
      sdk
        .fetchJSON(root + "/profiles")
        .then((result) => {
          setChoices(result.profiles);
          setProfile(result.selected || "");
        })
        .catch(() => setError("无法读取宿主 profile"));
    }, []);
    useEffect(() => {
      epoch.current++;
      setConfig(null);
      setForm({});
      original.current = {};
      setSelected([]);
      setJobs([]);
      setGallery({ items: [], total: 0 });
      setBatch(null);
      setBatches([]);
      setPlan(null);
      setToken("");
      setNotice("");
      setBusy(false);
      if (profile)
        guarded(async (active) => {
          await loadConfig();
          if (active()) await loadJobs();
          if (active()) await loadUploads();
        });
    }, [profile]);
    useEffect(() => {
      if (profile && tab === "gallery") guarded(loadGallery);
    }, [profile, tab, page, filter]);
    useEffect(() => {
      if (!profile) return;
      const timer = setInterval(() => loadJobs().catch(() => {}), 3000);
      return () => clearInterval(timer);
    }, [profile]);
    useEffect(() => {
      const listener = (e) => {
        if (dirty) {
          e.preventDefault();
          e.returnValue = "";
        }
      };
      window.addEventListener("beforeunload", listener);
      return () => window.removeEventListener("beforeunload", listener);
    }, [dirty]);
    function switchProfile(next) {
      if (!dirty || window.confirm("放弃当前 profile 未保存的配置？")) {
        epoch.current++;
        setProfile(next);
        setPage(1);
      }
    }
    async function submit(operation, payload) {
      if (submission.current) return;
      submission.current = true;
      try {
        await guarded(async (active) => {
          const issued = await api("/requests", profile, "POST", { operation });
          const result = await api("/jobs", profile, "POST", {
            operation,
            request_id: issued.request_id,
            payload,
          });
          if (active()) {
            setNotice("已接受任务 " + result.task_id);
            await loadJobs();
          }
        });
      } finally {
        submission.current = false;
      }
    }
    async function saveConfig() {
      await guarded(async (active) => {
        const candidate = { ...form };
        for (const [key, value] of Object.entries(candidate)) {
          if (typeof value === "string") {
            try {
              candidate[key] = parseField(key, value);
            } catch {
              const failure = new Error();
              failure.safeMessage = (labels[key] || key) + ": invalid_input。请修正此字段。";
              throw failure;
            }
          }
        }
        const result = await api("/config", profile, "PATCH", {
          version: config.version,
          changes: changedKeys(original.current, candidate),
        });
        if (active()) {
          setNotice(JSON.stringify(result.results || result));
          await loadConfig();
        }
      });
    }
    async function credential(action) {
      if (
        action === "clear" &&
        !window.confirm("清除当前 profile 的 Milky 凭证？")
      )
        return;
      await guarded(async (active) => {
        const result = await api("/credential", profile, "POST", {
          action,
          value: token,
        });
        if (active()) {
          setToken("");
          setNotice("凭证状态：" + result.status);
          await loadConfig();
        }
      });
    }
    async function upload(files) {
      if (!files.length) return;
      await guarded(async (active) => {
        const data = new FormData();
        for (const file of files) data.append("files", file);
        const response = await sdk.authedFetch(
          root + "/uploads?" + new URLSearchParams({ profile }),
          { method: "POST", body: data },
        );
        if (!response.ok) throw new Error();
        const result = await response.json();
        if (active()) {
          setBatch(result);
          setNotice("上传完成；确认候选后开始导入。");
        }
      });
    }
    const targets = selectedTargets(gallery.items, selected);
    return (
      <main className="milky-dashboard">
        <h1>Milky QQ</h1>
        <p>连接配置、共享图库与可追踪的维护任务。</p>
        <div className="milky-toolbar">
          <label>
            目标 profile{" "}
            <select
              aria-label="目标 profile"
              value={profile}
              onChange={(e) => switchProfile(e.target.value)}
            >
              <option value="">请选择</option>
              {choices.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <Badge>{profile || "未选择"}</Badge>
          {busy && <span role="status">处理中…</span>}
        </div>
        <nav className="milky-tabs" aria-label="Milky 管理">
          {[
            ["config", "配置"],
            ["gallery", "图库"],
            ["jobs", "维护任务"],
          ].map(([key, label]) => (
            <Button
              key={key}
              onClick={() => setTab(key)}
              aria-pressed={tab === key}
            >
              {label}
            </Button>
          ))}
        </nav>
        {error && (
          <p role="alert" className="milky-error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="milky-notice">
            {notice}
          </p>
        )}
        {!profile ? (
          <p>选择宿主已启用 Milky 的 profile 后开始管理。</p>
        ) : tab === "config" ? (
          config ? (
            <Card>
              <CardContent>
                <h2>连接与消息配置</h2>
                <p className="milky-notice">
                  保存后需重新加载或重启。运行态：
                  {config.runtime_status || "unknown"}
                  。宿主按字段保存，不提供跨入口条件事务；并发保存后请刷新核验。
                </p>
                {Object.entries(labels).map(([key, label]) => (
                  <label className="milky-field" key={key}>
                    {label}
                    {key === "group_member_event_notifications" ? (
                      <input
                        type="checkbox"
                        checked={!!form[key]}
                        disabled={config.writable?.[key] === false}
                        onChange={(e) =>
                          setForm({ ...form, [key]: e.target.checked })
                        }
                      />
                    ) : (
                      <input
                        disabled={config.writable?.[key] === false}
                        value={
                          typeof form[key] === "object"
                            ? JSON.stringify(form[key])
                            : (form[key] ?? "")
                        }
                        onChange={(e) =>
                          setForm({ ...form, [key]: e.target.value })
                        }
                      />
                    )}
                    <span className="milky-meta">
                      来源：{config.sources?.[key] || "unknown"} ·{" "}
                      {config.writable?.[key] === false ? "托管只读" : "可修改"}
                    </span>
                    {config.errors?.[key] && (
                      <span role="alert">此字段无有效值，请修正配置。</span>
                    )}
                  </label>
                ))}
                <p className="milky-meta">
                  白名单为空阻止全部普通入站；管理命令仍交给 Hermes core 授权，不会禁用插件或 SSE。全部放行请填写 group:* 和 dm:*。
                </p>
                <WillEditor
                  value={form.will_policy || {}}
                  onChange={(value) => setForm({ ...form, will_policy: value })}
                />
                <div className="milky-toolbar">
                  <Button disabled={busy || !dirty} onClick={saveConfig}>
                    保存普通配置
                  </Button>
                  <Button disabled={busy} onClick={() => guarded(loadConfig)}>
                    刷新配置
                  </Button>
                </div>
                <h2>凭证</h2>
                <p>
                  当前：{config.has_access_token ? "已配置" : "缺失"}
                  ；空输入保持原凭证。
                </p>
                <label className="milky-field">
                  新 token
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                  />
                </label>
                <div className="milky-toolbar">
                  <Button disabled={busy} onClick={() => credential("replace")}>
                    替换凭证
                  </Button>
                  <Button disabled={busy} onClick={() => credential("clear")}>
                    清除凭证
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <p>读取配置…</p>
          )
        ) : tab === "gallery" ? (
          <>
            <div className="milky-toolbar">
              <select
                aria-label="情绪筛选"
                value={filter.emotion}
                onChange={(e) => {
                  setPage(1);
                  setFilter({ ...filter, emotion: e.target.value });
                }}
              >
                <option value="">所有情绪</option>
                {emotions.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
              <input
                aria-label="标签筛选"
                placeholder="标签"
                value={filter.tag}
                onChange={(e) => {
                  setPage(1);
                  setFilter({ ...filter, tag: e.target.value });
                }}
              />
              <input
                aria-label="描述检索"
                placeholder="搜索描述"
                value={filter.description}
                onChange={(e) => {
                  setPage(1);
                  setFilter({ ...filter, description: e.target.value });
                }}
              />
            </div>
            <p>
              {gallery.total} 个条目 · 当前页已选 {targets.length} 个
            </p>
            <div className="milky-grid">
              {gallery.items.map((item) => (
                <article className="milky-sticker" key={item.sticker_id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.includes(item.sticker_id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, item.sticker_id]
                            : selected.filter((x) => x !== item.sticker_id),
                        )
                      }
                    />
                    {item.description}
                  </label>
                  <Preview profile={profile} id={item.sticker_id} />
                  <p>
                    {item.emotion} · {item.tags.join(" / ")}
                  </p>
                  <p className="milky-meta">
                    {item.sticker_id}
                    <br />
                    使用 {item.use_count} 次 · {item.file_status}
                    <br />
                    字段来源：{JSON.stringify(item.field_sources)}
                  </p>
                </article>
              ))}
            </div>
            {!gallery.items.length && <p>没有符合条件的贴纸。</p>}
            <div className="milky-toolbar">
              <Button disabled={page <= 1} onClick={() => setPage(page - 1)}>
                上一页
              </Button>
              <span>第 {page} 页</span>
              <Button
                disabled={page * 20 >= gallery.total}
                onClick={() => setPage(page + 1)}
              >
                下一页
              </Button>
            </div>
            <details>
              <summary>编辑已选择的 {targets.length} 个条目</summary>
              {Object.keys(edit).map((key) => (
                <label key={key} className="milky-field">
                  {key === "clear" ? "清除覆盖字段（逗号分隔）" : key}
                  <input
                    value={edit[key]}
                    onChange={(e) =>
                      setEdit({ ...edit, [key]: e.target.value })
                    }
                  />
                </label>
              ))}
              <Button
                disabled={!targets.length || busy}
                onClick={() =>
                  submit("edit", {
                    targets,
                    sets: Object.fromEntries(
                      Object.entries(edit)
                        .filter(([k, v]) => k !== "clear" && v)
                        .map(([k, v]) => [k, k === "tags" ? v.split(",") : v]),
                    ),
                    clears: edit.clear ? edit.clear.split(",") : [],
                  })
                }
              >
                提交字段修改
              </Button>
            </details>
            <div className="milky-toolbar">
              <Button
                disabled={!targets.length || busy}
                onClick={() => submit("reanalyze", { targets })}
              >
                重新分析所选
              </Button>
              <Button
                disabled={!targets.length || busy}
                onClick={() => {
                  if (
                    window.confirm(
                      "删除明确选择的 " +
                        targets.length +
                        " 个条目？\n" +
                        targets.map((x) => x.sticker_id).join("\n"),
                    )
                  )
                    submit("delete", { targets });
                }}
              >
                删除所选
              </Button>
            </div>
            <h2>上传图片</h2>
            <Button disabled={busy} onClick={() => guarded(loadUploads)}>
              查看保留批次
            </Button>
            <label className="milky-field">
              恢复批次
              <select
                value={batch?.batch_id || ""}
                onChange={(event) =>
                  setBatch(
                    batches.find(
                      (item) => item.batch_id === event.target.value,
                    ) || null,
                  )
                }
              >
                <option value="">选择已有批次</option>
                {batches.map((item) => (
                  <option key={item.batch_id} value={item.batch_id}>
                    {item.batch_id.slice(0, 12)} · {item.file_ids.length} 个候选
                    {item.active ? " · 任务中" : ""}
                  </option>
                ))}
              </select>
            </label>
            <p>单图 10 MiB，每批最多 50 张、100 MiB。上传后单独确认导入。</p>
            <input
              aria-label="选择图片"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              multiple
              disabled={busy}
              onChange={(e) => {
                upload([...e.target.files]);
                e.target.value = "";
              }}
            />
            {batch && (
              <div>
                <pre className="milky-results">
                  {JSON.stringify(batch, null, 2)}
                </pre>
                <div className="milky-toolbar">
                  <Button
                    disabled={busy || !batch.file_ids.length}
                    onClick={() =>
                      submit("import", {
                        batch_id: batch.batch_id,
                        file_ids: batch.file_ids,
                      })
                    }
                  >
                    导入本批次
                  </Button>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      guarded(async (active) => {
                        await api(
                          "/uploads/" + batch.batch_id,
                          profile,
                          "DELETE",
                        );
                        if (active()) setBatch(null);
                      })
                    }
                  >
                    丢弃本批次
                  </Button>
                </div>
              </div>
            )}
            <h2>图库维护</h2>
            <div className="milky-toolbar">
              <Button
                disabled={busy}
                onClick={() =>
                  guarded(async (active) => {
                    const result = await api(
                      "/cleanup/preview",
                      profile,
                      "POST",
                      {},
                    );
                    if (active()) setPlan(result);
                  })
                }
              >
                预览清理
              </Button>
              <Button disabled={busy} onClick={() => submit("reindex", {})}>
                修复索引
              </Button>
              <Button
                disabled={busy}
                onClick={() => submit("reclaim_uploads", {})}
              >
                回收过期上传
              </Button>
            </div>
            {plan && (
              <div>
                <pre className="milky-results">
                  {JSON.stringify(plan, null, 2)}
                </pre>
                <Button
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm("执行此预览范围的清理？"))
                      submit("cleanup", { plan_id: plan.plan_id });
                  }}
                >
                  确认此清理计划
                </Button>
              </div>
            )}
          </>
        ) : (
          <section>
            <h2>维护任务</h2>
            <p>
              页面关闭后任务继续运行。这里只轮询状态，断线不会自动重新提交。历史保留
              7 天、最多 1000 条；过期请求显示 expired。
            </p>
            <Button onClick={() => guarded(loadJobs)}>刷新任务</Button>
            {jobs.map((job) => (
              <Card key={job.task_id}>
                <CardContent>
                  <h3>
                    {job.operation} · {job.status}
                  </h3>
                  <p className="milky-meta">{job.task_id}</p>
                  <pre className="milky-results">
                    {JSON.stringify(
                      job.items || job.results || job.summary || Object.fromEntries(
                        Object.entries(job).filter(([key]) => ![
                          "task_id", "operation", "status", "created_at", "updated_at",
                        ].includes(key)),
                      ),
                      null,
                      2,
                    )}
                  </pre>
                  {!terminal.has(job.status) && (
                    <Button
                      onClick={() =>
                        guarded(async () => {
                          await api(
                            "/jobs/" + job.task_id + "/cancel",
                            profile,
                            "POST",
                            {},
                          );
                          await loadJobs();
                        })
                      }
                    >
                      取消未开始项
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
            {!jobs.length && <p>暂无任务。</p>}
          </section>
        )}
      </main>
    );
  }
  window.__HERMES_PLUGINS__.register("hermes-plugin-milky", App);
}
