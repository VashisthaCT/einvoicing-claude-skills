---
name: v-oncall-handover
description: Draft a weekly on-call handover doc for the E-Invoicing service, for any region. Config-driven via data/scopes.yaml — supported scopes ind, ksa, eu, my, mea (default ind,ksa). For each in-scope region it pulls verified PD bot incidents from that region's alert channels (+ shared #sev1-engg), reads each PD's thread to extract Fix/Resolution + Action Items, harvests customer-facing L3 threads, and computes Critical-API Health (the region's generate endpoints) + per-region Top-3 slowest/error-prone APIs via CubeAPM (1-hour buckets, mean-of-4-weeks baseline). Output path is per-scope (config-driven): IND/KSA → e-invoicing-be/oncall-handover/<year>/; EU/MY/MEA → einvoicing-core/docs/oncall-handover/<scope>/. Drafts only — outgoing on-call MUST verify everything before passing to next on-call.
---

You are drafting a weekly E-Invoicing on-call handover doc. Run every Monday morning before the handover meeting.

**This skill is config-driven.** All region-specific facts (Slack channels, PagerDuty service prefixes, CubeAPM services + generate endpoints, customer/engineer rosters, noisy rule_ids) live in **`data/scopes.yaml`**, NOT in this file. This file is the generic engine: it loads the requested scope(s) from config and runs the same logic for each. To add or fix a region, edit `data/scopes.yaml` only.

## Args

- `--scope <keys>` (optional) — comma-separated scope keys from `data/scopes.yaml` (`ind`, `ksa`, `eu`, `my`, `mea`). Default: `meta.default_scope` (currently `ind,ksa`). Multiple scopes → one combined doc with one section per scope, in the order given. Single scope → single-region doc.
- `--week-start <YYYY-MM-DD>` (optional) — Monday IST of the week to document. Default: previous Monday relative to today.
- `--outgoing <name>` (optional) — outgoing primary on-call. Default: the runner's name.
- `--shadow <name>` (optional) — outgoing shadow on-call (intern, L3 threads). Omit if no shadow.
- `--out <path>` (optional) — output markdown path. Default: resolved from config per scope (see Step 7). IND/KSA → `~/Desktop/e-invoicing-be/oncall-handover/<year>/oncall-handover-<weekstart>.md`; EU/MY/MEA → `~/Desktop/einvoicing-core/docs/oncall-handover/<scope>/oncall-handover-<weekstart>.md`. Create parent dirs if missing.

## Step 0 — Load config (do this first, every run)

Read `data/scopes.yaml`. Resolve `--scope` into the list of scope blocks. From `meta` load: `sev1_channel`, `cubeapm_region`, `output` (default output location), `default_scope`. Load the shared `engineers` roster and `l2_escalators` exclusion list. For each in-scope block, you now have: `label`, `pd_service_prefixes`, (optional) `pd_workload_filter`, `alert_channels`, `l3_channels`, `cubeapm_services`, `generate_endpoints`, `topk_service_regex`, `noisy_rule_ids`, `customers`, `notes`, and (optional) `output` override.

**If a requested scope's block is unpopulated** (empty `alert_channels`/`generate_endpoints`, or `notes: PENDING DISCOVERY`): stop and tell the user that scope isn't configured yet, and point them at `data/scopes.yaml` to fill it. Don't fabricate channels/endpoints.

Everywhere below where the legacy doc said "KSA" or "India", read **"each in-scope region, using its config block."** The union of all in-scope `alert_channels` + the shared `sev1_channel` is the set of PD channels to read; the union of `pd_service_prefixes` is the PD-service keep-filter; etc.

## Output structure (the doc the manager treats as source of truth)

One section per in-scope region (in `--scope` order). Template per region `<R>` (use its `label`):

```
# Mon <date> → Sun <date>  ·  Scope: <labels, comma-sep>

## PagerDuty Incidents — <R label>
[table: Severity | Count | Incident | PD Service | Slack Thread | Fix / Resolution | Action Items]
Incident column: 1-2 sentences, layman terms (no rule_ids, no JedisPool, no `cube.kind=static`). Mention day-of-week if useful.
Fix / Resolution column: auto-populated from thread reading (Step 3). 2-4 sentences. Who diagnosed root cause, who acted, how it closed (auto-resolve vs human-resolve vs fix-deployed).
Action Items column: markdown task list (`- [ ] item`) inside an HTML `<ul><li>`. Auto-populated where the thread surfaced concrete follow-ups; otherwise `<ul><li>[ ] _(none — add as discovered)_</li></ul>`. On-call edits the source MD directly to add items.
(If a region had no real PDs: "None this week" + any routing-gap note from its config `notes`.)

## PagerDuty Incidents — Noise/False Alerts
[combined across ALL in-scope regions in one table: Region | Count | Alert | PD Service]
(omit section if zero)

## Customer-Facing Defects (CFDs)
### <R label> — N threads
[Customer | Issue | Short-term Fix | Long-term Fix | Engineering Owner | Status | Slack Thread]
(one sub-table per in-scope region that shares/owns an L3 channel)

## Critical-API Health: generate paths
[table — every in-scope region's generate_endpoints, with mean wk vs 4w, p99 max-1h wk vs 4w mean, err% wk vs 4w mean, outlier flag if wk > 1.5× 4w mean. Region column distinguishes them.]

## Top 3 Slowest + Top 3 Error-Prone APIs (per region, this week vs 4w mean)
### <R label> — Top 3 slowest (p99 max in 1h)      [one pair of tables per in-scope region]
### <R label> — Top 3 error-prone (max err% in 1h)

[Each table: # | API | Service | p99 wk (s) or Err% wk | p99 4w mean or Err% 4w mean | Pattern]

### Key takeaways
- [bullets — regression clusters, zombie endpoints, 1h-vs-15min noise notes, filter tweaks]
```

Reference canonical example output (IND+KSA, week May 18-24 2026) *was* `/tmp/oncall-handover-test/2026/oncall-handover-2026-05-18.md` — but `/tmp` is ephemeral and the file is usually gone. The structure above plus the `<style>` block in Step 7 are the source of truth.

## Step 1 — Compute the week window

If `--week-start` not given: document the **most recent COMPLETE Mon–Sun week** = `(Monday of the current week) − 7 days`. (Run on Mon Jun 29 → weekstart Jun 22; run on Tue Jun 30 → still Jun 22.)

⚠️ **Do NOT** use "today if Monday, else most recent past Monday" — that picks the **in-progress** current week (on Tue it lands on yesterday's Monday), whose `[7d]` metric windows have little/no data and whose handover is incomplete. The week being handed over is the one that just **ended** last Sunday.

```
start_ist = <weekstart>T00:00:00+05:30
end_ist   = <weekstart>+7dT00:00:00+05:30
start_utc = start_ist - 5h30m
end_utc   = end_ist - 5h30m
```

For Slack `oldest`/`latest`, use Unix-second `.000000` strings. For PagerDuty `since`/`until`, ISO 8601 UTC. For CubeAPM `start`/`end`, ISO 8601 UTC, `step=900`.

## Step 2 — Harvest PagerDuty bot posts (Slack-first, PD API for verification only)

PD `list_incidents` API has empty `assignments[]` for our team — useless for attribution. Slack PD-bot posts are the source of truth for who-handled-what.

**Channels to read** = `meta.sev1_channel` (shared) + the union of every in-scope block's `alert_channels`. Use `slack_read_channel` with `oldest`/`latest`, paginate via cursor, cap 300/channel.

For every PagerDuty bot message extract:
- **Message TS (raw, with microseconds)** — capture `message_ts` from the Slack response verbatim (e.g. `1779497223.046859`). **Do NOT synthesize this from the IST timestamp string** — two confirmed failure modes:
  1. **Microseconds zero-padding**: real Slack `ts` always has non-zero micros. Constructing `p<unix_seconds>000000` lands near but not on the message.
  2. **IST→UTC timezone bug**: parsing `02:22:43 IST` and computing unix as if UTC gives a link 5h30 ahead. Real: `02:22:43 IST → 20:52:43 UTC (prev day) → 1779310363`. Always use the API-returned `message_ts`.
- IST timestamp (raw ts → `%a %b %d %H:%M IST`, display only — NOT for link construction).
- PD Service (verbatim, e.g. `[E-Invoicing-GCC] Proactive Alerts Sev1`).
- Urgency (`High` / `Low`).
- Title (verbatim).
- **Reply count** (gates whether the Step 3 thread deep-dive is worth doing; 0 replies = PD-bot-only, skip Fix/Resolution dive).
- Slack thread permalink — `https://cleartaxtech.slack.com/archives/<channel_id>/p<seconds><6-digit-micros>` from the raw ts. E.g. `ts=1779497223.046859` → `p1779497223046859`. Strip the dot, do not zero-pad.

**Filter strictly:** keep a PD post only if its PD Service starts with one of the **union of in-scope `pd_service_prefixes`** (from config). Drop everything else — including einvoicing-adjacent infra/other-team services the manager rejected:
- `ITR-alerts`, `Business Platform Alerts *` (even when title mentions IRP / `kramer-prod-irp-*`), `DevOps Alerts *`, `Altinity *`, `DBA Infra *`, `Data Platform *`, `MongoProd *`.

**`pd_workload_filter` exception (one documented carve-out — optional, off by default).** If an in-scope block has a `pd_workload_filter` regex, it means that region has **no dedicated PD service yet** and its alerts currently land on the shared `DevOps Alerts Sev 2` service. For that region only: ALSO keep a `DevOps Alerts Sev 2` post if its alert body / workload name matches the region's `pd_workload_filter`. This is the single exception to "drop DevOps Alerts". Attribute such a kept post to that region. (No scope ships with this enabled by default; MEA carries the recipe commented out — uncomment + add `#devops-alerts-sev2` to its `alert_channels` to capture MEA pages before its dedicated service goes live.)

If a region's config `notes` flags a routing gap (e.g. IND IRP CrashLoop on `Business Platform Alerts Sev1`), surface it as a prose callout in that region's section, not in the table.

## Step 3 — Verify each PD + extract Fix/Resolution + Action Items

For each in-scope PD bot post, run all checks:

1. **Read its full Slack thread via `slack_read_thread`** using the raw `message_ts` from Step 2. `limit=100` (more if reply count > 100). Three purposes:
   - **(a) False-alert filter.** Any human reply with verbatim "false alert" or "test alert" → bucket FALSE / TEST.
   - **(b) Fix/Resolution column** — 2-4 sentences: **root-cause diagnosis** (who identified the cause + what they found), **who acted** (engineering owner who drove troubleshooting, NOT the PD-ack-only person, NOT the L2 escalator), **how it closed** (auto-resolved by CubeAPM / human mark-resolve+silence / fix deployed), **outstanding state** (if force-closed but cause persists, flag it).
   - **(c) Action Items column** — concrete follow-ups: "we should X" / "need to check Y" / `@mention` investigate-asks / deferred fixes ("PR pending", "rollout next week") / unresolved open questions. Format as a markdown task list inside `<ul><li>`:
     ```html
     <ul>
       <li>[ ] Concrete action item with @owner or context</li>
       <li>[ ] Another item</li>
     </ul>
     ```
     No follow-ups → `<ul><li>[ ] _(none — add as discovered)_</li></ul>`.
2. **Auto-resolve pattern.** TTR < 5 min, no human ack, no human reply → likely FALSE flap. Confirm via #4.
3. **Pull alert payload** via `mcp__clarity-pagerduty__get_incident_alerts`:
   - `cube.kind = anomaly` + query `<> 4` / `< 4` on call-rate → traffic-dip detector. `value < anomaly_prediction` → FALSE (quiet period); during a known outage window → REAL (traffic genuinely dropped).
   - annotation contains `Test alert` / `Notification test` → TEST.
   - `cube.kind = static` (e.g. `Error percentage (High)`, `> 10%` / `> 25%`) → REAL static-threshold breach.
4. **Same-pattern repeats:** group consecutive same-title alerts → one row with `Count = N`, time range `start – end`. Merge + dedupe Fix/Resolution + Action Items across the group. BUT: if two fires of the same alert had **different root causes** (verified in their `#sev1-engg` threads — see #5), split them into separate rows; "same title" ≠ "same incident".
5. **Sev1 cause lives in `#sev1-engg` — always cross-read it.** The per-region `alert_channels` usually carry ONLY the PD-bot ack/resolve for a Sev1; the human root-cause bridge happens in the shared `#sev1-engg`. For every Sev1 (and any in-scope PD whose per-region thread shows only bot ack/resolve), find the SAME incident's `#sev1-engg` thread (match by incident title + timestamp — the `message_ts` differs per channel, so capture each separately) and read it for the real cause. Do NOT conclude "no human investigation" from the per-region thread alone. _(2026-06-30: both `[E-Invoicing] Circuit breaker ZATCA trigger` Sev1s were diagnosed only in `#sev1-engg` — Jun 24 = a pdfGenerator deploy whose pods got stuck, hitting the print API; Jun 25 = the licensing service's Redis URL not updated in Vault during the Redis→Valkey migration. Neither was a ZATCA issue — the alert is generically named and fires on ANY einvoicing circuit-breaker-open.)_
6. **Surface dependency / cross-team Sev1s that explain einvoicing symptoms** as a clearly-labelled awareness callout under the relevant region — NOT a row in the einvoicing PD tables, NOT counted as an einvoicing real-PD (that respects the `pd_service_prefixes` keep-filter and the manager's "no non-einvoicing PD services" rule). E.g. a `pdfGenerator`, `Prism-Sev1`, or `licensing` Sev1 in `#sev1-engg` that drove an einvoicing print/generate impact. Label it "not an E-Invoicing PD service — for awareness" and link the `#sev1-engg` thread. _(2026-06-30 example: `Prism-Sev1` OOMKill from oversized Notice-Management PDFs — Prism backs einvoicing print/extraction, so flagged as a dependency callout.)_

Bucket into:
- **Real** — per-region "Real" table, all 7 columns.
- **False alerts** — single combined "Noise/False Alerts" table across all in-scope regions (an anomaly fire is often region-X-named but posts to region-Y's PD service after receiver-group re-route). Include `Region` column + a verification quote. 4-column table only (no Fix/Resolution + Action Items).
- **Test** — drop entirely.

**Known noisy rule_ids** for the in-scope regions come from each block's `noisy_rule_ids` (these will likely false-fire every week). Treat a fire matching one of them as a strong false-alert prior, still confirmed via the payload check above.

## Step 4 — Customer-Facing Defects from L3

Read the union of in-scope `l3_channels` for the window, paginate cap 200.

**A CFD = one structured escalation posted by the scope's `l3_workflow_bot`** (e.g. IND/GCC's "Escalate Customer Issues to L3 New 2", `B094B94DUSZ`). These bot posts carry a fixed template — Submitted By · Salesforce Ticket Id · JIRA Link · Product · Environment · User Email · Workspace/PAN/GSTIN · Detailed Description. **Count and harvest ONLY these bot posts.** Ad-hoc human-posted threads (questions, mandate clarifications, broadcasts, digests) are **not** CFDs — no matter how many replies they have. (If a scope's `l3_workflow_bot` is empty in config, fall back to "parent message with `reply_count >= 5`" and state in the doc that the count is a heuristic, not workflow-based.)

For each `l3_workflow_bot` escalation post in the window:
1. **Region + customer come straight from the template** — the `Product` field (e.g. "Einvoice India" / "Einvoice GCC") plus the JIRA project key give the region (`EIOCJ`=IND, `GOCJ`=GCC/KSA, `EOCJ`=EU, `TMALOCJ`/`IMALOCJ`=MY, `MEA`=MEA); the `User Email` / `Workspace` / `Summary` give the customer (map the email domain to a customer name where the token list doesn't already name it).
2. **Read the full thread** (via the bot post's raw `message_ts`) to pull:
   - **Issue** verbatim (one line).
   - **Engineering Owner** = first **engineer** (from the shared `engineers` roster) to ack or post a substantive technical reply. Distinguish from `Submitted By` (the L2 escalator). Never attribute to anyone in `l2_escalators`.
   - **Short-term Fix** — mitigation applied during the incident (often `none`).
   - **Long-term Fix** — permanent fix planned (or "Closed not-a-bug").
   - **Status**:
     - `not-a-bug` reaction + `:white_check_mark:` → **Closed not-a-bug**
     - `:white_check_mark:` only → **Resolved**
     - engineer "closing the thread" near the end → **Resolved** / **Closed not-a-bug** as indicated
     - call scheduled / awaiting customer → **Awaiting customer**
     - no closure signal + last message > 2 days old → **Open**
   - **Slack Thread** permalink — `https://cleartaxtech.slack.com/archives/<l3_channel_id>/p<parent_ts_no_dot>`.
3. **Keep only in-scope regions.** Drop escalations whose Product / JIRA-project maps to a region not in `--scope` (those belong to other on-calls).

Group into one sub-table per in-scope region (header `### <label> — N threads`, where N = the workflow-escalation count). Each row: `# | Customer | Issue | Short-term Fix | Long-term Fix | Engineering Owner | Status | Slack Thread`. Then add:
- **Open CFDs handed over** — the open/awaiting workflow CFDs (customer + ticket).
- **Other customer threads** — a short note listing genuine customer-specific threads discussed in-channel but NOT escalated via the workflow (so the next on-call still sees them), explicitly flagged as not counted as CFDs.

## Step 5 — CubeAPM Critical-API Health (1-hour buckets)

Use `mcp__clarity-cubeapm__query_metrics_instant`. **Region param = `meta.cubeapm_region`** (`in` — all APM metrics route to `apm-default` regardless of logical region; verified via `list_available_regions`).

**Five evaluation timestamps** — each anchor is IST midnight at the END of that week's Sunday (= `00:00 IST` of the following Monday = `18:30 UTC` of the **Sunday**), so each `[7d]` window spans EXACTLY one Mon–Sun IST week:
- `wk_eval = <weekstart>+6d at 18:30 UTC` (end of this week's Sunday) — current week.
- `baseline_eval_w4 = <weekstart>-1d at 18:30 UTC` (most-recent prior week), `w3 = -8d`, `w2 = -15d`, `w1 = -22d` (oldest) — the 4 baseline weeks.

⚠️ **Off-by-one fix (2026-06-30):** the earlier formula (`wk_eval = <weekstart>+7d`, baselines at `-21/-14/-7/0d`) anchored **24h late** — each `[7d]` window captured a Tue→Mon span (dropping the week's Monday, bleeding into the next week's Monday) instead of the labelled Mon–Sun week. The anchor is `18:30 UTC` of the week's **Sunday**, i.e. one day BEFORE the following Monday. Sanity-check by converting each anchor back to IST and confirming the `[7d]` window reads `Mon 00:00 → next-Mon 00:00 IST`. (For weekstart Jun 22: wk=Jun 28 18:30Z, w4=Jun 21, w3=Jun 14, w2=Jun 7, w1=May 31 18:30Z.)

**Lookback:** `[7d:1h]` for current week and each prior week (same query shape, 5 anchor points).

**Why mean-of-4-weeks (not 28d rolling max):** a 28d `max_over_time` baseline is contaminated by any single bad week (the Apr 27 KSA Redis cascade put `v2/einvoices/generate` p99 at 61s — under 28d max, all 4 weeks "remember" 61s). Mean averages the spike with 3 normal weeks (~17-28s → ~41s baseline) and still catches sustained degradation (4 bad weeks → high mean).

### 5a — Critical-API table

Rows = the union of every in-scope block's `generate_endpoints` (with a Region column). For KSA the span path is on `<service>` per its config; for IND it's split across einvoicingbe + integrations services; for other regions, whatever its config lists.

Per endpoint compute 6 numbers + 1 flag (`{...}` = the endpoint's `service` + `span_name` from config, `span_kind="server"`):

| Column | Query shape (PromQL) | Eval time(s) |
|---|---|---|
| Mean wk (ms) | `1000 * sum by (service,span_name) (rate(cube_apm_latency_sum{...}[7d])) / sum by (service,span_name) (rate(cube_apm_latency_count{...}[7d]))` | wk_eval |
| Mean 4w avg (ms) | same shape, `[28d]` rate window — legacy 28d call-weighted aggregate | baseline_eval_w4 |
| p99 max-1h wk (s) | `max_over_time(histogram_quantiles("phi", 0.99, sum by (vmrange,service,span_name) (rate(cube_apm_latency_bucket{...}[1h])))[7d:1h])` | wk_eval |
| **p99 max-1h 4w mean (s)** | **same `[7d:1h]` query at all 4 baseline anchors, then average the 4 results per endpoint** | w1, w2, w3, w4 |
| Err% wk | `100 * sum (rate(cube_apm_calls_total{..., status_code="ERROR"}[7d])) / sum (rate(cube_apm_calls_total{...}[7d]))` | wk_eval |
| **Err% 4w mean** | **`max_over_time(((sum(rate(err)) / sum(rate(total))) * 100)[7d:1h])` at all 4 baseline anchors, then average** | w1, w2, w3, w4 |
| Outlier? | `yes` if `wk > 1.5 × 4w_mean` on EITHER p99 OR err%; else `no` | — |

**Query count:** ~8 instant queries per service group (4 weeks × 2 metrics). Run in parallel where possible. The nested `avg_over_time(max_over_time(...[7d:1h])[28d:7d])` shortcut times out at the 30s proxy ceiling — run separate weekly queries.

⚠️ **Parallelism limit (2026-06-30):** the **p99 `[7d:1h]` histogram subqueries are heavy** — a broad one (all `SpringController/v[0-9]+` endpoints × 4 services) fetches ~15k series and takes ~20–25s, right at the 30s proxy ceiling. Running the 5 weekly p99 anchors **in parallel makes 4 of 5 time out** (`context deadline exceeded`). Either (a) run the p99 anchors **sequentially**, or (b) **narrow the `span_name=~` regex** to just the endpoints you need (the in-scope `generate_endpoints` + the top-slowest/error candidates), which drops each query to <10s so a few can run concurrently. The err%/calls queries use `calls_total` (no histogram buckets), are light (~2-4s), and parallelize fine. Recommended flow: 1 broad p99 + 1 broad err% at `wk_eval` (to discover the top-3 candidates), then narrow-regex p99 + err% across the 4 baseline anchors.

Render as one HTML table (wrapped in `<div class="scroll">`): API, Region, Mean wk (ms), Mean 4w avg (ms, legacy 28d aggregate), p99 max-1h wk (s), p99 max-1h 4w mean (s), Err% wk, Err% 4w mean, Outlier?.

**Baseline note (always include below the table):** the 4w mean dilutes single-week outage spikes; the legacy Mean (ms) column still uses 28d call-weighted aggregate — flag with ⚠ any row where it looks artificially high from a brief past cascade dominating a small endpoint's 28d call total.

**If zero outliers → state "0 outliers; dropping Outlier Deep-Dive section per the rule" and OMIT the deep-dive subsection.** Don't fake-fill.

### 5b — Per-region Top 3 Slowest + Top 3 Error-Prone

For each in-scope region, two tables (slowest, error-prone), min-calls floor ≥ 5,000/week (filters sparse-data noise). Use the region's `topk_service_regex`:

**Top 3 slowest (region R):**
```promql
topk(3, max_over_time(histogram_quantiles("phi", 0.99,
  sum by (vmrange, service, span_name) (rate(cube_apm_latency_bucket{
    service=~"<R.topk_service_regex>",
    span_kind="server",
    span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[1h])))[7d:1h])
  and on (service, span_name) (
    sum by (service, span_name) (increase(cube_apm_calls_total{
      service=~"<R.topk_service_regex>",
      span_kind="server",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[7d])) >= 5000))
```

**Top 3 error-prone (region R):**
```promql
topk(3, max_over_time(
  ((sum by (service, span_name) (rate(cube_apm_calls_total{
      service=~"<R.topk_service_regex>",
      span_kind="server", status_code="ERROR",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[1h]))
   / sum by (service, span_name) (rate(cube_apm_calls_total{
      service=~"<R.topk_service_regex>",
      span_kind="server",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[1h]))) * 100)[7d:1h])
  and on (service, span_name) (
    sum by (service, span_name) (increase(cube_apm_calls_total{
      service=~"<R.topk_service_regex>",
      span_kind="server",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[7d])) >= 5000))
```

For each top-3 entry pull the 4w mean baseline (same 4-anchor average as 5a). Include per-week breakdown in Pattern (`Per-week: W1=Xs, W2=Ys, W3=Zs, W4=Ws`).

Pattern verdict:
- `Chronic` — wk ≈ 4w mean (0.85×–1.15×)
- `Chronic (slight regression)` — 1.15× ≤ wk < 1.5×
- `Chronic (slight improvement)` — 0.67× < wk ≤ 0.85×
- `NEW — Nx worse` — wk > 1.5× 4w mean (N = wk / 4w_mean, 1 decimal)
- `Improvement` — wk < 0.67× 4w mean
- `Chronic (highly variable)` — per-week values span >5× range; mean unrepresentative, flag unstable
- `Sparse-data noise` — total errors < 50 in the week despite ≥5k floor

Render each as HTML: #, API, Service, p99 wk (or Err% wk), p99 4w mean (or Err% 4w mean), Pattern.

## Step 6 — Compose Key Takeaways

Under the top-3 tables, a `**Key takeaways:**` block, 3-5 bullets:
- **Regression clusters.** Multiple endpoints regressing together (esp. same logical family across regions, e.g. `count`/`summary`) → one root-cause bullet, not three.
- **Zombie endpoints.** Sustained 100% err% or 300s+ p99 for ≥4 weeks AND no PD ever firing → surface for the team to confirm if deprecated.
- **1h-vs-15min noise rejection.** If the 1h view dropped endpoints that would have surfaced at 15-min, mention briefly.
- **Improvements.** Chronic-broken endpoints that improved this week.
- **Filter tweaks for next week.** Sparse-data artifacts still leaking → propose min-calls bump / regex tightening.

**Cross-reference PD breaches:** if a top-3 slowest entry coincides in time with a PD fire, note the link in that PD row's Fix/Resolution (Step 3).

## Step 7 — Save and notify

**Resolve the output location from config:** use the **first in-scope block that defines an `output:` override**; otherwise fall back to `meta.output`. (So the default `ind,ksa` run → `meta.output` = `~/Desktop/e-invoicing-be`; a single `eu`/`my`/`mea` run → that scope's override = `~/Desktop/einvoicing-core`.) Build the path as `<output.repo_path>/<output.subdir>/oncall-handover-<weekstart>.md`, expanding `{year}` in `subdir` to the weekstart's year. Create the full parent-dir chain if missing. **No scope suffix on the filename** — the folder path already identifies the region (e.g. `.../docs/oncall-handover/eu/oncall-handover-2026-06-08.md`).

Concretely with the shipped config:
- `ind,ksa` (default) → `~/Desktop/e-invoicing-be/oncall-handover/<year>/oncall-handover-<weekstart>.md`
- `eu` → `~/Desktop/einvoicing-core/docs/oncall-handover/eu/oncall-handover-<weekstart>.md`
- `my` → `~/Desktop/einvoicing-core/docs/oncall-handover/my/oncall-handover-<weekstart>.md`
- `mea` → `~/Desktop/einvoicing-core/docs/oncall-handover/mea/oncall-handover-<weekstart>.md`

Prepend this **theme-neutral** `<style>` block (table styling + `.scroll` wrapper) so HTML tables render consistently in VS Code preview, GitHub web, and browsers:

```html
<style>
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
th, td { border: 1px solid rgba(128,128,128,0.35); padding: 6px 10px; vertical-align: top; text-align: left; }
th { font-weight: 600; border-bottom-width: 2px; }
.scroll { overflow-x: auto; }
ul { margin: 0; padding-left: 18px; }
</style>
```

⚠️ **Never hardcode light `background` fills** (e.g. `th{background:#f6f8fa}`, `tr:nth-child(even) td{background:#fbfcfd}`, `code{background:#f0f1f2}`) without an explicit matching text `color`: a dark-themed renderer keeps the light text, so the cells render as light-text-on-light-fill (washed out / unreadable). Let backgrounds inherit the viewer theme; only the border uses a translucent gray that works on any background. (GitHub strips inline `<style>` for security, so this block only affects local/VS Code/browser rendering — GitHub uses its own theme-aware table CSS.)

**Save-only**: write the file and stop. **Do NOT** `git add` / commit / push. Both output repos (`e-invoicing-be`, `einvoicing-core`) are shared team code repos — handover commits pollute PR/changelog views. The outgoing on-call decides branching + commit cadence.

Print to the user:
- Doc path (absolute).
- Summary line: `Scope: <labels> · Real PDs: <n> · False alerts: <n> · Open CFDs: <n> · Outliers: <n>` (per-region counts where useful).
- Verification reminder: "Outgoing on-call must verify each PD's status, each CFD's owner/status, and the metrics interpretations BEFORE passing to next on-call. Edit the file directly — Action Items column is a markdown task list; add `- [ ] item` rows in the source MD."

Do **not** auto-send to anyone or auto-update any Slack on-call alias.

## Quirks (codified from the May 2026 PoC, region-agnostic unless noted)

- **CubeAPM region param is `meta.cubeapm_region` (`in`)** for ALL APM queries — KSA/MEA service metrics live in the `apm-default` cube (verified via `list_available_regions`). `ksa`/`mea` regions are for *logs* routing only.
- **CubeAPM uses `vmrange` not `le` for histograms** — for p99 use `histogram_quantiles("phi", 0.99, sum by (vmrange, ...) (rate(cube_apm_latency_bucket{...}[1h])))` — **plural `histogram_quantiles`** with `"phi"`. Singular `histogram_quantile(0.99, ...)` returns empty. Mean latency = `_sum/_count`.
- **`status_code` label value is `"ERROR"` not `"STATUS_CODE_ERROR"`.** `sight-agent.lookup_apm_metrics` pre-built queries use the wrong value — write PromQL directly.
- **`cube_apm_servicegraph_calls_total` is empty** in this tenant. Fall back to per-peer client-span aggregation for downstream-dependency analysis.
- **`cube_apm_apdex_calls_total` returns empty** for our services. Don't depend on apdex.
- **Spring `dispatcherServlet` quirk** — during cascades, errors bubble pre-routing and get attributed to `WebTransaction/Servlet/dispatcherServlet` instead of the endpoint, so per-endpoint err% reads 0%. Mitigation: the service-level err% in Critical-API catches it; the Top-3 error-prone filter to `SpringController/v[0-9]+/.*` keeps dispatcher noise out.
- **28d × 15-min subquery queries time out** at the 30s proxy ceiling (5 services × 28d × 15-min ≈ 5,000+ series). The 1h bucket keeps these well under the limit.
- **Endpoint label is `span_name`** (format `WebTransaction/SpringController/<path> (<METHOD>)`), service label is `service`.
- **PD `list_incidents` API has empty `assignments[]`** — Slack channels are the source of truth for who-handled-what.
- **Slack permalinks must use the real `message_ts`** (e.g. `1779497223.046859` → `p1779497223046859`, dot stripped, micros NOT zero-padded). Never compute the ts from a parsed IST timestamp — past 5h30 / off-by-minute link bugs. See Step 2.
- **Slack `from:@me` doesn't work** — use `from:<@USERID>` angle-bracket form, or `in:<@USERID>` for self-DMs.
- **Sev1 PDs always post to the shared `#sev1-engg` (where the human cause bridge happens); they MAY also mirror to the per-region alert channel.** E.g. the `[EInv-GCC] Zatca … Sev1` fires posted to BOTH `#sev1-engg` and `#einv-gcc-alerts`; the per-region copy was bot-only while the cause was in `#sev1-engg` (so the earlier "Sev1 goes to `#sev1-engg` *only*" was wrong — they can appear in both, same incident but a different `message_ts` per channel). Always read the `#sev1-engg` thread for the cause (Step 3 item 5). Sev2 PDs go to the per-region alert channel (config `alert_channels`).
- **`#sc-reverse-einvoice-pagerduty-alerts` is reverse-einvoice (different team)** — never include.
- Region-specific routing gaps (e.g. IND IRP → Coralogix only, zero PD posts on `#irp-prod-alerts`) live in each scope's config `notes` — surface them as prose callouts, not table rows.

## Don't

- Don't include licensing-service / DevOps / Altinity / DBA / MongoProd / ITR-alerts / Business Platform Alerts PDs, even when the underlying app is einvoicing-related (manager rejected non-einvoicing PD services in the May 2026 review). The `pd_service_prefixes` keep-filter enforces this.
- Don't include regions that aren't in `--scope`. (This is the OPPOSITE of the old IND/KSA-only rule — the skill is now multi-region, but only the requested scopes, so each on-call owns their slice and CFDs/PDs for other regions get dropped.)
- Don't trust memory entries over verified incident threads. Read the actual thread for root cause; memory may be stale or about a different incident.
- Don't auto-send the doc anywhere; don't auto-commit/push into the output repo.
- Don't include test alerts (planned routing tests) — drop entirely.
- Don't claim a PD is connected to a previous outage without verifying timestamps + alert payload + thread content.
- Don't add an "Action items handed to next on-call" summary section — Action Items live per-PD-row (Step 3).
- Don't add a verification-reminder footer to the doc body — the reminder is printed to the user (Step 7) only.
- Don't fabricate Slack permalinks (Step 2 — must use raw `message_ts`).
- Don't run a scope whose config block is unpopulated (`PENDING DISCOVERY` / empty channels) — tell the user to fill `data/scopes.yaml` first.
- Don't keep a Critical-API "Outlier Deep-Dive" subsection when 0 outliers triggered.
- Don't use 15-min buckets for the metrics tables — 1h is the right granularity for sustained-anomaly handover (verified May 2026).
- Don't auto-pick the in-progress week — weekstart is the most recent COMPLETE Mon–Sun week (Step 1).
- Don't conclude a Sev1 had "no human investigation" from the per-region channel alone — its cause is almost always in `#sev1-engg` (Step 3 item 5). Cross-read it before writing Fix/Resolution.
- Don't merge two fires of the same alert title into one row when their threads show different root causes (Step 3 item 4).
- Don't run the p99 `[7d:1h]` anchors in parallel over all endpoints — 4 of 5 time out. Sequential, or narrow the `span_name` regex (Step 5a parallelism note).

## Verifiable success criteria

- Output saved to the config-resolved per-scope path (IND/KSA → `e-invoicing-be/oncall-handover/<year>/`; EU/MY/MEA → `einvoicing-core/docs/oncall-handover/<scope>/`), filename `oncall-handover-<weekstart>.md`, parent dirs created.
- Every PD row has 7 columns: Severity | Count | Incident | PD Service | Slack Thread | Fix / Resolution | Action Items.
- Every PD permalink uses the real `message_ts` (sub-second micros present, not `000000`).
- Critical-API table has one row per in-scope `generate_endpoint` (5 KSA + 4 IND for the default scope). Baseline header reads "p99 max-1h 4w **mean** (s)" / "Err% 4w **mean**".
- If 0 outliers: Outlier Deep-Dive omitted entirely.
- One pair of Top-3 tables (slowest, error-prone) per in-scope region, with the `≥5,000 calls/week` filter.
- Key takeaways cites specific endpoints, `Nx worse` regressions, and a regression-cluster hypothesis if multiple endpoints moved together.
- Only the requested `--scope` regions appear; no other-region PDs/CFDs leak in.
- Output path printed to user; nothing auto-sent or committed.

## Coda push (REMOVED 2026-05-25)

Previously Step 8 pushed the doc to Coda doc `LRUx2GW3fq` via `scripts/coda_push_handover.py`. **Deprecated** — save locally only. The script + `data/coda_table_widths.yaml` remain for reference; the skill no longer invokes them. To re-enable, restore the auto-invocation here and update `HEADER_SIG_TO_KEY` in the script for the current 7-column PD table + metrics tables.
