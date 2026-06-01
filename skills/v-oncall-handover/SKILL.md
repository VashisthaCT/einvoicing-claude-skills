---
name: v-oncall-handover
description: Draft a weekly on-call handover doc for E-Invoicing service (IND + KSA). Pulls verified PD bot incidents from #sev1-engg / #einv-gcc-alerts / #e-invoicing-pds, reads each PD's thread to extract Fix/Resolution + Action Items, harvests customer-facing L3 threads from #einvoice-l3-support, and computes Critical-API Health (9 generate endpoints) + per-region Top-3 slowest/error-prone APIs via CubeAPM (1-hour buckets). Output: ~/Desktop/e-invoicing-be/oncall-handover/2026/oncall-handover-<weekstart>.md. Drafts only — outgoing on-call MUST verify everything before passing to next on-call.
---

You are drafting Vashistha's weekly E-Invoicing on-call handover doc. Run every Monday morning before the handover meeting. Default scope: India + KSA only.

## Args

- `--week-start <YYYY-MM-DD>` (optional) — Monday IST of the week to document. Default: previous Monday relative to today.
- `--outgoing <name>` (optional) — outgoing primary on-call. Default: `Vashistha Garg (PagerDuty)`.
- `--shadow <name>` (optional) — outgoing shadow on-call (intern, L3 threads). Omit if no shadow.
- `--out <path>` (optional) — output markdown path. Default: `~/Desktop/e-invoicing-be/oncall-handover/2026/oncall-handover-<weekstart>.md`. Create the `2026` directory if missing.

## Output structure (the doc the manager treats as source of truth)

```
# Mon <date> → Sun <date>

## PagerDuty Incidents — KSA
[table: Severity | Count | Incident | PD Service | Slack Thread | Fix / Resolution | Action Items]
Incident column: 1-2 sentences, layman terms (no rule_ids, no JedisPool, no `cube.kind=static` etc). Mention day-of-week if useful.
Fix / Resolution column: auto-populated from thread reading (Step 3). 2-4 sentences. Capture who diagnosed root cause, who acted, how it closed (auto-resolve vs human-resolve), any deployed fix.
Action Items column: markdown task list (`- [ ] item`) inside an HTML `<ul><li>` (renders in both VS Code preview and GitHub). Auto-populated where the thread surfaced concrete follow-ups; otherwise `_(none — add as discovered)_`. The on-call person edits the source MD directly to add items.

## PagerDuty Incidents — India
[same 7 columns as KSA, or "None this week" + IRP-routing-gap note]

## PagerDuty Incidents — Noise/False Alerts
[combined IND + KSA false alerts in one table: Region | Count | Alert | PD Service]
(omit section if zero)

## Customer-Facing Defects (CFDs)
### KSA — N threads
[Customer | Issue | Short-term Fix | Long-term Fix | Engineering Owner | Status | Slack Thread]
### India — N threads
[same]

## Critical-API Health: generate paths (KSA + IND)
[table — all 9 generate endpoints (5 KSA + 4 IND) with mean wk vs 4w, p99 max-1h wk vs 4w mean, err% wk vs 4w mean, outlier flag if wk > 1.5× 4w mean]

## Top 3 Slowest + Top 3 Error-Prone APIs (per region, this week vs 4w mean)
### KSA — Top 3 slowest (p99 max in 1h)
### IND — Top 3 slowest (p99 max in 1h)
### KSA — Top 3 error-prone (max err% in 1h)
### IND — Top 3 error-prone (max err% in 1h)

[Each table: # | API | Service | p99 wk (s) or Err% wk | p99 4w mean or Err% 4w mean | Pattern (chronic / NEW Nx worse / improvement / sparse-data noise / chronic-highly-variable)]

### Key takeaways
- [bullets — count/summary regression clusters, zombie endpoints, 1h-vs-15min noise rejection notes, filter tweaks for next week]
```

Reference: `/tmp/oncall-handover-test/2026/oncall-handover-2026-05-18.md` is the canonical example output (week May 18-24, 2026, generated during the 2026-05-25 redesign).

