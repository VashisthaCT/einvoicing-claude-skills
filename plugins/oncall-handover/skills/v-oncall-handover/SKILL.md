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

Read the config file. **Resolve its path in this order** — a bare relative `data/scopes.yaml` resolves against the session's working directory, which is wrong whenever the user isn't sitting in the plugin folder:

1. `${CLAUDE_PLUGIN_ROOT}/data/scopes.yaml` — set when installed as a plugin. Use this if `CLAUDE_PLUGIN_ROOT` is set.
2. `<repo-root>/plugins/oncall-handover/data/scopes.yaml` — if running inside a clone of this repo (the dir containing `.claude-plugin/marketplace.json`).
3. `~/dev/einvoicing-claude-skills/plugins/oncall-handover/data/scopes.yaml` — last-resort fallback for a bare-copied skill.

If none resolve, stop and tell the user the config is missing — do NOT fall back to hardcoded channels or endpoints.

Resolve `--scope` into the list of scope blocks. From `meta` load: `sev1_channel`, `cubeapm_region`, `output` (default output location), `default_scope`. Load the shared `engineers` roster and `l2_escalators` exclusion list. For each in-scope block, you now have: `label`, `pd_service_prefixes`, (optional) `pd_workload_filter`, `alert_channels`, `l3_channels`, `cubeapm_services`, `generate_endpoints`, `topk_service_regex`, `noisy_rule_ids`, `jira_projects`, (optional) `jira_pass2_filter` (extra JQL for Step 4 pass 2), (optional) `oncall_handle` (used by Step 4b), `customers`, `notes`, (optional) `output` override, and (optional) `alert_format` + `alert_match` — `alert_format` defaults to `pd_bot` when absent; `coralogix` selects the alternate recognizer in Step 2.

**If a requested scope's block is unpopulated** (empty `alert_channels`/`generate_endpoints`, or `notes: PENDING DISCOVERY`): stop and tell the user that scope isn't configured yet, and point them at `data/scopes.yaml` to fill it. Don't fabricate channels/endpoints.

Everywhere below where the legacy doc said "KSA" or "India", read **"each in-scope region, using its config block."** The union of all in-scope `alert_channels` + the shared `sev1_channel` is the set of PD channels to read; the union of `pd_service_prefixes` is the PD-service keep-filter; etc.

## Output structure (the doc the manager treats as source of truth)

One section per in-scope region (in `--scope` order). Template per region `<R>` (use its `label`):

