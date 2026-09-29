---
name: v-pr-review
description: Review one or more GitHub PRs with a codebase deep-dive. Auto-detects mode by author — your own PRs get a 10-check pre-flight plus the deep-dive (optional --auto-fix rewrites the PR description); anyone else's PR gets the deep-dive only. Detects the country from changed paths and flags known gotchas. Saves each review locally. Multi-PR mode reviews sequentially and waits for "go" between PRs. Never comments on, approves, or merges a PR.
---

You are reviewing one or more PRs for the user. Mode is auto-detected per PR from the author. Multi-PR runs sequentially, with discussion between PRs.

Do the review yourself: read the diff, the files it touches, and their callers. Don't fan it out to sub-agents or a multi-agent workflow.

## Inputs

- `<pr>` — PR URL or number (number only → repo from the current directory's `origin`)
- `<pr1> <pr2> ...` — multiple PRs, reviewed sequentially (multi-PR mode)
- `--auto-fix` — own PRs only. Rewrites the PR description via `gh pr edit`. Ignored (with a warning) on others' PRs.
- `--out <dir>` — where reviews are saved. Default `~/Documents/pr-reviews/`.

## Mode auto-detection

For each PR, compare the author with the authenticated `gh` user:
```
gh api user --jq .login
gh pr view <pr> --repo <owner/repo> --json author --jq .author.login
```

| Author | Mode | What runs | --auto-fix |
|---|---|---|---|
| you | **own** | 10-check pre-flight + deep-dive review | valid (rewrites your PR description) |
| anyone else | **others** | deep-dive review only | warn + ignore |

## Workflow per PR

### Step 1 — Resolve + fetch
- Number only: repo from `git remote get-url origin` in the current directory. URL: parse repo + PR number from it.
- Fetch the metadata and the diff:
```
gh pr view <pr> --repo <owner/repo> --json url,title,body,state,files,additions,deletions,reviewRequests,statusCheckRollup,mergeable,labels,author,baseRefName,headRefName,headRefOid,commits
gh pr diff <pr> --repo <owner/repo>
```

### Step 2 — Read changed files at the PR head
Local clone = the current directory if its `origin` is the PR's repo, else `~/Desktop/<repo>` if it exists. Read its `CLAUDE.md` for repo conventions.

For each file in `files`, read the PR-head version — not whatever branch the clone has checked out:
1. Clone is at the PR head (`git rev-parse HEAD` == `headRefOid`) → `Read` the file.
2. Clone is elsewhere → `git -C <clone> fetch origin pull/<pr>/head`, then `git -C <clone> show FETCH_HEAD:<path>`.
3. No clone → `gh api -H "Accept: application/vnd.github.raw" "repos/<owner>/<repo>/contents/<path>?ref=<headRefOid>"`.

Read enough surrounding code to understand context (whole class/function for Java, whole module for Python).

### Step 2.5 — Country detection
Scan the changed paths + title + body for country signals:

| Path / keyword | Country |
|---|---|
| `einvoice-jo/`, `clear-jofotara/`, `jordan` | JO |
| `einvoice-ae/`, `clear-ae-fta/`, `uae`, `tabby` | AE |
| `einvoice-my/`, `clear-my-lhdn/`, `malaysia` | MY |
| `einvoice-be/`, `belgium` | BE |
| `einvoice-pl/`, `poland`, `ksef` | PL |
| `e-invoicing-be/` (IND), `clr-irp-be/`, `nic`, `ewb`, `irn`, `gst` | IN |
| `einvoice-ksa`, `zatca`, `ksa`, `saudi` | SA |
| `france`, `ppf`, `cdar` | FR |
| `clear-peppol-ap/` (when not country-pinned) | Peppol |

Multiple matches → check each. No match → cross-country / platform PR; skip this step.

For each detected country, read the country module's `CLAUDE.md` / `README.md` in the clone if present, and check the PR against the known gotchas:
- AE mapper change → `TaxCategory` element order inside `TaxSubtotal` unchanged (einvoicing-core#1282 added 18 regression tests guarding it)
- JO mapping change → Money-wrapper `.value.value` pattern not regressed
- IN change → NIC switcher logic not re-introduced (reverted post-Nov 2025)

Anything that breaks one of these goes under Correctness in Step 7.

### Step 3 — Cross-reference codebase
For each modified function/symbol:
- Grep call-sites: `grep -rn "<symbol>" <clone>/src/` (no clone → say call-site coverage is limited)
- Check downstream consumers
- Verify backwards-compatibility (does the old caller still work after this change?)
- Look for similar-pattern usages elsewhere — catches whole bug-classes (e.g. one typo'd path in an enum like `EInvoiceUblFields` → verify every entry)
- For schema/DB changes: trace producer + consumer paths
- For API changes: enumerate all callers
- For new features: check feature-flag gating (`@ConditionalOnCountry`, `@ConditionalOnProperty`, etc.)

### Step 4 — Run the new tests (local clone only)
If there's a clone and the PR adds tests, run only the new test class, on the PR head, in a throwaway worktree:
```
git -C <clone> fetch origin pull/<pr>/head
git -C <clone> worktree add <tmp-dir>/pr-<pr> FETCH_HEAD
cd <tmp-dir>/pr-<pr> && mvn test -Dtest=<NewTestClass>   # multi-module: -pl <module> -am -Dsurefire.failIfNoSpecifiedTests=false
git -C <clone> worktree remove --force <tmp-dir>/pr-<pr>
```
Use the JDK / build command the repo's `CLAUDE.md` names. Note pass/fail. If you didn't run them, say "didn't run" — never fabricate.

### Step 5 — Classify findings
Bucket every observation into:
- **Correctness** — does the logic work? cite `file:line`
- **Impact** — call-sites, backwards-compat, downstream consumers, side-effects
- **Test quality** — new tests added? cover the change? edge cases? gating tests?
- **Concerns / nits** — non-blocking but worth flagging (PR description issues, missing docs, code-style)

### Step 6 — Own PR pre-flight (own mode only)
Run 10 checks. Report each as ✅ / ⚠️ / ❌:

A. **Description structure** — body has Why / What / How / Test plan / Rollback / Linked tickets sections?
B. **JIRA link** — body contains `[A-Z]+-\d+` or a JIRA URL?
C. **AI tag** — body mentions AI assistance ("AI-assisted", Claude Code, Cursor, a `Co-Authored-By: Claude` line)?
D. **Design doc link** — body links a Confluence/Drive LLD/HLD/design doc?
E. **Test coverage heuristic** — for each changed `.java` file, does a matching `*Test.java` exist in the diff or the codebase?
F. **Instrumentation** — for new endpoints/jobs/handlers, does the diff add `@Timed`, `MeterRegistry`, `Counter`, `log.info`, `Sentry.captureException`?
G. **CI status** — any failing checks in `statusCheckRollup`?
H. **Branch staleness** — `gh api "repos/<owner>/<repo>/compare/<baseRefName>...<headRefOid>" --jq '{behind_by, merge_base_date: .merge_base_commit.commit.committer.date}'`. Flag if `behind_by` > 0 and the merge base is more than 7 days old.
I. **TODOs in diff** — search the added lines for `TODO`/`FIXME`/`XXX`. List with file:line.
J. **Reviewers requested** — `reviewRequests` empty? Suggest reviewers from `CODEOWNERS`, else the most frequent recent authors of the touched files (`git -C <clone> log -n 50 --format='%an' -- <paths> | sort | uniq -c | sort -rn`).

### Step 7 — Compose review

```
## Review — PR #<pr>: <title>

**Author:** <author> · **Repo:** <repo> · **Mode:** own | others
**Verdict:** ✅ approve | ⚠️ request-changes | ❌ block

### 1. Correctness
[bullets — cite file:line]

### 2. Impact
[backwards-compat, call-sites, downstream consumers]

### 3. Test quality
[new tests? gaps? edge cases?]

### 4. Concerns / nits
[non-blocking items]

### 5. Pre-flight (own mode only)
A. Description structure: ✅ / ⚠️ — <detail>
B. JIRA link: ...
... (J. Reviewers)

### 6. TL;DR
[1-3 line summary]
```

### Step 8 — Auto-fix (own + --auto-fix only)
If the user passed `--auto-fix` AND mode == own:
1. Generate a rewritten PR description (fill missing sections with stubs based on the diff/commits).
2. Write it to `<out>/<repo>-<pr>-rewrite.md`.
3. Run `gh pr edit <pr> --repo <owner/repo> --body-file <path>`.
4. Confirm: "✅ PR description rewritten + posted."

Skip (with a warning) if mode == others or `state` isn't `OPEN`.

### Step 9 — Persist
Write the review to `<out>/<repo>-<pr>.md` (create `<out>` if missing) with frontmatter:

```yaml
---
pr_url: <url>
author: <login>
mode: own | others
review_date: <ISO 8601 IST>
verdict: approve | request-changes | block
findings_count: <N>
substantive: true | false   # true if findings ≥ 5
files_reviewed: <N>
---

[full review markdown body from Step 7]
```

### Step 10 — Multi-PR handoff
If multiple PRs are queued:
- Print: `PR <i> of <N> reviewed. Discuss findings, type 'go' for PR <i+1>, or 'stop' to halt.`
- Wait for the user's response.
- On `go`: repeat from Step 1 with the next PR.
- On `stop` or discussion: hold + respond to the discussion. Wait for an explicit `go`.

## Hard rules

- **NEVER post comments via `gh pr comment` or similar.**
- **NEVER auto-merge or auto-approve via `gh pr review --approve`.**
- `--auto-fix` rewrites the PR DESCRIPTION ONLY (own PR), not comments or reviews.
- No `git commit` / `git push` (user does these).
- If the Claude Code sandbox blocks `gh` (api.github.com, macOS keychain), `git -C <clone>`, or a test run, rerun it with `dangerouslyDisableSandbox: true`.

## Verifiable success
- Review markdown at `<out>/<repo>-<pr>.md` with valid frontmatter.
- `verdict` set to one of: approve / request-changes / block.
- `findings_count` ≥ 1 for any non-trivial PR.
- No PR comments posted: `gh pr view <pr> --repo <owner/repo> --json comments --jq '.comments | length'` matches the pre-review count.

## Failure modes
- PR not found → abort with the `gh pr view` error.
- gh rate-limit → suggest a retry in N min.
- gh auth missing → run `gh auth status`, ask the user to `gh auth login`.
- No local clone → `gh api` for file reads (Step 2); skip the test run.
- Diff too large (>1000 lines) → focus on logic-bearing files; note skipped boilerplate.
- `--auto-fix` on others' PR → warn and proceed without auto-fix.
- `--auto-fix` on a closed/merged PR → warn and proceed without auto-fix.
- `--auto-fix` when the description is already complete → still safe; no destructive change.

## Don't
- Don't auto-comment on the PR.
- Don't auto-merge.
- Don't auto-approve.
- Don't move to the next PR in multi-PR mode without an explicit `go`.
- Don't fabricate test results — actually run the tests or say "didn't run".
- Don't include real TINs / API secrets in review reports.
- Don't `gh pr checkout` or switch branches in the user's clone — use `FETCH_HEAD` / a throwaway worktree.
- Don't fork into "review my own" vs "review others'" subskills — keep auto-detection in one skill.