## Step 1 — Compute the week window

If `--week-start` not given: compute previous Monday in IST (today if today is Monday, else most recent past Monday).

```
start_ist = <weekstart>T00:00:00+05:30
end_ist   = <weekstart>+7dT00:00:00+05:30
start_utc = start_ist - 5h30m
end_utc   = end_ist - 5h30m
```

For Slack `oldest`/`latest`, use Unix-second `.000000` strings.
For PagerDuty `since`/`until`, use ISO 8601 UTC.
For CubeAPM `start`/`end`, use ISO 8601 UTC. `step=900`.

## Step 2 — Harvest PagerDuty bot posts (Slack-first, PD API for verification only)

PD `list_incidents` API has empty `assignments[]` for our team — useless for attribution. Slack PD-bot posts are the source of truth for who-handled-what.

Read these channels:
- `#sev1-engg` (C08F1GJ9Z24) — cross-team Sev1 PD bot
- `#einv-gcc-alerts` (C03L955GFD5) — KSA `[E-Invoicing-GCC]` Sev2 PD bot
- `#e-invoicing-pds` (C0209C9E153) — IND `[E-Invoicing-Ind]` PD bot

Use `slack_read_channel` with `oldest`/`latest`, paginate via cursor, cap 300/channel.

For every PagerDuty bot message extract:
- **Message TS (raw, with microseconds)** — capture `message_ts` from the Slack response verbatim (e.g. `1779497223.046859`). **Do NOT synthesize this from the IST timestamp string** — two failure modes are confirmed:
  1. **Microseconds zero-padding**: real Slack `ts` values always have non-zero micros (e.g. `.046859`). Constructing `p<unix_seconds>000000` produces a wrong link that lands near but not on the message.
  2. **IST→UTC timezone bug**: if you parse `02:22:43 IST` from the message body and compute unix as if it were UTC, you get a link that's 5h30 ahead of the real message. Real conversion is `02:22:43 IST → 20:52:43 UTC (previous day) → unix 1779310363`. Always use the API-returned `message_ts` directly.
- IST timestamp (convert raw ts → `%a %b %d %H:%M IST` for display only — NOT for link construction).
- PD Service (verbatim, e.g. `[E-Invoicing-GCC] Proactive Alerts Sev1`)
- Urgency (`High` / `Low`)
- Title (verbatim)
- **Reply count** — capture from Slack response (used to gate whether thread-read is worth doing in Step 3; threads with 0 replies are PD-bot-only and skip the "Fix/Resolution" deep dive).
- Slack thread permalink — construct as `https://cleartaxtech.slack.com/archives/<channel_id>/p<seconds><6-digit-micros>` from the raw ts. E.g. `ts=1779497223.046859` → `p1779497223046859`. Strip the dot, do not zero-pad.

**Filter strictly:** keep only PD services starting with `[E-Invoicing-` or `[EInv-`. Drop:
- `ITR-alerts` (different team)
- `Business Platform Alerts *` (different team — even when title mentions IRP / `kramer-prod-irp-*`)
- `DevOps Alerts *`, `Altinity *`, `DBA Infra *`, `Data Platform *`, `MongoProd *` (infra)

Note any IND IRP CrashLoopBackOff incidents on `Business Platform Alerts Sev1` in the "India — Real" section as a routing-gap callout (not in the table).

## Step 3 — Verify each PD + extract Fix/Resolution + Action Items

For each PD bot post in scope, run all of these checks:

