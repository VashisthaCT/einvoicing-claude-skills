---
name: v-oncall-tags
description: List the threads OUTSIDE the support channel where the e-invoicing on-call Slack handle was tagged during a week and the on-call replied — infra warnings, product questions, security asks, release pings that never reach the handover. Config-driven per scope (oncall_handle in data/scopes.yaml). Runs standalone, and v-oncall-handover calls it for its "Tagged outside support" section. Read-only.
---

You surface the on-call's work that happens outside the official channels. The handover reads the support and alert channels only, so when the on-call handle is tagged in a product, infra or security channel and the on-call answers there, that work is invisible to the next on-call. This skill lists it.

**Read-only.** Never post, reply or react in Slack.

## Args

- `--scope <keys>` (optional) — scope keys from `data/scopes.yaml`. Default: `meta.default_scope`. Scopes that share a handle (e.g. `ind` and `ksa`) are searched once.
- `--week-start <YYYY-MM-DD>` (optional) — Monday IST of the week. Default: the most recent COMPLETE Mon–Sun week, same rule as v-oncall-handover Step 1.
- `--oncall <name or Slack user ID>` (optional) — whose replies count. Default: the outgoing on-call v-oncall-handover passes in, else the Slack user running the skill. Resolve a name to its user ID with `slack_search_users`.

## Step 0 — Load config

Resolve `data/scopes.yaml` exactly as v-oncall-handover Step 0 does (`${CLAUDE_PLUGIN_ROOT}/data/scopes.yaml` first). For each in-scope block read:
- `oncall_handle` — `{ id, name }`. The `id` is what you search; `name` is for display only.
- `l3_channels` — the support channels, where tags are expected. These are excluded.

**No `oncall_handle` on a scope → stop for that scope and say so.** Do not guess a handle from naming patterns, and never substitute a PagerDuty role name: Slack user groups and PD roles are different audiences that only look alike.

## Step 1 — Search

Tool: `slack_search_public_and_private`.
- `keywords`: `["<oncall_handle.id>"]` — **search the ID, not the name.** Verified 2026-10-05 on a real week: the ID found 38 hits, the name 28, and nothing was name-only. The name search misses every mention Slack never resolved to a name — bot posts, Slackbot notices, forwarded messages.
- `filters`: `after:<weekstart − 1 day> before:<weekstart + 7 days>` (both bounds are exclusive).
- `include_bots: true`, `sort: timestamp`, `include_context: false`.
- **Follow the cursor until it runs out.** A page holds at most 20 results; one busy week already filled more than one page.
- Keep only results whose own text contains the ID. Match on the **bare ID** — search output shows `<@S…>` while `slack_read_thread` shows `<!subteam^S…>` for the same tag.
- Thread replies are found too, even in threads started weeks earlier — most tags are replies.

## Step 2 — Filter

1. **Drop tags inside the scope's `l3_channels`** — they are the expected path.
2. **Skip recurring reminders** without reading them: the same author posting near-identical text on 2+ days (e.g. a daily "Open L3 Issues count" bot). Match on author + text, not the bot flag — some daily digests post as a normal user.

## Step 3 — Read each remaining thread, keep only the ones the on-call replied in

Read the thread with `slack_read_thread` — **always from the parent.** About half of all tags are just "^" or "check this"; the ask lives in the parent. On threads with more than 100 replies the tool returns the newest 100, so pass `oldest=<tag ts>` to read from the tag onward.

**Keep the thread only if the on-call (`--oncall`) posted at least one reply after the tag.** A reaction (`:ack:`, `:eyes:`) is not a reply. A reply that only reroutes to another team still counts — it is on-call work — and its outcome is "Rerouted to <team>". Drop every other thread.

For each kept thread record:
- **Asked by** — who tagged, and the day.
- **Ask** — one plain-English line. What did they actually want?
- **Type** — one of: Prod alert / infra · Customer / support ask · Feature / API request · Question · Release / deploy · Security / compliance · Other.
- **Outcome** — Open / Answered / Resolved / Rerouted / Moved to L3, plus a few words from the thread's own evidence. Say "unclear" rather than guess.
- **Link** — permalink from the raw `ts` returned by the API, never computed from a displayed time. For a reply: `https://cleartaxtech.slack.com/archives/<channel>/p<ts without dot>?thread_ts=<parent ts>&cid=<channel>`.

## Step 4 — Output

Plain markdown, no HTML (the user's preview shows HTML as raw text):

```
## Tagged outside support — N threads

Threads outside `#<support channel>` where `<handle name>` was tagged and the on-call replied.

| Channel | Asked by | Ask | Type | Outcome | Link |
```
- Sort open threads first.
- Nothing under the table — no counts of other tags, no footer lines.
- Omit the whole section when N = 0.

Standalone run: print the section in chat. Inside v-oncall-handover: it becomes that doc's section.

## Limits (for you — they stay out of the doc)

- Search only sees what the person running it can see: public channels, plus private channels and DMs they belong to.
- Search indexes a message's current text — a tag edited out later won't be found.
- The user group's membership rotates at handover (Monday afternoon IST on 2026-10-05), so tags early on Monday may have reached the previous on-call.
