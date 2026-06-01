#!/usr/bin/env python3
"""Push the v-oncall-handover weekly markdown doc to Coda as HTML with
preserved column widths.

Why HTML, not markdown:
  - Coda's `format: "markdown"` paste creates static-width tables that get
    squished when one cell is much longer than its siblings.
  - Coda's `format: "html"` paste creates real Coda data tables AND honors
    <th style="width:Npx"> on creation. Widths persist forever after that.

Workflow:
  1. Read /tmp/coda_handover_<weekstart>.md (or the path from --md).
  2. For each markdown table, look up its width profile in
     data/coda_table_widths.yaml (keyed by --table-keys flag, in order of
     appearance). Convert that table to HTML with <th style="width:Npx">
     embedded per column.
  3. Non-table content (headings, paragraphs, lists) gets passed through
     to Coda as separate markdown contentUpdate calls.
  4. Append everything to the configured Coda page.

Usage:
  CODA_TOKEN=<token> python3 scripts/coda_push_handover.py \\
      --md ~/oncall-handover-2026-04-27.md \\
      --doc-id LRUx2GW3fq \\
      --page-id canvas-4_oBrW7S-z \\
      --table-keys ksa_pd,noise_false,cfd_ksa,cfd_ind

The --table-keys arg names the width profiles in
data/coda_table_widths.yaml in the order tables appear in the doc.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
WIDTHS_PATH = REPO_ROOT / "data" / "coda_table_widths.yaml"
TOKEN_FILE = Path.home() / ".coda_token"
CODA_API = "https://coda.io/apis/v1"

# Auto-detect a table's width-profile key from its column headers.
# Tables with the same column signature share a profile (e.g. KSA RPM and
# IND RPM both map to `rpm`).
HEADER_SIG_TO_KEY = {
    ("Severity", "Count", "Incident", "PD Service", "Slack Thread"): "ksa_pd",
    ("Region", "Count", "Alert", "PD Service"): "noise_false",
    ("Customer", "Issue", "Short-term Fix", "Long-term Fix",
     "Engineering Owner", "Status", "Slack Thread"): "cfd_ksa",
    ("#", "Endpoint", "Min (RPM)", "Min @", "Max (RPM)", "Max @", "Mean"): "rpm",
    ("#", "Endpoint", "Min (ms)", "Min @", "Max (ms)", "Max @", "Mean"): "latency",
    ("When (IST)", "Region", "Issue", "Status / Owner"): "breach",
}


def load_widths():
    if not WIDTHS_PATH.exists():
        return {}
    return yaml.safe_load(WIDTHS_PATH.read_text()) or {}


def load_token():
    """CODA_TOKEN env var first, then ~/.coda_token file fallback."""
    tok = os.environ.get("CODA_TOKEN")
    if tok:
        return tok.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def detect_table_key(headers):
    """Return the width-profile key for a table given its header tuple."""
    return HEADER_SIG_TO_KEY.get(tuple(headers))


def md_inline_to_html(text: str) -> str:
    """Convert a single line of inline markdown (within a table cell) to HTML.

    Supports: **bold**, *italic*, `code`, [link](url), <br>.
    Leaves unknown markup as-is.
    """
    # Escape stray HTML angle brackets that aren't part of an existing tag
    # (we leave <br>, <b>, <i> etc. alone — markdown rarely embeds them).
    # Keep simple: rely on author keeping cells well-formed.

    # Code spans first (so * inside `code` doesn't get bolded)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    # Italic (single * or _)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    return text


def parse_md_table(lines):
    """Parse a markdown table. Returns (headers, rows) or None."""
    if len(lines) < 2:
        return None
    if not (lines[0].lstrip().startswith("|") and re.match(r"^\s*\|[\s|:\-]+\|", lines[1])):
        return None
    headers = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        if not line.lstrip().startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return headers, rows


def md_table_to_html(headers, rows, widths_map):
    """Build a Coda-friendly HTML table with embedded <th> widths.

    `data-coda-view-config-hiddenuimask="64"` hides the auto-generated
    "Table N" title row (Coda assigns sequential names on creation; we
    don't need them since each table has an H2 heading right above it).
    Verified 2026-05-10 via probe push.
    """
    th_html = []
    for h in headers:
        w = widths_map.get(h)
        style = f' style="width: {w}px;"' if w else ""
        th_html.append(f"<th{style}>{md_inline_to_html(h)}</th>")
    head = "<thead><tr>" + "".join(th_html) + "</tr></thead>"
    body_rows = []
    for r in rows:
        tds = "".join(f"<td>{md_inline_to_html(c)}</td>" for c in r)
        body_rows.append(f"<tr>{tds}</tr>")
    body = "<tbody>" + "".join(body_rows) + "</tbody>"
    return (
        '<table data-coda-view-config-hiddenuimask="64">'
        f"{head}{body}</table>"
    )


def split_md_into_blocks(md_text):
    """Yield ('markdown', text) or ('table', (headers, rows)) blocks."""
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(
            r"^\s*\|[\s|:\-]+\|", lines[i + 1]
        ):
            # Table starts
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            parsed = parse_md_table(lines[i:j])
            if parsed:
                yield ("table", parsed)
            i = j
            continue
        # Collect contiguous non-table lines
        j = i
        while j < len(lines):
            if (
                lines[j].lstrip().startswith("|")
                and j + 1 < len(lines)
                and re.match(r"^\s*\|[\s|:\-]+\|", lines[j + 1])
            ):
                break
            j += 1
        chunk = "\n".join(lines[i:j])
        if chunk.strip():
            yield ("markdown", chunk)
        i = j


def coda_put(doc_id, page_id, payload, token, max_retries=4):
    """PUT to Coda with retry on 429 (rate limit) — exponential backoff."""
    import time
    url = f"{CODA_API}/docs/{doc_id}/pages/{page_id}"
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            method="PUT",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            data=body,
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)  # 2, 4, 8, 16 s
                print(f"  429 rate-limited — sleeping {wait}s (attempt {attempt+1}/{max_retries})",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            # Transient network issue — retry with backoff
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  network error ({type(e).__name__}: {e}) — retry in {wait}s (attempt {attempt+1}/{max_retries})",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    # unreachable


def append_block(doc_id, page_id, content, fmt, token):
    """Append one block; sleep briefly after to avoid Coda's 429 rate limit."""
    import time
    payload = {
        "contentUpdate": {
            "insertionMode": "append",
            "canvasContent": {"format": fmt, "content": content},
        }
    }
    resp = coda_put(doc_id, page_id, payload, token)
    time.sleep(1.0)  # gentle pacing — Coda 429s on burst pushes
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True, help="Path to weekly handover markdown")
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--page-id", required=True)
    ap.add_argument(
        "--table-keys", default=None,
        help="Optional comma-separated width-profile key override per table in "
             "order. If omitted, keys are auto-detected from column headers.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Print HTML payloads instead of pushing")
    ap.add_argument("--stop-at-heading", default=None,
                    help="Stop pushing at a markdown heading containing this string.")
    ap.add_argument("--start-at-heading", default=None,
                    help="Skip everything until a markdown heading containing this string.")
    args = ap.parse_args()

    token = None if args.dry_run else load_token()
    if not token and not args.dry_run:
        sys.exit("CODA_TOKEN env var or ~/.coda_token file required")

    widths_cfg = load_widths()
    md = Path(args.md).read_text()

    blocks = list(split_md_into_blocks(md))
    keys_override = (
        [k.strip() for k in args.table_keys.split(",") if k.strip()]
        if args.table_keys else None
    )
    table_idx = 0
    pushes = 0
    started = args.start_at_heading is None
    for kind, payload in blocks:
        # Honor --start-at-heading: skip everything until matching heading
        if not started:
            if kind == "markdown" and any(
                line.startswith("#") and args.start_at_heading in line
                for line in payload.splitlines()
            ):
                started = True
            else:
                continue
        if (
            args.stop_at_heading
            and kind == "markdown"
            and any(
                line.startswith("#") and args.stop_at_heading in line
                for line in payload.splitlines()
            )
        ):
            if args.dry_run:
                print(f"--- STOP: hit heading containing '{args.stop_at_heading}' ---")
            break
        if kind == "markdown":
            # Strip image lines — Coda can't resolve local file refs
            payload = "\n".join(
                line for line in payload.splitlines()
                if not line.lstrip().startswith("![")
            )
            if not payload.strip():
                continue
            if args.dry_run:
                print(f"--- markdown block ({len(payload)} chars) ---")
                print(payload[:500] + ("..." if len(payload) > 500 else ""))
            else:
                append_block(args.doc_id, args.page_id, payload, "markdown", token)
                pushes += 1
        else:
            headers, rows = payload
            if keys_override:
                if table_idx >= len(keys_override):
                    sys.exit(
                        f"ERROR: more tables in doc ({table_idx + 1}) than "
                        f"--table-keys profiles ({len(keys_override)})."
                    )
                key = keys_override[table_idx]
            else:
                key = detect_table_key(headers)
                if key is None:
                    print(
                        f"WARN: no width profile for headers {headers!r}; "
                        f"pushing without explicit widths.", file=sys.stderr
                    )
            widths_map = widths_cfg.get(key) or {} if key else {}
            html = md_table_to_html(headers, rows, widths_map)
            table_idx += 1
            if args.dry_run:
                print(f"--- table {table_idx} (key={key!r}, widths={widths_map}) ---")
                print(html[:500] + ("..." if len(html) > 500 else ""))
            else:
                append_block(args.doc_id, args.page_id, html, "html", token)
                pushes += 1

    if not args.dry_run:
        print(f"Pushed {pushes} blocks ({table_idx} tables) to Coda page {args.page_id}")


if __name__ == "__main__":
    main()