1. **Read its full Slack thread via `slack_read_thread`** using the raw `message_ts` captured in Step 2. Pass `limit=100` (or more if reply count > 100). This serves three purposes:
   - **(a) False-alert filter.** If any human reply contains the verbatim text "false alert" or "test alert" → bucket as FALSE / TEST.
   - **(b) Fix/Resolution column.** Extract 2-4 sentences capturing:
     - **Root-cause diagnosis** — who identified the cause and what they found (e.g. "Yash Doshi diagnosed: Marico bulk EWB prints + AP India scheduled cron saturated Redis").
     - **Who acted** — engineering owner who drove the troubleshooting (NOT the PD acknowledgment-only person, NOT the L2 escalator).
     - **How it closed** — auto-resolved by CubeAPM (no human action) vs human-resolved (mark-resolve + silence) vs fix-deployed (PR/config change merged during incident).
     - **Outstanding state** — if the PD was force-closed but the underlying cause persists, flag it (e.g. "Ayush mark-resolved + 3hr silence; memory came down naturally but root cause unaddressed").
   - **(c) Action Items column.** Extract concrete follow-ups from the thread. Look for:
     - Direct mentions: "we should X", "need to check Y", "follow up with Z"
     - `@mention` callouts asking someone to investigate or confirm
     - Deferred fixes: "going live tomorrow", "PR pending review", "rollout next week"
     - Open questions from the thread that didn't get resolved
   - Format Action Items as a markdown task list inside `<ul><li>` for the table cell:
     ```html
     <ul>
       <li>[ ] Concrete action item with @owner or context</li>
       <li>[ ] Another item</li>
     </ul>
     ```
   - If the thread had no concrete follow-ups → use `<ul><li>[ ] _(none — add as discovered)_</li></ul>` placeholder. The on-call person edits the MD source directly to add items; the rendered preview auto-updates.
2. **Auto-resolve pattern.** If TTR < 5 min, no human ack, no human reply → likely FALSE flap. Confirm via #4.
3. **Pull alert payload** via `mcp__clarity-pagerduty__get_incident_alerts`:
   - If `cube.kind = anomaly` and query is `<> 4` or `< 4` on call-rate → traffic-dip detector. If `value < anomaly_prediction` → FALSE (just a quiet period). If during a known outage window → REAL (traffic genuinely dropped).
   - If alert annotation contains `Test alert` or `Notification test` → TEST.
   - If alert is `cube.kind = static` (e.g. `Error percentage (High)` rule_id 1009, `> 10%` or `> 25%`) → REAL static-threshold breach.
4. **Same-pattern repeats:** group consecutive alerts with the same title pattern → one row with `Count = N`, time range as `start – end`. Merge Fix/Resolution + Action Items across the group (deduplicate).

Bucket into:
- **Real** — goes in the per-region "Real" table with all 7 columns including Fix/Resolution + Action Items.
- **False alerts** — goes in the **single combined "Noise/False Alerts" table** (covers both IND and KSA — many anomaly fires are KSA-named but post to the IND PD service after the receiver-group re-route). Include a `Region` column. Add a verification quote. False-alert rows do NOT need Fix/Resolution + Action Items columns (4-column table only).
- **Test** — drop entirely (planned, not noise to surface).

Known noisy CubeAPM rules (will likely fire false alerts every week):
- `rule_id 1153` — `EInvoicing KSA anomaly` (KSA call-rate dip)
- `rule_id 1151` — `E Invoicing India Integration anomaly` (IND integrations call-rate dip)
- `rule_id 1150` — `E-Invoicing India Anomaly` (IND legacy call-rate dip)

## Step 4 — Customer-Facing Defects from L3

Read `#einvoice-l3-support` (C055ABMAVCL) for the window, paginate cap 200.

