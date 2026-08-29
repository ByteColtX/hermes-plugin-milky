## Context

See `proposal.md` for the motivation. The repository is an unimplemented Python 3.13+
Hermes platform-adapter skeleton. `ARCHITECTURE.md` defines the target ownership and
protocol boundaries, while this change's `tasks.md` defines the future T01-T20 delivery
order. OpenSpec's main `specs/` directory describes behavior as built, so these
contracts remain in this active change until the corresponding runtime behavior exists.

## Goals / Non-Goals

**Goals:**

- Give every externally meaningful Milky adapter capability one stable capability path
  and one structured delta spec file.
- Make the protocol paths, identity namespaces, processing order, safety boundaries,
  errors, and degradation behavior testable before implementation.
- Keep OpenSpec artifacts aligned with the existing architecture without claiming that
  the skeleton already provides the described behavior.

**Non-Goals:**

- Implementing Python modules, Hermes integration, network clients, or tests in this change.
- Inventing Milky fields or Hermes media APIs where the architecture marks behavior as
  uncertain.
- Creating a second plugin entry point, an arbitrary Agent-callable Action catalog, a temp-message
  sending route, a plugin-owned media cache, or legacy configuration aliases.

## Decisions

### One capability, one delta spec

Each capability listed in `proposal.md` maps to exactly one
`specs/<capability-path>/spec.md`. This follows the spec-driven schema's capability
contract and keeps a future archive merge unambiguous. The capability paths are flat
because this repository has no established OpenSpec domain taxonomy yet.

### Agent-facing context is a bounded compatibility bridge

The Hermes public platform-adapter surface is trigger-oriented: it accepts a
`MessageEvent` turn but does not expose a platform-neutral append/observe-only operation for a
message that Will decided to wait on. Discarding those messages would make a later group
mention see only the trigger and lose the short conversational lead-in. The Milky adapter
therefore batches only the bounded, same-chat wait window into one read-only
`channel_context` at trigger time. This preserves context without creating an Agent turn or
Hermes transcript entry for every wait message; the current trigger remains the sole body of
the turn.

The rendering contract follows the proven compact format in
`../hermes-platform-onebot-v11/onebot_v11_platform/context.py` and its context tests, while
changing the protocol field mapping for Milky:

~~~text
[<sender_name> uid <sender_id> msg_id <message_id> reply_id <reply_id>]
<body>
~~~

History records are oldest-first and joined by one newline; an empty history is `None`. Header
and body line-boundary escaping keeps untrusted names and content from creating fake records.
The effective Hermes Agent input remains `channel_context`, then a blank line and
`[New message]`, then the current `MessageEvent.text`; the adapter does not embed that marker
itself. The display-name mapping is group member card → group member nickname → sender ID for
group messages, and friend nickname → sender ID for friend messages. In Milky those values are
read from the corresponding `group_member`/`friend` sender model, rather than copying OneBot
payload names.

This is deliberately a rendering compatibility decision, not a protocol migration: Milky
continues to use `dm:` instead of OneBot `private:`. Temporary sessions are recognized at the
protocol boundary and dropped with `ignored_temp`; they do not get a canonical key, buffer,
Will decision, Hermes turn, or outbound route. All attachment resolution remains deferred until
trigger as required by the Milky architecture.

### Plugin admission and Hermes-owned busy scheduling

Hermes exposes busy-input scheduling for platform adapters through the Gateway's
`display.busy_input_mode` setting. `queue` keeps follow-ups for later turns, `steer` injects
eligible text into the active run, and `interrupt` redirects or interrupts the active run;
the Gateway also owns its pending/FIFO and media-merge behavior. The adapter's
`handle_message()` returns after handing work to Hermes, so the plugin MUST NOT implement a
second Agent queue or wait for an Agent turn to finish.

The plugin uses one short-lived per-chat coordination boundary plus detached processing:

1. The SSE consumer parses and canonicalizes the event, performs atomic deduplication and
   assigns an ingress sequence.
2. The chat admission coordinator serializes canonical/Gate/wait-buffer/Will state and the
   atomic drain that creates a detached trigger batch in ingress order.
3. After the batch is detached, resource resolution, mapping and the single
   `handle_message()` submission run without holding the admission boundary. Different chats
   and successive trigger handlers may proceed independently; busy input behavior is then
   decided by Hermes according to `busy_input_mode`.
4. If resolution or mapping fails, retry the same detached batch or record an unrecoverable
   failure; never append it back unconditionally.
5. The detached handler ends after `handle_message()` returns normally. Hermes owns the
   active-session guard, busy handling, pending/FIFO follow-up, interrupt and steer behavior.

This keeps plugin state atomic without making an Agent stall block the SSE receive loop or
creating a plugin-side Agent queue. A later message may be admitted while Hermes is busy; its
fate is determined by the public Hermes adapter contract, not by a copied session runtime.

### Milky DTO boundary

