# einvoicing-claude-skills

ClearTax e-invoicing team Claude Code skills, shared across the IND+KSA on-call rotation.

## What's inside

| Skill | Triggers | What it does |
|---|---|---|
| **`/v-oncall-handover`** | Run Monday morning before handover meeting | Drafts the weekly on-call handover doc for E-Invoicing (IND + KSA). Pulls verified PagerDuty bot incidents from `#sev1-engg` / `#einv-gcc-alerts` / `#e-invoicing-pds`, reads each PD's full Slack thread to extract Fix/Resolution + Action Items, harvests customer-facing L3 threads from `#einvoice-l3-support`, and computes Critical-API Health (9 generate endpoints) + per-region Top-3 slowest/error-prone APIs via CubeAPM (1-hour buckets, mean-of-4-weeks baseline). Saves locally — no auto-commit, no auto-send. |

## Prerequisites

You need:
1. **Claude Code installed** with MCP servers configured for: Slack, CubeAPM, PagerDuty (`mcp__clarity-cubeapm__*`, `mcp__clarity-pagerduty__*`, and the Slack MCP server).
2. **Read access to ClearTax Slack workspace** including `#sev1-engg` (C08F1GJ9Z24), `#einv-gcc-alerts` (C03L955GFD5), `#e-invoicing-pds` (C0209C9E153), `#einvoice-l3-support` (C055ABMAVCL).
3. **CubeAPM query access** routed through the IND default cube (single endpoint covers IND + KSA APM metrics).
4. **A local clone of `e-invoicing-be`** — the default output path is `~/Desktop/e-invoicing-be/oncall-handover/2026/oncall-handover-<weekstart>.md`. Skill creates the `oncall-handover/2026/` subdirs if missing.

## Install

```bash
# In Claude Code
/plugin install VashisthaCT/einvoicing-claude-skills
```

After install, the `/v-oncall-handover` skill is available. Skill auto-launches when you type `/v-oncall-handover` or describe the task in natural language ("draft this week's on-call handover").

## Customize for your identity (4 things to change)

The skill ships with Vashistha's identifiers baked in. Before your first run, edit `skills/v-oncall-handover/SKILL.md` and update:

1. **Your Slack user_id** — search for `U087T0SHNCC` in the file and replace with yours. Used for `from:<@yourID>` searches.
2. **Your self-DM channel** — search for `D088362AS65` and replace with your DM-with-self channel ID. (Right-click your own name in Slack → Copy link → grab the ID from the URL.)
3. **Your manager + their DM** — search for `Ayush Jain (Slack U0ABBKV5QDU, DM D0AC1AKDJKT)` and replace.
4. **Your local repo path** — if `e-invoicing-be` lives somewhere other than `~/Desktop/`, edit the `--out` default in Step 1 of `SKILL.md`.

Engineer-owner list (the L3 CFD attribution) is in Step 4 of `SKILL.md` — keep or extend with your team's roster.

## Args

- `--week-start <YYYY-MM-DD>` — Monday IST of the week to document. Default: previous Monday.
- `--outgoing <name>` — outgoing primary on-call. Default: your name from SKILL.md.
- `--shadow <name>` — outgoing shadow on-call (intern, L3 threads). Omit if no shadow.
- `--out <path>` — output markdown path. Default: `~/Desktop/e-invoicing-be/oncall-handover/2026/oncall-handover-<weekstart>.md`.

## What it does (Steps 1-7)

1. Computes the Mon→Sun IST week window from `--week-start`.
2. Harvests PagerDuty bot posts from 3 Slack channels. Filters to `[E-Invoicing-*` and `[EInv-*` PD services only.
3. For each PD post: reads the full Slack thread to extract Fix/Resolution (root cause, who acted, how it closed) and Action Items (concrete follow-ups). Verifies against false-alert patterns + alert payload.
4. Harvests customer-facing L3 threads (≥5 replies) from `#einvoice-l3-support`. Attributes to engineering owner (not L2 escalator).
5. Computes Critical-API Health on 9 generate endpoints + per-region Top-3 slowest/error-prone APIs via CubeAPM. Baseline = mean of last 4 weekly p99-max-1h values (replaces the contaminated `max_over_time([28d:1h])` that previous versions used).
6. Composes Key takeaways block — regression clusters, zombie endpoints, 1h-vs-15min noise rejection notes.
7. Saves to disk. **Save-only — never auto-commits to `e-invoicing-be` or pushes anywhere.** You decide branching + commit cadence.

## What it doesn't do (intentionally)

- Doesn't send the doc anywhere (no Slack post, no Coda push, no email).
- Doesn't `git add` / commit / push the output. `e-invoicing-be` is a shared team code repo — every commit there shows up in PR/changelog views.
- Doesn't include licensing-service, DevOps, Altinity, DBA, MongoProd, ITR-alerts, or Business Platform Alerts PDs (manager rejected non-einvoicing PD services in May 2026 review).
- Doesn't mix EU / MY / BE / UAE / JO into the doc — scope is IND + KSA only.
- Doesn't fabricate Slack permalinks. Always uses the real `message_ts` from the API response.

## Verification before passing to next on-call

The skill drafts; you verify. Always check:
- Each PD's Fix/Resolution accuracy (thread may not have the full story — root cause may be discussed elsewhere).
- Each CFD's engineering owner + status (the heuristic gets it ~90% right but can miss).
- The metrics interpretations — especially regression-cluster hypotheses. Cross-check with DB/index/query-plan owners before flagging to team.

To add action items: just edit the source MD — append `- [ ] new item` rows inside the existing `<ul>` cells in the Action Items column. Rendered preview auto-updates.

## Reporting issues / contributing

This is a private team-internal repo. Open issues / PRs here, or DM Vashistha Garg (`U087T0SHNCC`).

## Related (Vashistha's personal skills)

The full personal productivity skills (32 skills, including `/v-rca`, `/v-country-brain`, `/v-pr-review`, etc.) live at `VashisthaCT/personal-skills` (also private). Ask Vashistha if you want access to those too.