For each parent message with `reply_count >= 5`:
1. Identify customer (look for known names: MAF, Mitsuba, Tabby, Swiggy, Eicher, Salam, Zamil, Alkhorayef, Gulf Cryo, Country Delight, Pidilite, etc., or any company-name-like token in the parent message). Customer name often appears in the email/PAN/GSTIN field of the L2-escalation template, not in the "Submitted By" field.
2. **Read the full thread** — required for every CFD. Pull:
   - **Issue** verbatim (one line).
   - **Engineering Owner** = the **first engineer (not L2 escalator) to ack the thread or post a substantive technical reply.** Distinguish from `Submitted By` in the parent — that's the L2 person who escalated, NOT the engineer. The L2 names (Kuwar Siddharth Singh, Sarfaraz, Ashutosh Barik, Kareem.Nawaz, Prashant K, Raksith Jain etc.) are NOT engineering owners. Engineers in our team include Sushant Gupta (`U0A75MW4VPY`), Yash Doshi (`U08C0D2ULSD`), Ayush Jain (`U0ABBKV5QDU`), Aquib Jawed (`U01FSG6S057`), Vinay Hegde (`UTUA6G9R6`), Vinay Gupta (`U01JN2XUQSC`), Gajjala Kullayappa (`U02TGQ66E3B`), Om Anil, Vaibhav Pawar, Shivkumar, Siddhant — pick whichever one drove the troubleshooting.
   - **Short-term Fix** — what mitigation was applied during the incident (often `none` if no immediate workaround, just diagnosis).
   - **Long-term Fix** — what permanent fix is planned (or "Closed not-a-bug" if no fix needed).
   - **Status** — derive from thread closure:
     - `not-a-bug` reaction on parent + `:white_check_mark:` reaction → **Closed not-a-bug**
     - `:white_check_mark:` reaction only → **Resolved**
     - "closing the thread" or "closing this thread" message from an engineer near the end → **Resolved** or **Closed not-a-bug** (whichever the engineer indicated)
     - Customer call scheduled / awaiting customer response → **Awaiting customer**
     - No closure signal + last message > 2 days old → **Open**
   - **Slack Thread** permalink — `https://cleartaxtech.slack.com/archives/C055ABMAVCL/p<parent_ts_no_dot>`
3. Filter to KSA + IND only (drop UAE, EU, MY, JO threads — those go to other teams' L3 channels which we don't read).
4. Drop platform-wide threads not specific to einvoicing service (e.g. licensing-service Sev1 affecting all customers).

Group into KSA + India sub-tables. Each row: `# | Customer | Issue | Short-term Fix | Long-term Fix | Engineering Owner | Status | Slack Thread`. List "Open CFDs handed over" at the bottom (just customer names, no details).

## Step 5 — CubeAPM Critical-API Health (9 generate endpoints, 1-hour buckets)

Use `mcp__clarity-cubeapm__query_metrics_instant`. Region param: `in` for everything (APM metrics route to `apm-default` cube regardless of logical region — verified via `list_available_regions`).

**Five evaluation timestamps:**
- `wk_eval = <weekstart>+7d at 18:30 UTC` (end of Sunday IST) — for current-week stats
- `baseline_eval_w1 = <weekstart>-21d at 18:30 UTC` (end of 4-weeks-ago Sunday) — for week 1 of baseline
- `baseline_eval_w2 = <weekstart>-14d at 18:30 UTC`
- `baseline_eval_w3 = <weekstart>-7d at 18:30 UTC`
- `baseline_eval_w4 = <weekstart> at 18:30 UTC` (end of last-week Sunday = start of current week) — for week 4 of baseline

**Lookback window:**
- `[7d:1h]` for both current week and each of the 4 prior weeks (each query is the same shape, just evaluated at 5 different anchor points)

**Why mean-of-4-weeks (and not 28d rolling max):** the 28d `max_over_time` baseline is contaminated whenever a single bad week sits inside the window. Apr 27 KSA Redis cascade put `v2/einvoices/generate` p99 at 61s for that one week; under the 28d max baseline, all 4 weeks "remember" that 61s. Under mean-of-4-weeks, the 61s is averaged with the other 3 normal weeks (~17-28s), yielding a 41s baseline that correctly distinguishes the cascade-week from typical behavior. Mean dilutes single-week spikes but still catches sustained-trend degradation (4 weeks of bad data → 4 high values → high mean).

### 5a — Critical-API table (9 rows)

The 9 generate endpoints:
- **KSA (5)** on `einvoicingbe-prod-oci-http` (server span): `v2/einvoices/generate (POST)`, `v2/einvoices/generate-with-file (POST)`, `v2/einvoices/generate/async (POST)`, `v2/einvoices/generate-with-file-offline (POST)`, `v2/einvoices/generate-with-base64-offline/async (POST)`
- **IND einvoicingbe (2)** on `einvoicingbe-prod-http`: `v1/einvoices/generate (POST)`, `v1/ewaybill/generate (POST)`
- **IND integrations (2)** on `einvoicing-integrations-prod-http`: `v2/eInvoice/generate (PUT)`, `v2/eInvoice/ewaybill (POST)`