`milky/models.py` is the only owner of protocol-shaped data. Use frozen, slotted typed models
for `Event`, `IncomingMessage`, `IncomingForwardedMessage`, `OutgoingForwardedMessage`,
`FriendEntity`, `GroupEntity`, `GroupMemberEntity`, and each known segment variant. Every model
has a safe `extras` mapping for version extensions; extras are diagnostic-only and never become
text or an Action parameter implicitly.

The parser must reject booleans where `int64` is required, negative IDs/counters/timestamps,
missing required fields, wrong JSON container types, and inconsistent group IDs. Protocol
`int64` values become validated Python `int` values; internal chat keys are only `group:<id>`
and `dm:<id>`. The Milky v1.3 login response uses `data.uin`; group list and member responses
use `data.groups` and `data.member`. A defensive missing `message_seq` is allowed to reach the
explicit `no_stable_message_id` canonical downgrade, but it never enters a stable dedup key.
`message_scene=temp` is a successful protocol parse followed by an explicit `ignored_temp`
result, not a malformed message and not a `dm:` fallback.

The top-level `Event` contains `event_type`, Unix-second `time`, `self_id`, and an object-valued
`data`. `IncomingMessage` contains `message_scene`, `peer_id`, `message_seq`, `sender_id`,
`time`, and ordered `segments`, plus the scene-specific friend/group sender entities when
provided. `FriendEntity` supplies user identity and nickname; `GroupEntity` supplies group
identity and counts; `GroupMemberEntity` supplies group/user identity, nickname/card, role and
mute fields, especially nullable or omitted `shut_up_end_time`. Forwarded-message DTOs contain
timestamp, sender identity/name, and nested ordered segments, but an incoming `forward` segment
initially contains only `forward_id`, title, preview and summary; full messages come from the
separate `get_forwarded_messages` Action at trigger time. Known incoming segment payloads are
text, mention, mention_all, face, reply, image, record, video, file, forward, market_face,
light_app, xml, and markdown. Milky v1.3 has no independent mention-here segment, so that signal
cannot be inferred from arbitrary text. `image`, `record`, and `video` only produce
`media_resource_references`, retaining `resource_id`, optional `temp_url`, and safe MIME/size
hints. Inbound `file` only produces `file_attachment_references`, retaining `file_id`,
`file_name`, `file_size`, optional `file_hash`, and the raw segment; it is not a Milky
`media_resource` and is not resolved through `get_resource_temp_url`. A file may be materialized
as `kind="document"` at the Hermes boundary, but that does not change its inbound type. An
outbound file is a separate `file_upload` and never a message segment. The protocol schema's
`[unknown]` default is not adopted: unknown segments remain unknown raw extensions and never
become text.

The first observed v1.3 test-environment responses also established that `get_group_list` returns
an object containing `groups`, successful member responses may omit `shut_up_end_time` when the
member is not muted, and SSE uses an outer `milky_event` field whose JSON payload carries the
business `event_type`. These observations are compatibility fixtures, not credentials or live
data snapshots.

### Normalizer and strategy-feature boundary

T07 owns only protocol-independent identity, the canonical identity shell and TTL dedup. T08
consumes the T04 typed DTO and is the single owner of segment semantics, ordered body rendering,
strategy features and categorized deferred references. T09 consumes the canonical and normalized
results for Gate and admission; it must not reparse raw segments. This prevents canonical,
Will routing and willingness from independently deriving different meanings from the same
payload.

The observable normalized result preserves the original segment order and exposes body content,
strategy text, mention signals, reply presence and target sequence, the separately typed
`media_resource_references` and `file_attachment_references`, and safe diagnostics. Text and
markdown contribute their declared content; mention contributes a safe display form and self/all
signals; face, reply, image, record, video, file, forward, market face, light app and XML
contribute stable explanatory placeholders while retaining typed data. Unknown segments contribute
only safe raw/diagnostic metadata. Reply and forward nested content are kept for later resolution
and are not silently merged into the current message's strategy text.

Milky v1.3 has no independent `mention_here` segment. T08 therefore emits only self, all and
none for ordinary v1.3 input, and never infers here from text or a mention name. A future here
signal requires an explicitly recognized protocol extension and a separate contract. A reply
with the schema-required `message_seq` is a quote signal even when its original content has not
yet been fetched; missing required reply fields remain a malformed protocol case rather than an
invented target.

T08 performs no Action or other external operation. `resource_id` for image, record and video is
resolved only later through the confirmed `get_resource_temp_url` Action. A `file_id` is not
passed to that Action: group files use the confirmed `get_group_file_download_url` Action with
`group_id` and `file_id`; private files use the confirmed `get_private_file_download_url` Action
with `user_id`, `file_id`, and the required `file_hash`. These Actions return a `download_url`,
but that URL is still not a local path. `forward_id` uses `get_forwarded_messages`; a missing
full reply uses `get_message` with its scene, peer and message sequence. T08 stores only the
categorized references. Resource failure placeholders and Hermes attachment materialization
belong to T14.

### Milky reference taxonomy and Hermes materialization boundary

The adapter uses different names for protocol references and materialized local attachments:

