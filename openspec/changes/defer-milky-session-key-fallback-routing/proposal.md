# Proposal

## Why

Hermes may reconstruct a Milky destination from the session key when the original session source is unavailable. Because the key is split at fixed colon positions while Milky targets contain a colon, this fallback can lose the group or QQ identifier and prevent notification delivery to the intended chat. The issue is recorded for follow-up, but its repair is deferred.

## What Changes

- Record session-key fallback routing as a known, deferred issue.
- Do not change plugin behavior, Hermes core, session keys, or destination encoding in this tracking entry.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This entry does not change specified behavior; spec changes will be considered when a repair is scheduled.

## Impact

- The fallback may affect asynchronous task completion and shutdown or restart notifications when Hermes cannot use the original session source. Ordinary replies commonly retain that source.
- Shutdown and restart notifications iterate current runtime sessions; a configured home channel may receive a separate notification. This issue does not imply broadcast to every stored conversation.
- When repair is resumed, preserve Milky's local `group:<id>` and `dm:<id>` targets, allowlist behavior, and outbound target contract. No `g_`/`d_` encoding or other alias scheme is selected here.
- Status: **known issue, deferred**. No implementation or solution design is included in this change.