```
# Mon <date> → Sun <date>  ·  Scope: <labels, comma-sep>

## PagerDuty Incidents — <R label>
[table: Severity | Count | Incident | Slack Thread | Fix / Resolution | Action Items]
PD Service is NOT a column — name the region's PD service(s) once in a line beneath the heading. Within one region it barely varies (EU is a single service carrying both urgencies), so a column of it is dead weight on every row.
Incident column: 1-2 sentences, layman terms (no rule_ids, no JedisPool, no `cube.kind=static`). Mention day-of-week if useful.
Fix / Resolution column: auto-populated from thread reading (Step 3). **1-2 sentences.** Root cause, who acted, how it closed (auto-resolve vs human-resolve vs fix-deployed). Don't narrate the investigation — the thread link carries the detail for anyone who needs it.
Action Items column: markdown task list (`- [ ] item`) inside an HTML `<ul><li>`. Auto-populated where the thread surfaced concrete follow-ups; otherwise `<ul><li>[ ] _(none — add as discovered)_</li></ul>`. On-call edits the source MD directly to add items.
(If a region had no real PDs: "None this week" + any routing-gap note from its config `notes`.)

## Noise / False Alerts
ONE line per in-scope region — not a table:
`**<R label>** — N false alerts (rule_ids <ids>). <one clause naming the dominant pattern.>`
The per-alert breakdown was never acted on; the count plus the rule_ids is what tells the next on-call whether a rule still needs tuning. (Omit the section entirely if zero across all regions.)

## Customer-Facing Defects (CFDs)
### <R label> — N raised this week
[Customer | Issue | Fix | Engineering Owner | Status | Slack Thread]
Short-term Fix and Long-term Fix collapse into ONE `Fix` column — in practice short-term was `none` on most rows and the pair read as padding. Where both genuinely exist, write `<short-term> → <long-term>`.

### <R label> — closed this week, raised earlier (N)
[Ticket | Customer | Issue | Closed as | Engineering Owner | Slack Thread]
Escalations whose thread predates this window but whose JIRA ticket reached a done status during it (Step 4, pass 2). Omit the sub-section when N = 0.

## Tagged outside support — N tags in M channels
[Channel | Who | Ask | Type | Answered by | Status | Link] — produced by the sibling skill **v-oncall-tags** (Step 4b). Open and unanswered first; FYI/cc-only tags and daily reminder bots collapse to one line. Omit when N = 0.

## Critical-API Health: generate paths
[table: API | Region | p99 max-1h wk (s) | p99 4w mean (s) | Err% wk | Err% 4w mean | Outlier?]
The two legacy Mean (ms) columns are **dropped** — they used a 28d call-weighted aggregate that one past cascade distorts, always shipped with a ⚠ caveat, and nobody acted on them. p99 and err% are what drive decisions.
If NO endpoint is an outlier, replace the table with one line: `All <N> generate endpoints within 1.5× their 4-week baseline on p99 and error rate.`

## Top 3 Slowest + Top 3 Error-Prone APIs
Render a region's pair of tables **only when that region has at least one entry that is new or worsening** (wk > 1.5× its 4w mean). A chronically-slow-but-flat endpoint is not news every single week — collapse those into one line: `Chronic, flat vs baseline: <api> (p99 <n>s), <api> (err <n>%).`
### <R label> — Top 3 slowest (p99 max in 1h)      [only when the gate above is met]
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

PD `list_incidents` API has empty `assignments[]` for our team — useless for attribution. The Slack alert posts are the source of truth for who-handled-what, in whichever format the region uses.

**Channels to read** = `meta.sev1_channel` (shared) + the union of every in-scope block's `alert_channels`. Use `slack_read_channel` with `oldest`/`latest`, paginate via cursor, cap 300/channel.

**Two alert formats exist — check each scope's `alert_format` before parsing.** Default is `pd_bot`. A scope set to `coralogix` does NOT receive classic PagerDuty-incident-bot posts, so everything below about a "PD Service" field simply does not apply to it, and parsing it as `pd_bot` silently yields zero alerts for that region every single week.

For every PagerDuty bot message (`alert_format: pd_bot`) extract:
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

**`alert_format: coralogix` (Malaysia today).** Some regions never get a PagerDuty-incident-bot post at all. Their alerts are raised in Coralogix, posted to the region's Slack channel in Coralogix's own layout, and fanned out to PagerDuty separately — so the Slack message carries **no PD Service field**, and the strict filter above would drop every one of them, leaving that region reading "None this week" forever. For a scope whose `alert_format` is `coralogix`:

- **Identify an alert** by the tokens in `alert_match` (config), not by a PD Service prefix — e.g. a `[CRITICAL]` / `[FIRING]` / `[ERROR]` marker plus the region's application name (`ct-my-prod`) or alert-name tokens (`Einvoicing Core My`, `Routing MY`).
- **Severity** maps from the Coralogix priority, not PD urgency: `P1` / `CRITICAL` → Sev1-equivalent, `P2` / `ERROR` → Sev2-equivalent. Record which mapping you used.
- **PD Service** — there is none in the message. Use the region's `pd_service_prefixes[0]` as the display value so the doc stays consistent across regions, and note once under the table that this region's pages originate in Coralogix.
- Everything else is unchanged: raw `message_ts` for permalinks, reply-count gating, the Step 3 thread dive, and the `noisy_rule_ids` false-alert check all work the same.
- **On the first run for such a region, print how many messages matched `alert_match` versus how many were in the channel.** A match count of 0 against a non-empty channel means the tokens are wrong — say so loudly rather than emitting "None this week", which is indistinguishable from a genuinely quiet week and is exactly how a region goes unmonitored without anyone noticing.

If a region's config `notes` flags a routing gap (e.g. IND IRP CrashLoop on `Business Platform Alerts Sev1`), surface it as a prose callout in that region's section, not in the table.

## Step 3 — Verify each PD + extract Fix/Resolution + Action Items

For each in-scope alert post, run all checks. **This applies to both `alert_format`s** — a Coralogix-format alert (Step 2) gets the same thread dive, false-alert filter, Fix/Resolution and Action Items treatment as a PD-bot post. Where a check below names a PD-only field (urgency, PD Service), use the Coralogix equivalent Step 2 recorded.

1. **Read its full Slack thread via `slack_read_thread`** using the raw `message_ts` from Step 2. `limit=100` (more if reply count > 100). Three purposes:
   - **(a) False-alert filter.** Any human reply with verbatim "false alert" or "test alert" → bucket FALSE / TEST.
   - **(b) Fix/Resolution column** — **1-2 sentences** (tightened 2026-09-21; the thread link carries the detail): **root-cause diagnosis** (who identified the cause + what they found), **who acted** (engineering owner who drove troubleshooting, NOT the PD-ack-only person, NOT the L2 escalator), **how it closed** (auto-resolved by CubeAPM / human mark-resolve+silence / fix deployed), **outstanding state** (if force-closed but cause persists, flag it).
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

   ⚠️ **`alert_format: coralogix` regions have no `cube.kind`** — the alert was raised in Coralogix, not CubeAPM, so this payload check does not apply and `get_incident_alerts` may not resolve the post to a PD incident at all. For those, judge real-vs-false from: the thread's own human replies (#1a), the auto-resolve pattern (#2), the region's `noisy_rule_ids`, and the Coralogix priority (a `P2`/`ERROR` that auto-cleared in minutes with no human reply is the usual flap). **Say in the doc that these were classified without payload verification** — and note that a region with an empty `noisy_rule_ids` (MY and MEA today) has no false-alert filter at all yet, so its counts will run high until those ids are captured from a live run.
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
   - **Fix** — one column. The permanent fix, or "Closed not-a-bug". Only when a distinct mitigation was applied first does it become `<short-term> → <long-term>`; don't write `none → <fix>`.
   - **Status — read it from JIRA, not from reactions.** The bot template carries a `JIRA Link`. Resolve that ticket with `mcp__de387922-450f-43fc-88e8-473a7b0c3961__getJiraIssue`. **`statusCategory` decides open vs closed** — every project spells its workflow differently, and the category is the one field Jira guarantees. **The status NAME carries the close reason** — verified 2026-10-05: in EIOCJ/GOCJ the Done transition usually leaves `resolution` empty (66 of 118 EIOCJ Done tickets), and the real reason lives in names like `Gov Issues`, `Invalid / Too Old`, `Cannot Reproduce`, `Duplicate`. So:
     - `Done` → **Closed — `<status name verbatim>`** (append the resolution only when it is non-empty). Write the name as-is; readers understand "Invalid / Too Old" or "Gov Issues" without a mapping table, and a table would drift as workflows change.
     - `In Progress` → **Open (in progress)**
     - `To Do` → **Open**

     Thread signals override in one direction only: a thread clearly saying *call scheduled* / *awaiting customer input* → **Awaiting customer**, even while the ticket is still open.
   - **Reaction fallback** — use ONLY when the template carries no JIRA Link, the link won't parse, or the Atlassian MCP is unavailable. Then: `not-a-bug` + `:white_check_mark:` → Closed not-a-bug; `:white_check_mark:` only → Resolved; an engineer closing the thread → as indicated; no closure signal and last message > 2 days old → Open. **Suffix every reaction-derived status with `~`** and add one footnote under the table: `~ status inferred from Slack reactions — no JIRA ticket linked.`
     ⚠️ Reactions lag reality. Nobody goes back to add a tick when a ticket closes weeks later, which is precisely how long-pending defects kept getting reported as still-open. Treat the tick as a weak signal, the ticket as the truth.
   - **Slack Thread** permalink — `https://cleartaxtech.slack.com/archives/<l3_channel_id>/p<parent_ts_no_dot>`.