Per endpoint, compute 6 numbers + 1 flag:

| Column | Query shape (PromQL) | Eval time(s) |
|---|---|---|
| Mean wk (ms) | `1000 * sum by (service,span_name) (rate(cube_apm_latency_sum{...}[7d])) / sum by (service,span_name) (rate(cube_apm_latency_count{...}[7d]))` | wk_eval |
| Mean 4w avg (ms) | same shape with `[28d]` rate window — legacy 28d call-weighted aggregate | baseline_eval_w4 |
| p99 max-1h wk (s) | `max_over_time(histogram_quantiles("phi", 0.99, sum by (vmrange,service,span_name) (rate(cube_apm_latency_bucket{...}[1h])))[7d:1h])` | wk_eval |
| **p99 max-1h 4w mean (s)** | **Run the same `[7d:1h]` query at all 4 baseline_eval anchors (w1-w4), then average the 4 results per endpoint.** | baseline_eval_w1, w2, w3, w4 |
| Err% wk | `100 * sum (rate(cube_apm_calls_total{..., status_code="ERROR"}[7d])) / sum (rate(cube_apm_calls_total{...}[7d]))` | wk_eval |
| **Err% 4w mean** | **Run `max_over_time(((sum(rate(err)) / sum(rate(total))) * 100)[7d:1h])` at all 4 baseline_eval anchors, then average.** | baseline_eval_w1, w2, w3, w4 |
| Outlier? | `yes` if `wk > 1.5 × 4w_mean` on EITHER p99 OR err%; else `no` | — |

**Practical query count:** 8 instant queries per service group (4 weeks × 2 metrics) — about 24 queries total (3 service groups × 8). Each completes in 1-5 seconds; run in parallel where possible. Tried `avg_over_time(max_over_time(...[7d:1h])[28d:7d])` nested-subquery shortcut — times out at the 30s proxy ceiling. Run as separate weekly queries instead.

Render as one HTML table (wrapped in `<div class="scroll">`) with columns: API, Region, Mean wk (ms), Mean 4w avg (ms, legacy 28d aggregate), p99 max-1h wk (s), p99 max-1h 4w mean (s), Err% wk, Err% 4w mean, Outlier?.

**Baseline methodology note (always include below the table):** Briefly state that the 4w mean dilutes single-week outage spikes (one bad week of data is averaged with 3 normal weeks). The legacy Mean (ms) column still uses 28d call-weighted aggregate — flag with ⚠ any rows where that column looks artificially high due to a brief past cascade dominating a small endpoint's 28d call total.

**If zero outliers triggered → state "0 outliers; dropping Outlier Deep-Dive section per the rule" and OMIT any deep-dive subsection.** Don't fake-fill.

### 5b — Per-region Top 3 Slowest + Top 3 Error-Prone

Four sub-tables, all with min-calls floor ≥ 5,000 per week (filters sparse-data noise like `v1/settings/print/template`):

**KSA Top 3 slowest:**
```promql
topk(3, max_over_time(histogram_quantiles("phi", 0.99,
  sum by (vmrange, service, span_name) (rate(cube_apm_latency_bucket{
    service=~"einvoicingbe-prod-oci-http|einvoicingbe-prod-oci-bulk-http",
    span_kind="server",
    span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[1h])))[7d:1h])
  and on (service, span_name) (
    sum by (service, span_name) (increase(cube_apm_calls_total{
      service=~"einvoicingbe-prod-oci-http|einvoicingbe-prod-oci-bulk-http",
      span_kind="server",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[7d])) >= 5000))
```

**IND Top 3 slowest:** same shape, swap service to `einvoicingbe-prod-http|einvoicing-integrations-prod-http`.

