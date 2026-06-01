# CLAUDE.md — einvoicing-claude-skills

## What this is
ClearTax e-invoicing team Claude Code skills, shared across the IND+KSA on-call rotation. Forked from `VashisthaCT/personal-skills` for team use.

## Conventions
- Skills are prefixed `v-` (matching the source repo convention).
- Skill format: `skills/<name>/SKILL.md` with frontmatter (name, description).
- Drafts only — no skill auto-sends to Slack / Email / Coda / Git. Output lands locally in `~/Desktop/e-invoicing-be/oncall-handover/2026/`.

## Don't
- Don't run `git commit` or `git push` from the skill — user does these.
- Don't auto-send to Slack channels or external DMs. Drafts only.
- Don't commit handover MDs to `e-invoicing-be` — it's a shared team code repo. Save-only; outgoing on-call decides branching + commit cadence.

## Identifiers (must be customized per user before first run)

Edit `skills/v-oncall-handover/SKILL.md` and replace these with your own identifiers:

| Field | Vashistha's value (template) | Where to find yours |
|---|---|---|
| Slack user_id | `U087T0SHNCC` | Slack → profile → ⋮ → Copy member ID |
| Self-DM channel | `D088362AS65` | Right-click your name in Slack → Copy link → ID after `/archives/` |
| Manager Slack | `U0ABBKV5QDU` (Ayush Jain) | Manager's profile → Copy member ID |
| Manager DM | `D0AC1AKDJKT` | DM thread with manager → Copy link |

## MCP requirements

The skill requires these MCP servers connected in your Claude Code config:
- **Slack MCP** — for reading `#sev1-engg`, `#einv-gcc-alerts`, `#e-invoicing-pds`, `#einvoice-l3-support`. Tools used: `slack_read_channel`, `slack_read_thread`, `slack_search_public`.
- **CubeAPM MCP** (`clarity-cubeapm`) — for metrics queries. Tools used: `query_metrics_instant`, `query_metrics_range`, `list_available_regions`.
- **PagerDuty MCP** (`clarity-pagerduty`) — optional, used in Step 3 alert-payload verification. Tools: `get_incident_alerts`.

If any MCP is missing, the skill will degrade gracefully (e.g. skip alert-payload verification if PagerDuty is missing). It will fail to produce useful output if Slack or CubeAPM is missing.

## Tooling quirks (codified during the May 2026 build)

These are detailed in `skills/v-oncall-handover/SKILL.md` under the **Quirks** section. Highlights:
- CubeAPM `status_code` label value is `"ERROR"` not `"STATUS_CODE_ERROR"` (sight-agent pre-built queries are wrong).
- Use `histogram_quantiles("phi", 0.99, ...)` plural for vmrange buckets — singular `histogram_quantile(0.99, ...)` returns empty.
- Spring `dispatcherServlet` quirk — during cascades, per-endpoint err% reads 0% because errors get attributed to the dispatcher span. Mitigated by service-level err% in Critical-API table.
- Slack permalinks MUST use the real `message_ts` from the API. Never synthesize from a parsed IST timestamp — past bug landed wrong links via micros-zero-pad + IST→UTC timezone confusion.
