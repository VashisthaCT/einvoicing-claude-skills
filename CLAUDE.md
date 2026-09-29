# CLAUDE.md — einvoicing-claude-skills

## What this is
ClearTax e-invoicing team Claude Code skills, shared across the on-call rotations. Forked from `VashisthaCT/personal-skills` for team use. The on-call handover skill is **config-driven and multi-region** — IND, KSA, EU/Peppol, Malaysia (MY), MEA — selected via `--scope`. The PR review skill (`v-pr-review`) needs no config, only an authenticated `gh` CLI.

## Conventions
- Skills are prefixed `v-` (matching the source repo convention).
- Skill format: `skills/<name>/SKILL.md` with frontmatter (name, description). The SKILL.md is the **generic engine**; all region-specific facts live in `data/scopes.yaml`.
- **To add or fix a region, edit `data/scopes.yaml` only** — never hardcode channels / PD prefixes / services / endpoints back into SKILL.md.
- Drafts only — no skill auto-sends to Slack / Email / Coda / Git. One opt-in exception: `v-pr-review --auto-fix` edits the runner's own PR description. Output location is per-scope (config): IND/KSA → `~/Desktop/e-invoicing-be/oncall-handover/<year>/`; EU/MY/MEA → `~/Desktop/einvoicing-core/docs/oncall-handover/<scope>/`. Configured via `meta.output` (default) + per-scope `output:` overrides in `data/scopes.yaml`.

## Don't
- Don't run `git commit` or `git push` from the skill — user does these.
- Don't auto-send to Slack channels or external DMs. Drafts only.
- Don't commit handover MDs to `e-invoicing-be` — it's a shared team code repo. Save-only; outgoing on-call decides branching + commit cadence.

## Configuring scopes (data/scopes.yaml)

`data/scopes.yaml` is the single source of region config. Top-level keys:
- `meta` — `default_scope`, `cubeapm_region`, `output` (default output `{repo_path, subdir}`), shared `sev1_channel`.
- `engineers` / `l2_escalators` — shared rosters for L3 CFD owner attribution (Step 4).
- `scopes.<key>` — one block per rotation (`ind`, `ksa`, `eu`, `my`, `mea`): `pd_service_prefixes`, `alert_channels`, `l3_channels`, `cubeapm_services`, `generate_endpoints`, `topk_service_regex`, `noisy_rule_ids`, `customers`, `notes`.

The `eu` / `my` / `mea` blocks were auto-discovered (Slack/PagerDuty/CubeAPM sweep). **Verify channel IDs, PD prefixes, and generate endpoints against a live week before relying on a region's metrics tables** — discovered values carry a confidence marker in `notes`. To onboard a new rotation, copy an existing block and fill its fields.

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