**KSA Top 3 error-prone:**
```promql
topk(3, max_over_time(
  ((sum by (service, span_name) (rate(cube_apm_calls_total{
      service=~"einvoicingbe-prod-oci-http|einvoicingbe-prod-oci-bulk-http",
      span_kind="server", status_code="ERROR",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[1h]))
   / sum by (service, span_name) (rate(cube_apm_calls_total{
      service=~"einvoicingbe-prod-oci-http|einvoicingbe-prod-oci-bulk-http",
      span_kind="server",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[1h]))) * 100)[7d:1h])
  and on (service, span_name) (
    sum by (service, span_name) (increase(cube_apm_calls_total{
      service=~"einvoicingbe-prod-oci-http|einvoicingbe-prod-oci-bulk-http",
      span_kind="server",
      span_name=~"WebTransaction/SpringController/v[0-9]+/.*"}[7d])) >= 5000))
```

**IND Top 3 error-prone:** same shape, swap services.

For each top-3 entry, also pull the 4w mean baseline. **Same methodology as Critical-API (Step 5a):** run the `[7d:1h]` query at all 4 baseline_eval anchors (w1, w2, w3, w4), then average the per-week values to get the 4w mean. Include the per-week breakdown in the Pattern column (`Per-week: W1=Xs, W2=Ys, W3=Zs, W4=Ws`) so the reader can see whether a high mean is driven by one outlier week or all-4-weeks-consistent.

Compute Pattern verdict:
- `Chronic` — wk ≈ 4w mean (within 0.85× – 1.15× band)
- `Chronic (slight regression)` — 1.15× ≤ wk < 1.5×
- `Chronic (slight improvement)` — 0.67× < wk ≤ 0.85×
- `NEW — Nx worse` — wk > 1.5× 4w mean (compute N = wk / 4w_mean, round to 1 decimal)
- `Improvement` — wk < 0.67× 4w mean
- `Chronic (highly variable)` — annotate when per-week values span >5× range (e.g. KSA `v2/einvoices/count` err%: 7% / 20% / 19% / 76% across 4 weeks). Mean isn't representative; flag as unstable rather than chronic.
- `Sparse-data noise` — even with ≥5k floor, if total errors < 50 in the week → flag

Render each as an HTML table with columns: #, API, Service, p99 wk (or Err% wk), p99 4w mean (or Err% 4w mean), Pattern.

## Step 6 — Compose Key Takeaways (replaces old "Headlines")

Under the four top-3 tables, add a `**Key takeaways:**` block with 3-5 bullets:

- **Regression clusters.** If multiple endpoints regressed simultaneously (especially same logical-endpoint family — e.g. `count`/`summary` across regions), call it out as a single root-cause investigation. One bullet, not three. Example: "Three count/summary endpoints regressed in lockstep (KSA summary p99 32×, IND count p99 16×, IND summary err% 22×) — likely shared DB/index/query-plan root cause. Single follow-up."
- **Zombie endpoints.** Any endpoint with sustained 100% err% or 300s+ p99 for ≥4 weeks AND no PD ever firing on it. Surface for the team to confirm if deprecated.
- **1h-vs-15min noise rejection.** If the 1h view dropped any endpoints that would have surfaced at 15-min, mention briefly (proves the filter is working — transient retry storms vs sustained regressions).
- **Improvements.** Chronic-broken endpoints that improved this week. Worth a positive-trend mention.
- **Filter tweaks for next week.** Sparse-data artifacts still leaking (e.g. settings/print/template) → propose min-calls bump or regex tightening.

**Cross-reference with PD breaches**: If a top-3 slowest entry coincides in time with a PD fire, mention the link in the Fix/Resolution column of the PD row (Step 3 should already have this; double-check).

## Step 7 — Save and notify

