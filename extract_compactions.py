"""Extract compaction metrics from a Claude Code session transcript (JSONL).

Usage:
    python extract_compactions.py SESSION.jsonl > compactions.csv

Reads only. Emits one CSV row per `compact_boundary` entry, with numbers only:
no message text, no paths, no identifiers from the transcript are written.

Columns
    n                    compaction index (1-based)
    trigger              "auto" or "manual" (compactMetadata.trigger)
    start_s              seconds from the start of the first compaction to the
                         start of this one (boundary timestamp minus durationMs)
    lag_s                seconds between the last user/tool-result entry before
                         the compaction and its start
    duration_s           compactMetadata.durationMs / 1000
    pre_tokens           compactMetadata.preTokens (client-side figure)
    post_tokens          compactMetadata.postTokens (client-side figure)
    cum_dropped_tokens   compactMetadata.cumulativeDroppedTokens
    next_request_ctx     input + cache_read + cache_creation tokens of the first
                         API response after the boundary (server-side figure)
    next_cache_read      cache_read_input_tokens of that response
    next_cache_creation  cache_creation_input_tokens of that response
    requests_since_prev  API requests answered between the previous boundary
                         and this one
    summary_chars        length of the summary text written by this compaction
"""
import csv
import json
import sys
from datetime import datetime, timedelta


def ts(entry):
    t = entry.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def summary_text(entry):
    c = (entry.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict))
    return ""


def main(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    bounds = [i for i, e in enumerate(entries)
              if e.get("type") == "system" and e.get("subtype") == "compact_boundary"]
    summaries = [e for e in entries if e.get("isCompactSummary")]
    user_times = sorted(ts(e) for e in entries
                        if e.get("type") == "user" and not e.get("isCompactSummary") and ts(e))

    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["n", "trigger", "start_s", "lag_s", "duration_s", "pre_tokens", "post_tokens",
                "cum_dropped_tokens", "next_request_ctx", "next_cache_read",
                "next_cache_creation", "requests_since_prev", "summary_chars"])
    t0 = None
    prev = -1
    for n, i in enumerate(bounds, 1):
        e = entries[i]
        cm = e["compactMetadata"]
        start = ts(e) - timedelta(milliseconds=cm["durationMs"])
        if t0 is None:
            t0 = start
        before = [t for t in user_times if t <= start]
        lag = (start - before[-1]).total_seconds() if before else ""

        # distinct API responses between the previous boundary and this one
        req_ids = {x.get("requestId") for x in entries[prev + 1:i]
                   if x.get("type") == "assistant" and x.get("requestId")}

        nxt = next((x for x in entries[i + 1:]
                    if x.get("type") == "assistant"
                    and ((x.get("message") or {}).get("usage") or {}).get("cache_read_input_tokens") is not None
                    and (x.get("message") or {}).get("model") != "<synthetic>"), None)
        u = ((nxt or {}).get("message") or {}).get("usage") or {}
        ctx = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)

        w.writerow([n, cm.get("trigger"), "%.1f" % (start - t0).total_seconds(),
                    "%.2f" % lag if lag != "" else "", "%.1f" % (cm["durationMs"] / 1000),
                    cm.get("preTokens"), cm.get("postTokens"), cm.get("cumulativeDroppedTokens"),
                    ctx or "", u.get("cache_read_input_tokens", ""), u.get("cache_creation_input_tokens", ""),
                    len(req_ids), len(summary_text(summaries[n - 1])) if n - 1 < len(summaries) else ""])
        prev = i


if __name__ == "__main__":
    main(sys.argv[1])