| Layer | Name | Contents and ownership |
|---|---|---|
| Milky normalization | `media_resource_references` | `image`/`record`/`video`; `resource_id`, optional `temp_url`, safe MIME/size hints |
| Milky normalization | `file_attachment_references` | inbound `file`; `file_id`, name, size, optional hash, raw segment; not a `media_resource` |
| Milky normalization | `forward_references` / `reply_references` | IDs and inline/target metadata; not downloadable attachments yet |
| Hermes handoff | `hermes_attachment_materializations` | successful local path plus MIME/kind; `kind` may be `image`, `audio`, `video`, or `document` |
| Hermes `MessageEvent` | `media_urls` / `media_types` | existing Hermes fields containing only materialized local paths and their MIME types |

The inspected Hermes public surface does not expose one generic remote-reference-to-attachment
function. `cache_image_from_url()` and `cache_audio_from_url()` are async URL helpers: they
perform the download and return a local path, so T14 must await them. The corresponding bytes
cache helpers, including `cache_video_from_bytes()` and `cache_document_from_bytes()`, are
synchronous and only cache bytes already supplied; they do not await or fetch a URL.
`cache_media_bytes()` in `gateway.platforms.base` is the generic bytes materializer: it classifies
an attachment and returns `CachedMedia(path, media_type, kind, display_name)`, routing a ZIP or
other non-image/video/audio payload to `kind="document"` via `cache_document_from_bytes()`.
It is a cache/materialization primitive, not a document parser or URL downloader. A second
same-named helper in `gateway/platforms/media_cache.py` has a different signature and return
shape, so it is not a license to guess a broader adapter contract. The resolver therefore MUST
use a confirmed helper/seam for the specific kind, MUST await every async materialization before
constructing `MessageEvent`, and MUST leave the attachment unsupported if a safe URL-to-bytes
seam is absent. It MUST NOT create a plugin cache, issue an unconfirmed direct download, or
invent a generic `await_resource()` API.

Hermes `run.py` treats a materialized non-image/non-audio/non-video path as a document attachment:
it emits a path-pointing context note and tells the Agent to extract the content with its tools.
The common materializer does not itself parse a ZIP, PDF, DOCX, or spreadsheet into text.

`handle_message()` is a separate boundary: it accepts an already materialized `MessageEvent`,
spawns Hermes background processing and returns after submission. T14 awaits resource
materialization; T15 does not await the later Agent turn.

### Fixture boundary

T03 fixtures are separated into raw Action JSON responses, raw event JSON payloads, raw SSE frames,
and sanitized expected classifications. Action fixtures preserve the per-Action data envelope;
event fixtures use synthetic IDs and neutral content; SSE fixtures test the outer `milky_event`
wrapper separately from inner `event_type`. No fixture stores live IDs, token material, complete
live messages, media URLs or local paths. Live observations can only update the expected field
shape and boundary behavior.

### Keep the change active until implementation

The main OpenSpec specs describe the system as built. Since the current code is only a
skeleton, the delta files are the truthful location for the desired behavior. They may
be synced or archived only after the matching implementation, automated tests, quality
checks, and required local Milky smoke have evidence in the execution ledger.

### Behavior in specs, how in this design and tasks

The spec files state observable inputs, outputs, ordering, failure categories, and
security constraints. Module names, dependency direction, fixture strategy, and T01-T20
sequencing remain in this design, `ARCHITECTURE.md`, and this change's `tasks.md` so a
future refactor does not unnecessarily change the behavior contract.

### Protocol and safety uncertainty fails closed

Where the architecture cannot confirm remote execution, target routing, or media safety,
the contracts require `transport_unknown`, `unsupported`, or safe placeholders. For
plugin-local mute tracking, the state is deliberately fail-closed with only `muted` and
`unmuted`; an unverified refresh never silently becomes unmuted.

## Risks / Trade-offs

- **[Large initial change]** → The user explicitly requested coverage of every planned
  feature; each file remains narrowly scoped and is independently reviewable.
- **[Specs describe behavior not yet present]** → The proposal and `openspec/README.md`
  label the change active and prohibit archive until implementation evidence exists.
- **[Milky/Hermes version drift]** → Keep uncertain details at the protocol boundary and
  add a fixture/regression case before changing a behavior contract.
- **[Spec drift during implementation]** → Use OpenSpec update/sync actions and keep the
implementation evidence ledger in this change's `tasks.md` current.

## Migration Plan

1. Review and validate this change with OpenSpec strict validation.
2. Implement the capabilities in the dependency order from this change's `tasks.md`,
   adding fixtures and tests at each checkpoint.
3. Verify the implementation against the scenarios and record automated/real-environment
   evidence without secrets.
4. Sync or archive only the capabilities whose behavior is actually implemented; keep
   incomplete capabilities in an active change or split a follow-up change.

## Open Questions

- standalone sender 是否启用，以及其附件输入 URI（`http(s)://`、`file://`、`base64://`）的
  接收/安全策略，当前明确延期；v0.1 不实现、不在 manifest 声明，也不以默认值替用户决定。
- 其余外部协议或 Hermes API 细节继续以 fixture、unsupported 或显式 runtime-unknown 表达，
  不得在实现时按 OneBot 行为猜测。