Write the composed doc to `~/Desktop/e-invoicing-be/oncall-handover/2026/oncall-handover-<weekstart>.md` (create the `oncall-handover/2026/` directory chain if missing — the parent `~/Desktop/e-invoicing-be/` is the local clone of `ClearTax/e-invoicing-be`, a shared team code repo). Prepend the standard `<style>` block (table styling + `.scroll` wrapper) at the top of the file so HTML tables render with consistent column widths in VS Code preview, GitHub web view, and any browser. Reference: `/tmp/oncall-handover-test/2026/oncall-handover-2026-05-18.md` for the canonical style block.

**Save-only**: the skill writes the file to disk and stops. **Do NOT** auto-`git add` / commit / push it. `e-invoicing-be` is a shared team code repo — every commit there shows up in PR/changelog views, which would pollute history with weekly handover noise. The outgoing on-call decides whether to commit + push (typically on a branch), and when.

Print to the user:
- Doc path (absolute, e.g. `~/Desktop/e-invoicing-be/oncall-handover/2026/oncall-handover-2026-05-18.md`)
- Summary line: `Real PDs: <ksa_real>+<ind_real> · False alerts: <ksa_false>+<ind_false> · Open CFDs: <count> · Outliers: <n>`
- Verification reminder: "Outgoing on-call must verify each PD's status, each CFD's owner/status, and the metrics interpretations BEFORE passing to next on-call. Edit the file directly — Action Items column is markdown task list, just add `- [ ] item` rows in the source MD."

Do **not** auto-send to anyone or auto-update Slack on-call alias.

## Step 8 — Coda push (REMOVED 2026-05-25)

Previously, this step pushed the doc to Coda doc `LRUx2GW3fq` via `scripts/coda_push_handover.py`. **Deprecated** — user directive: save locally to `~/Desktop/e-invoicing-be/oncall-handover/2026/` only, no Coda push.

The script + YAML widths file remain in the repo for reference / future re-enablement, but the skill no longer invokes them:
- `scripts/coda_push_handover.py` — unused
- `data/coda_table_widths.yaml` — unused

If a future use-case needs Coda push back, re-introduce the auto-invocation here and update the `HEADER_SIG_TO_KEY` map in the script to cover the new PD table shape (7 columns: Severity | Count | Incident | PD Service | Slack Thread | Fix / Resolution | Action Items) and the new metrics tables.

## Quirks (codified from the May 2026 PoC)

- **CubeAPM region param is centralized to `in`** for all APM queries (KSA service metrics live in the `apm-default` cube — verified via `list_available_regions`). `ksa`/`mea` regions are for *logs* routing only.
- **CubeAPM uses `vmrange` not `le` for histograms** — for p99, use `histogram_quantiles("phi", 0.99, sum by (vmrange, ...) (rate(cube_apm_latency_bucket{...}[1h])))` — note the **plural `histogram_quantiles`** function with `"phi"` as first arg. The singular `histogram_quantile(0.99, ...)` returns empty. For mean latency, use `_sum/_count` pattern.
- **`status_code` label is `"ERROR"` not `"STATUS_CODE_ERROR"`** for our services. `sight-agent.lookup_apm_metrics` pre-built queries use the wrong value — bypass them and write the PromQL directly.
- **`cube_apm_servicegraph_calls_total` is empty** in this CubeAPM tenant. Fall back to per-peer client-span aggregation if downstream-dependency analysis is needed.
- **`cube_apm_apdex_calls_total` returns empty** for our 5 services — either instrumentation gap or label mismatch. Don't depend on apdex.
- **Spring `dispatcherServlet` quirk** — when errors bubble pre-routing (during cascades), they get attributed to `WebTransaction/Servlet/dispatcherServlet` span instead of the specific endpoint. Result: per-endpoint err% reads 0% during cascade events. Mitigation: the service-level err% in Critical-API table catches it; the Top-3 error-prone tables filter to real `SpringController/v[0-9]+/.*` endpoints so dispatcher noise doesn't dominate.
- **28d × 15-min subquery queries time out** at 30s proxy ceiling when querying 5 services × 28d × 15-min subquery (5,000+ time series). The 1h bucket switch (current design) keeps these well under the limit.
- **Endpoint label is `span_name`** (not `name`/`http_route`/`uri`/`endpoint`). Format: `WebTransaction/SpringController/<path> (<METHOD>)`.
- **Service label is `service`** (not `service_name`).
- **PD `list_incidents` API has empty `assignments[]`** — Slack channels are the source of truth for who-handled-what.
- **Slack permalinks must use the real `message_ts` returned by the API** (e.g. `1779497223.046859`). Construct as `p<seconds><6-digit micros>` with the dot stripped. **Do NOT** zero-pad the micros and **do NOT** compute the ts from an IST timestamp string parsed out of the message body — both have produced 5h30 / 10-min off-by-X-minute permalinks in past runs. See Step 2 for the canonical pattern.
- **Slack `from:@me` doesn't work** — use `from:<@U087T0SHNCC>` angle-bracket form, or `in:<@U087T0SHNCC>` for self-DMs.
- **Sev1 PDs go to `#sev1-engg` only, not the per-region alert channel.** Sev2 PDs go to the per-region alert channel.
- **#irp-prod-alerts has zero PD bot posts** — IRP routes to Coralogix only. India real PD count from E-Invoicing PD services is typically 0; flag IRP routing gap as a follow-up.
- **`#sc-reverse-einvoice-pagerduty-alerts` is reverse-einvoice (different team)** — do not include.