3. **Keep only in-scope regions.** Drop escalations whose Product / JIRA-project maps to a region not in `--scope` (those belong to other on-calls).

### Pass 2 — closed this week, raised earlier

Pass 1 only sees threads the bot posted **inside** the window. A defect raised weeks ago and closed during this on-call is invisible to it — the week's most useful outcome goes unreported. Catch those from JIRA rather than Slack.

For each in-scope region, take its `jira_projects` from config and query for tickets that reached a done status inside the window, via `mcp__de387922-450f-43fc-88e8-473a7b0c3961__searchJiraIssuesUsingJql`:

```
project IN (<keys>) AND statusCategory = Done
  AND statusCategoryChangedDate >= "<weekstart> 00:00" AND statusCategoryChangedDate <= "<weekstart+6d> 23:59"
  [AND <scope's jira_pass2_filter, if set>]
ORDER BY statusCategoryChangedDate DESC
```

⚠️ **Never use `resolutiondate` here.** It is only set when a ticket gets a resolution, and EIOCJ's Done transition doesn't set one — on 2026-10-05 a `resolutiondate` query found 1 of the week's 5 closures. `statusCategoryChangedDate` records when the ticket entered Done, whatever the resolution. Jira evaluates these dates in the account's timezone (+05:30 here), so the bounds above are IST.

