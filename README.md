# einvoicing-claude-skills

ClearTax e-invoicing team Claude Code skills, shared across the on-call rotations.

## What's inside

| Skill | Triggers | What it does |
|---|---|---|
| **`/v-oncall-handover`** | Run Monday morning before handover meeting | Drafts the weekly on-call handover doc for E-Invoicing, **for any region**. Config-driven via [`data/scopes.yaml`](data/scopes.yaml) — supported scopes `ind`, `ksa`, `eu`, `my`, `mea` (default `ind,ksa`). For each in-scope region it pulls verified PagerDuty bot incidents from that region's alert channels (+ shared `#sev1-engg`), reads each PD's full Slack thread to extract Fix/Resolution + Action Items, harvests customer-facing L3 threads, and computes Critical-API Health (the region's generate endpoints) + per-region Top-3 slowest/error-prone APIs via CubeAPM (1-hour buckets, mean-of-4-weeks baseline). Saves locally — no auto-commit, no auto-send. |

## Architecture: generic engine + config

The skill is **config-driven**. `skills/v-oncall-handover/SKILL.md` is the generic engine — the week-window math, thread-reading, false-alert/CFD heuristics, CubeAPM baseline methodology, and output format are all region-agnostic. Every region-specific fact lives in **[`data/scopes.yaml`](data/scopes.yaml)**:

```yaml
scopes:
  ind:  { alert_channels, pd_service_prefixes, cubeapm_services, generate_endpoints, ... }
  ksa:  { ... }
  eu:   { ... }   # EU / Peppol
  my:   { ... }   # Malaysia
  mea:  { ... }   # UAE / Oman / Jordan
```

**To add or fix a region, edit `data/scopes.yaml` only.** `--scope ind,ksa` produces one combined doc (the original behavior); `--scope eu` (or `my`, `mea`) produces that region's doc. Multiple scopes → one combined doc with a section per region.

## Prerequisites

1. **Claude Code** with MCP servers for: Slack, CubeAPM (`mcp__clarity-cubeapm__*`), PagerDuty (`mcp__clarity-pagerduty__*`).
2. **Read access** to the Slack channels listed in `data/scopes.yaml` for the scope(s) you run (alert channels + L3 channels + shared `#sev1-engg` `C08F1GJ9Z24`).
3. **CubeAPM query access** routed through the IND default cube (`meta.cubeapm_region: in` — single endpoint covers all regions' APM metrics).
4. **A local clone of the output repo(s).** Output is per-scope: IND/KSA → `~/Desktop/e-invoicing-be/oncall-handover/<year>/`; EU/MY/MEA → `~/Desktop/einvoicing-core/docs/oncall-handover/<scope>/`. Configured via `meta.output` + per-scope `output:` in `data/scopes.yaml`. The skill creates the parent dirs if missing. (You only need the clone for the scope(s) you actually run.)

## Install

```bash
# In Claude Code
/plugin install VashisthaCT/einvoicing-claude-skills
```

After install, `/v-oncall-handover` is available, or describe the task ("draft this week's KSA on-call handover").

## Configure for your team (edit `data/scopes.yaml`)

- **`meta.output`** (default `{repo_path, subdir}`) + per-scope **`output:`** overrides — where each region's doc is written. Ships as: IND/KSA → `~/Desktop/e-invoicing-be/oncall-handover/{year}/`; EU/MY/MEA → `~/Desktop/einvoicing-core/docs/oncall-handover/<scope>/`.
- **`engineers` / `l2_escalators`** — the shared rosters used to attribute L3 CFDs to the engineer who drove the fix (not the L2 escalator). Extend with your team.
- **Per-scope blocks** — `alert_channels`, `l3_channels`, `pd_service_prefixes`, `cubeapm_services`, `generate_endpoints`, `topk_service_regex`, `noisy_rule_ids`, `customers`, `notes`.

> ⚠️ The `eu` / `my` / `mea` blocks were **auto-discovered** from a Slack/PagerDuty/CubeAPM sweep. Each value carries a confidence marker in its block's `notes`. **Verify channel IDs, PD prefixes, and generate endpoints against a live week before trusting that region's metrics tables.**

## Args

- `--scope <keys>` — comma-separated scope keys (`ind`, `ksa`, `eu`, `my`, `mea`). Default: `meta.default_scope` (`ind,ksa`).
- `--week-start <YYYY-MM-DD>` — Monday IST of the week to document. Default: previous Monday.
- `--outgoing <name>` — outgoing primary on-call.
- `--shadow <name>` — outgoing shadow on-call (intern, L3 threads). Omit if none.
- `--out <path>` — output markdown path. Default resolved per-scope from config (the scope's `output:` override, else `meta.output`); filename `oncall-handover-<weekstart>.md`.

## What it does (Steps 0-7)

0. Loads `data/scopes.yaml` and resolves `--scope` into config blocks.
1. Computes the Mon→Sun IST week window.
2. Harvests PagerDuty bot posts from the in-scope alert channels + shared `#sev1-engg`. Keeps only PD services matching the in-scope `pd_service_prefixes`.
3. For each PD post: reads the full Slack thread → Fix/Resolution + Action Items, verifies against false-alert patterns + alert payload (+ each region's `noisy_rule_ids`).
4. Harvests customer-facing L3 threads (≥5 replies) from the in-scope `l3_channels`. Attributes to the engineer who drove the fix (not the L2 escalator), per the shared rosters.
5. Computes Critical-API Health on each region's `generate_endpoints` + per-region Top-3 slowest/error-prone via CubeAPM. Baseline = mean of last 4 weekly p99-max-1h values.
6. Composes Key takeaways — regression clusters, zombie endpoints, 1h-vs-15min noise notes.
7. Saves to disk. **Save-only — never auto-commits or pushes.**

## What it doesn't do (intentionally)

- Doesn't send the doc anywhere (no Slack post, no Coda push, no email).
- Doesn't `git add` / commit / push the output. Both output repos (`e-invoicing-be`, `einvoicing-core`) are shared team code repos.
- Doesn't include licensing-service, DevOps, Altinity, DBA, MongoProd, ITR-alerts, or Business Platform Alerts PDs (manager rejected non-einvoicing PD services in May 2026). The `pd_service_prefixes` keep-filter enforces this.
- Doesn't include regions outside `--scope` — each on-call gets only their slice; other-region PDs/CFDs are dropped.
- Doesn't run an unpopulated scope — if a region's config block is empty/`PENDING DISCOVERY`, it tells you to fill `data/scopes.yaml` first.
- Doesn't fabricate Slack permalinks — always uses the real `message_ts` from the API response.

## Verification before passing to next on-call

The skill drafts; you verify. Always check each PD's Fix/Resolution accuracy, each CFD's engineering owner + status, and the metrics interpretations (especially regression-cluster hypotheses). To add action items, edit the source MD — append `- [ ] new item` rows inside the existing `<ul>` cells.

## Reporting issues / contributing

Private team-internal repo. Open issues / PRs here, or DM Vashistha Garg (`U087T0SHNCC`).

## Related (Vashistha's personal skills)

The full personal productivity skills (`/v-rca`, `/v-country-brain`, `/v-pr-review`, etc.) live at `VashisthaCT/personal-skills` (private). Ask Vashistha for access.