## Don't

- Don't include licensing-service / DevOps / Altinity / DBA / MongoProd / ITR-alerts / Business Platform Alerts PDs in scope, even when the underlying app is einvoicing-related (manager rejected non-einvoicing PD services in the May 2026 review).
- Don't mix EU / MY / BE / UAE / JO into the doc — scope is IND + KSA only.
- Don't trust memory entries (`project_ksa_outage_rca.md` style) over verified incident threads. Read the actual `#sev1-engg` thread for root cause; the memory may be stale or about a different incident.
- Don't auto-send the doc anywhere.
- Don't include test alerts (planned routing tests) — drop entirely.
- Don't claim a PD is connected to a previous outage without verifying timestamps + alert payload + thread content.
- Don't add an "Action items handed to next on-call" summary section. Action Items live per-PD-row in the Action Items column (Step 3); that's the canonical surface.
- Don't add a verification-reminder footer to the doc body. The reminder is printed to the user (Step 7) only — never embedded in the markdown.
- Don't fabricate Slack permalinks (see Step 2 — must use raw `message_ts`).
- Don't `git add` / commit / push the handover MD into `e-invoicing-be` — it's a shared team code repo. Save only; outgoing on-call decides branching + commit cadence.
- Don't keep a Critical-API "Outlier Deep-Dive" subsection when 0 outliers triggered — drop it entirely per the rule. Don't fake-fill with marginal rows.
- Don't use 15-min buckets for the metrics tables — they catch transient retry-storms and create noise. The 1h bucket is the right granularity for sustained-anomaly handover (verified May 2026: dropped 3 transient ewaybill spikes that weren't real regressions).

## Verifiable success criteria

- Output saved to `~/Desktop/e-invoicing-be/oncall-handover/2026/oncall-handover-<weekstart>.md`.
- Every PD row has 7 columns: Severity | Count | Incident | PD Service | Slack Thread | Fix / Resolution | Action Items.
- Every PD permalink uses the real `message_ts` (sub-second micros present, not `000000`).
- Critical-API table has 9 rows (5 KSA + 4 IND). Baseline column header reads "p99 max-1h 4w **mean** (s)" / "Err% 4w **mean**" (not "avg" — methodology note clarifies it's mean of 4 weekly p99-max values, not call-weighted average).
- If 0 outliers: Outlier Deep-Dive section omitted entirely.
- Four per-region Top-3 tables (KSA slowest, IND slowest, KSA error-prone, IND error-prone) with `≥5,000 calls/week` filter applied.
- Key takeaways block cites specific endpoint names, regressions (with `Nx worse` framing), and a regression-cluster hypothesis if multiple endpoints moved together.
- Coda push NOT invoked (deprecated 2026-05-25).
- Output path printed to user.
