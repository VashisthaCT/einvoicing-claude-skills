---
name: v-oncall-tags
description: Find every time the e-invoicing on-call Slack handle was tagged OUTSIDE the support channel during a week, and why — infra warnings, product questions, security asks, release pings that never reach the handover. Config-driven per scope (oncall_handle in data/scopes.yaml). Runs standalone, and v-oncall-handover calls it for its "Tagged outside support" section. Read-only.
---

You find the on-call work that happens outside the official channels. The handover reads the support and alert channels only, so when someone tags the on-call handle in a product, infra or security channel, that ask — and whether anyone answered it — is invisible to the next on-call. This skill makes it visible.

**Read-only.** Never post, reply or react in Slack.

## Args

- `--scope <keys>` (optional) — scope keys from `data/scopes.yaml`. Default: `meta.default_scope`. Scopes that share a handle (e.g. `ind` and `ksa`) are searched once.
- `--week-start <YYYY-MM-DD>` (optional) — Monday IST of the week. Default: the most recent COMPLETE Mon–Sun week, same rule as v-oncall-handover Step 1.

## Step 0 — Load config

Resolve `data/scopes.yaml` exactly as v-oncall-handover Step 0 does (`${CLAUDE_PLUGIN_ROOT}/data/scopes.yaml` first). For each in-scope block read:
- `oncall_handle` — `{ id, name }`. The `id` is what you search; `name` is for display only.
- `l3_channels` — the support channels, where tags are expected. These are excluded.
- the shared `engineers` roster — to tell an e-invoicing responder from anyone else.

**No `oncall_handle` on a scope → stop for that scope and say so.** Do not guess a handle from naming patterns, and never substitute a PagerDuty role name: Slack user groups and PD roles are different audiences that only look alike.

## Step 1 — Search

Tool: `slack_search_public_and_private`.
- `keywords`: `["<oncall_handle.id>"]` — **search the ID, not the name.** Verified 2026-10-05: the ID matches both mention forms, `<@ID>` (people) and `<!subteam^ID>` (bots and workflows). Searching the handle's name misses the second form entirely.
- `filters`: `after:<weekstart − 1 day> before:<weekstart + 7 days>` (both bounds are exclusive).
- `include_bots: true`, `sort: timestamp`, `include_context: false`.
- **Follow the cursor until it runs out.** A page holds at most 20 results; one busy week already filled more than one page.
- Keep only results whose text really contains the ID. Drop prose that just mentions the handle's name.

## Step 2 — Filter

1. **Drop tags inside the scope's `l3_channels`** — count them, but they are the expected path.
2. **Collapse recurring reminders.** The same author posting near-identical text on 2+ days (e.g. a daily "Open L3 Issues count" bot) becomes one line: `<channel> — daily reminder, N posts`. Not N rows.
3. What remains is the outside-tag list.

## Step 3 — Read each outside tag

Read its thread with `slack_read_thread` — from the parent if the tag is a reply. Record:
- **Ask** — one plain-English line. What did they actually want?
- **Type** — one of: Prod alert / infra · Customer / support ask · Feature / API request · Question · Release / deploy · Security / compliance · FYI / cc-only · Other.
- **Answered by** — the first reply from someone on the `engineers` roster, and roughly how long after the tag. "Nobody" is a valid answer and the most important one.
- **Status** — resolved / open / unclear, from the thread's own evidence (a fix shipped, a "done", a ✅). Say "unclear" rather than guess.
- **Link** — permalink from the raw `ts` returned by the API, never computed from a displayed time. For a reply: `https://cleartaxtech.slack.com/archives/<channel>/p<ts without dot>?thread_ts=<parent ts>&cid=<channel>`.

Pure `cc: @handle` tags with no ask: mark FYI / cc-only and move on.

## Step 4 — Output

```
## Tagged outside support — N tags in M channels
| Channel | Who | Ask | Type | Answered by | Status | Link |
```
- Sort **open and unanswered first** — those are what the incoming on-call must pick up.
- FYI / cc-only tags and collapsed reminders go in ONE line under the table, not as rows.
- Under the table, one line: `Inside #<support channel>: K tags (expected, not listed).`
- Omit the whole section when N = 0.

Standalone run: print the section in chat. Inside v-oncall-handover: it becomes that doc's section.

## Limits — say these in the doc, don't hide them

- Search only sees what the person running it can see: public channels, plus private channels and DMs they belong to. Tags in private channels they aren't in are invisible. Add one footer line saying so.
- Search indexes a message's current text — a tag edited out later won't be found.