Then:
1. **Drop every ticket pass 1 already captured** — match on ticket key, so nothing is double-counted between the two tables.
2. **Keep only escalations.** The `*OCJ` projects are mostly Salesforce-created escalations, but not only — they also hold internal dev tasks and months-old Salesforce feature "Story" tickets. A scope's `jira_pass2_filter` (e.g. `issuetype = Bug` for ind/ksa, verified 2026-10-05) keeps pass 2 to real escalations.
3. For each survivor pull: ticket key, customer, one-line issue, `Closed as` (the status name verbatim, plus the resolution if non-empty), engineering owner (the assignee, mapped through the shared `engineers` roster; fall back to the assignee's display name), and the originating Slack thread permalink where the ticket carries one.
4. Render in the `closed this week, raised earlier` sub-table. Omit the sub-section when it comes back empty.
5. **Escalations with no Jira ticket are invisible to this query.** When reading the L3 channel turns up an older ticket-less escalation that closed this week (e.g. a fix confirmed in-thread), add it to the same table with `—` as the ticket. Otherwise say once under the table that ticket-less escalations aren't tracked here.

**If the Atlassian MCP is unavailable:** skip pass 2, fall back to reactions in pass 1, and state once in the doc — `Late-closure pass skipped — Atlassian MCP unavailable; statuses below are Slack-inferred.` Never drop it silently, or the doc quietly understates the week again.

### Rendering

Group pass 1 into one sub-table per in-scope region (header `### <label> — N raised this week`, where N = the workflow-escalation count). Each row: `# | Customer | Issue | Fix | Engineering Owner | Status | Slack Thread`. Then add:
- **Open CFDs handed over** — the open/awaiting workflow CFDs (customer + ticket).
- **Other customer threads** — a short note listing genuine customer-specific threads discussed in-channel but NOT escalated via the workflow (so the next on-call still sees them), explicitly flagged as not counted as CFDs.

## Step 4b — Tagged outside support

Follow the sibling skill **v-oncall-tags** (`skills/v-oncall-tags/SKILL.md` in this plugin) for the same week and scopes, and paste its section into the doc. Why it exists: on-call is regularly tagged in infra, product, security and release channels; none of those asks reach Steps 2–4, so an unanswered one silently disappears at handover. If no in-scope block has an `oncall_handle`, skip it and say so in one line.

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

Per endpoint compute 4 numbers + 1 flag (`{...}` = the endpoint's `service` + `span_name` from config, `span_kind="server"`):

| Column | Query shape (PromQL) | Eval time(s) |
|---|---|---|
| p99 max-1h wk (s) | `max_over_time(histogram_quantiles("phi", 0.99, sum by (vmrange,service,span_name) (rate(cube_apm_latency_bucket{...}[1h])))[7d:1h])` | wk_eval |
| **p99 max-1h 4w mean (s)** | **same `[7d:1h]` query at all 4 baseline anchors, then average the 4 results per endpoint** | w1, w2, w3, w4 |
| Err% wk | **`max_over_time(((sum(rate(err)) / sum(rate(total))) * 100)[7d:1h])`** — the same worst-hour shape as the baseline | wk_eval |
| **Err% 4w mean** | **`max_over_time(((sum(rate(err)) / sum(rate(total))) * 100)[7d:1h])` at all 4 baseline anchors, then average** | w1, w2, w3, w4 |
| Errors wk | `sum(increase(cube_apm_calls_total{..., status_code="ERROR"}[7d]))` — raw count, for the sparse check | wk_eval |
| Outlier? | `yes` if `wk > 1.5 × 4w_mean` on EITHER p99 OR err%, **unless the err% trip rests on < 50 errors in the week** (the same sparse-data rule as the Top-3 tables) — then `no`, and footnote it if the endpoint had zero errors in all 4 baseline weeks | — |

⚠️ **Err% must be worst-hour vs worst-hour.** Until 2026-10-05 the week used a 7-day average (`rate(...[7d])`) while the baseline used the mean of worst hours — two different measures, so the ratio meant nothing (one IND endpoint read 0.79× one way and 2.95× the other). Also expect `rate()` to inflate sparse error series: a 0.76% worst hour was really 23 errors in 48k calls — that's what the < 50 rule is for.

**Query count:** ~8 instant queries per service group (4 weeks × 2 metrics). Run in parallel where possible. The nested `avg_over_time(max_over_time(...[7d:1h])[28d:7d])` shortcut times out at the 30s proxy ceiling — run separate weekly queries.

⚠️ **Parallelism limit (2026-06-30):** the **p99 `[7d:1h]` histogram subqueries are heavy** — a broad one (all `SpringController/v[0-9]+` endpoints × 4 services) fetches ~15k series and takes ~20–25s, right at the 30s proxy ceiling. Running the 5 weekly p99 anchors **in parallel makes 4 of 5 time out** (`context deadline exceeded`). Either (a) run the p99 anchors **sequentially**, or (b) **narrow the `span_name=~` regex** to just the endpoints you need (the in-scope `generate_endpoints` + the top-slowest/error candidates), which drops each query to <10s so a few can run concurrently. The err%/calls queries use `calls_total` (no histogram buckets), are light (~2-4s), and parallelize fine. Recommended flow: 1 broad p99 + 1 broad err% at `wk_eval` (to discover the top-3 candidates), then narrow-regex p99 + err% across the 4 baseline anchors.

Render as one HTML table (wrapped in `<div class="scroll">`): API, Region, p99 max-1h wk (s), p99 max-1h 4w mean (s), Err% wk, Err% 4w mean, Outlier?. **No Mean (ms) columns** — dropped 2026-09-21; the 28d call-weighted aggregate was distorted by any past cascade, always needed a ⚠ caveat, and never drove a decision. That also removes 2 of the ~8 queries per service group.

**If no endpoint is an outlier, don't render the table at all** — emit the single line `All <N> generate endpoints within 1.5× their 4-week baseline on p99 and error rate.` A full table of unremarkable numbers is the bulk of what made this doc feel verbose.

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
- Every PD row has 6 columns: Severity | Count | Incident | Slack Thread | Fix / Resolution | Action Items — PD service named once under the heading, never as a column. Fix / Resolution is 1-2 sentences.
- Every PD permalink uses the real `message_ts` (sub-second micros present, not `000000`).
- Noise / False Alerts is one line per region, not a table.
- Every CFD status traces to a Jira `statusCategory`, or carries a trailing `~` plus the footnote when it fell back to Slack reactions. A doc with no `~` and no Jira lookups performed is wrong.
- The `closed this week, raised earlier` sub-table is present whenever pass 2 returned anything, and the Atlassian-unavailable note is present whenever it was skipped. Silence on both is a failure.
- Critical-API table has one row per in-scope `generate_endpoint` (5 KSA + 4 IND for the default scope) and **no Mean (ms) columns**. Baseline header reads "p99 max-1h 4w **mean** (s)" / "Err% 4w **mean**".
- If 0 outliers: the Critical-API table collapses to the one-line all-within-baseline statement, and Outlier Deep-Dive is omitted entirely.
- Top-3 tables render only for regions with something new or worsening; chronic-flat endpoints collapse to one line. The `≥5,000 calls/week` filter still applies.
- Key takeaways cites specific endpoints, `Nx worse` regressions, and a regression-cluster hypothesis if multiple endpoints moved together.
- Only the requested `--scope` regions appear; no other-region PDs/CFDs leak in.
- "Tagged outside support" is present for every scope with an `oncall_handle` (or omitted because N = 0, said in one line), with open and unanswered tags listed first.
- Output path printed to user; nothing auto-sent or committed.

## Coda push (REMOVED 2026-05-25)

Previously Step 8 pushed the doc to Coda doc `LRUx2GW3fq` via `scripts/coda_push_handover.py`. **Deprecated** — save locally only. The script + `data/coda_table_widths.yaml` remain for reference; the skill no longer invokes them. To re-enable, restore the auto-invocation here and update `HEADER_SIG_TO_KEY` in the script for the current 7-column PD table + metrics tables.
