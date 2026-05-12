# Roadmap

Where hermes-recipes goes next. Reflects the state at 0.2.0
(2026-05-12).

## Next major: Phase 4c — Workflow worker + node executor

Status: **pending**. The runner enqueues tasks onto per-agent JSON queues
already (`shared-context/workflow-queues/<agentId>.jsonl`); the worker is
what consumes them and actually invokes the LLM / tool / approval node.

**Files to port from `clawrecipes/src/lib/workflows/`:**

| TS file | LOC | Python target |
|---|---|---|
| `workflow-worker.ts` | 1761 | `hermes_recipes/workflows/worker.py` |
| `workflow-node-executor.ts` | 534 | `hermes_recipes/workflows/node_executor.py` |
| `workflow-node-output-readers.ts` | 165 | `hermes_recipes/workflows/node_output_readers.py` |
| `kitchen-review-url.ts` | 49 | `hermes_recipes/workflows/kitchen_review.py` |

**Hermes integration decisions already made (see `docs/MAPPING.md`):**

- **LLM calls** go through `ctx.llm` (the `PluginLlm` facade defined in
  `hermes-agent/agent/plugin_llm.py`). Lets workflow nodes use the user's
  active model + credential pool without bringing their own keys. The
  facade also enforces per-plugin override config keys under
  `plugins.entries.<plugin_id>.llm.*`.
- **Tool invocations** go through `tools.registry.invoke(name, args)`.
- **Approval bindings** map to per-profile gateway transports
  (Telegram / Discord / Slack DMs). Approvals continue to be file-first
  under `shared-context/workflow-runs/<runId>/approvals/approval.json`;
  the worker only needs to *request* the approval — patching the file
  + resuming is already wired in Phases 4a + 6b.

**Effort estimate:** 2–3 sessions. The worker is the largest single
module in the TS source; node-executor is the next-largest. Both have
real Hermes-runtime integration surfaces (LLM, tools, gateway) that
need careful adapter design.

**Why we paused before tackling it:** the package is already useful
without 4c — team scaffolding, profile provisioning, cron reconciliation,
the ticket lifecycle, and the workflow scheduler all work. 4c unlocks
*node execution* specifically.

## Smaller things

- **Port remaining media drivers** (`NanoBananaPro`, `RunwayVideo`,
  `KlingVideo`, `LumaVideo`, `GenericDriver`). Same pattern as
  `openai_image_gen.py`; ~60–140 LOC each.
- **Slash commands.** Register `/recipes-tickets`, `/recipes-dispatch`,
  etc. via `ctx.register_command()` so agents can call them mid-
  conversation. We have the plugin context plumbing; this is mostly
  CLI-handler → command-handler shim work.
- **`hermes plugins list` for entry-point plugins.** Upstream gap in
  Hermes v0.13.0 — the directory-only `_discover_all_plugins()` helper
  in `hermes_cli/plugins_cmd.py` should also walk entry-points. Worth
  a PR to hermes-agent rather than working around it here.
- **Built-in recipe distribution.** The OpenClaw plugin ships bundled
  recipes under `recipes/default/`. We should publish a sister package
  `hermes-recipes-default` (or bundle inside this one) with team
  recipes for development / marketing / research / customer-support /
  writing teams.

## Long-tail / nice-to-have

- **Kanban sync adapter (Phase 6c?).** Mirror ticket-file state into
  Hermes's existing kanban DB at `~/.hermes/kanban.db` so users see
  the same tickets in `hermes kanban` and `/kanban`. Plan is documented
  in `docs/MAPPING.md` §4; defer until users actually want it.
- **Outbound posting.** The HTTP client + sanitizer are ported in
  Phase 5; we need workflow node-types for `outbound_post` (Phase 4c).
- **Honcho/Mem0 memory backends.** Recipes that want pluggable team
  memory would benefit from talking to Hermes's memory provider API
  rather than the file-first jsonl streams.
- **`hermes claw migrate` integration.** The existing OpenClaw
  migration skill (`optional-skills/migration/openclaw-migration/`)
  imports SOUL/memories/skills but skips recipes. After 4c lands,
  extend it to import workspace recipes too.
