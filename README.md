# Case study: an autocompact loop from `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1`

A single Claude Code session compacted itself 8 times in under 4 minutes after
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` was set to `1` in `~/.claude/settings.json`.
This repository holds the numbers extracted from that session's transcript and
what they show. It is one session, not a benchmark.

**Short version**

- The override was set below the session's fixed context floor (about 90k
  tokens), so every request re-triggered compaction.
- Each compaction took 14–25 s and freed about 1–2k tokens of real context.
- Removing the setting from `settings.json` did not stop the loop. The variable
  stayed in the running process until the app was restarted.
- A manual `/compact` did not stop it either.
- None of the 8 summaries recorded that the loop was happening.

## Environment

| | |
|---|---|
| Claude Code version | 2.1.321 |
| Entry point | `claude-desktop` (desktop app, Code tab) |
| OS | Windows 11 |
| Model | `claude-haiku-5-5` |
| Context window shown by the app | 1M (read from the app's context panel, not from the transcript) |
| Setting | `"env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "1"}` in `~/.claude/settings.json` |

## What was measured, and how

Everything below comes from the session's JSONL transcript, read with
[`extract_compactions.py`](extract_compactions.py). The output is
[`compactions.csv`](compactions.csv). The raw transcript is not published
because it contains account identifiers and local configuration.

Two kinds of token figures appear, and they are not the same count:

- `pre_tokens` and `post_tokens` come from `compactMetadata` on each
  `compact_boundary` entry. They are written by the client.
- `next_request_ctx` is `input_tokens + cache_read_input_tokens +
  cache_creation_input_tokens` from the first API response after the boundary.
  It is what the server billed as input.

## The 8 compactions

Times are seconds from the start of the first compaction.

| # | Trigger | Start (s) | Duration (s) | `pre_tokens` | `post_tokens` | Next request, real input | Requests since previous |
|---|---|---|---|---|---|---|---|
| 1 | auto | 0.0 | 23.2 | 182,962 | 21,164 | 90,840 | 12 |
| 2 | auto | 37.6 | 14.7 | 92,010 | 21,216 | 90,929 | 1 |
| 3 | auto | 56.7 | 15.4 | 91,917 | 20,756 | 90,313 | 1 |
| 4 | auto | 74.4 | 14.1 | 92,011 | 20,644 | 90,119 | 1 |
| 5 | manual | 99.7 | 14.2 | 91,363 | 20,694 | 90,577 | 1 |
| 6 | auto | 166.7 | 25.0 | 91,617 | 21,226 | 92,387 | 1 |
| 7 | auto | 197.8 | 15.8 | 93,297 | 21,210 | 90,901 | 1 |
| 8 | auto | 220.3 | 16.0 | 92,541 | 20,665 | 91,214 | 1 |

Row 8's next request came after an app restart, with a cold cache.

### Timeline of the other events

| Time (s) | Event |
|---|---|
| −4.2 | `env` block with the override written to `settings.json` |
| 0.0 | First compaction starts, in the same turn, without a restart |
| 56.4 | `env` block removed from `settings.json` |
| 74.2 | File re-read; the block is gone |
| 93.1 | Client emits: "Autocompact is thrashing: the context refilled to the limit within 3 turns of the previous compact, 3 times in a row." |
| 99.7 | User runs `/compact` |
| 166.4 | `printenv CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` inside the session returns `1` |
| 197.5 | Windows user and machine scopes are empty; process scope is `1` |
| 264 | App restarted |
| 270.8 | Process scope is empty |
| 264–733 | Context grows from 91,214 to 100,682 tokens with no further compaction |

## Findings

### 1. The trigger values are not a threshold

After the first one, every compaction fired after exactly one API request, about
0.3 s after the first entry that followed that request (`lag_s` in the CSV). The
`pre_tokens` values (91,363–93,297) are simply where the context happened to be.
The transcript does not record the threshold. It only bounds it: below 91,363
with the override, above 100,682 without it.

### 2. `post_tokens` is not the context the model receives

`post_tokens` was about 21k every time. The next request was 90,119–92,387
tokens. In the seven requests that were served from cache, 56,869 tokens were an
identical cached prefix and 33–36k were rewritten.

The transcript shows what is re-attached after each boundary. Sizes are bytes of
the JSONL line, not tokens, and whether each one reaches the model in full was
not verified:

| Attachment type | Bytes |
|---|---|
| `skill_listing` | 54,243 |
| `invoked_skills` | 43,656 |
| `prompt_snapshot` | 35,162 |
| `deferred_tools_delta` | 18,735 |
| `file` (two re-read files) | 17,841 |
| `mcp_instructions_delta` | 13,083 |
| `output_style_instructions` | 7,078 |
| `agent_listing_delta` | 5,959 |

### 3. Each compaction bought almost nothing

`pre_tokens` minus the next request's real input, for compactions 2–8:
1,081 · 1,604 · 1,892 · 786 · −770 · 2,396 · 1,327 tokens. Compaction 6 ended
with more context than it started with. The two figures are counted by
different sides, so treat these as approximate.

Cost of the loop: 138.5 s spent compacting inside a 236 s window (59%), and
`cumulativeDroppedTokens` reached 660,143.

### 4. The first compaction had a different cause

A skill load added one 322,102-byte message and the request input went from
86,937 to 179,401 tokens in one step. That is why compaction 1 shows
`pre_tokens` of 182,962. The override was written 4 s earlier.

### 5. Adding the setting applied live; removing it did not

The override took effect in the turn where it was written. After it was removed
from the file, the process still reported `1`, and three more automatic
compactions followed. Only the restart cleared it.

### 6. Manual `/compact` is the same operation

It produced the same `post_tokens` (20,694) and the same next-request size
(90,577). The next automatic compaction started 0.27 s after the first tool
result that followed.

### 7. What the summaries kept and lost

The 8 summaries are 7,844–10,212 characters each, all with the same nine
sections. Compared sentence by sentence with a similarity script, then checked
by hand for the cases listed here:

| Item | Present in summaries |
|---|---|
| The thrashing error, or any count of compactions | none of the 8 |
| "Effect of the setting not verified" | 3, 4 and 5, each written by that effect |
| User messages, quoted verbatim | all 8 |
| List of available skills (a pending task depended on it) | 1 and 2 only |
| Exact strings of the file edits | 1–3, gone by 4 |
| Contents of the user's memory files (not just file names) | 5 and 6 only |
| Mentions of the variable name | 6, 5, 3, 2, 2, 3, 3, 2 |

Some facts appeared in a later summary without being in the earlier one. They
came from files that are re-attached after each boundary, not from the previous
summary.

## Practical takeaways

1. Measure the context floor before lowering the threshold. A threshold below
   the floor cannot be satisfied by compacting.
2. Judge a compaction by the next request's input tokens, not by `post_tokens`.
3. To lower the floor, remove skills, tools and instructions. Compaction only
   shrinks messages.
4. Check the size of a skill before loading it in a long session.
5. If a session loops, restart the client. `/compact` and editing the settings
   file did not help here.
6. Try behaviour-changing environment variables in a throwaway session.
7. Do not rely on a compaction summary to know what happened during compaction.
   Read the transcript.
8. Anything that must survive several compactions should live in a file.

## Limits

- One session, one version, one platform, one model.
- The threshold itself was never observed, only bounded.
- The summary comparison is a pattern seen across 8 summaries of the same short
  session. It is not a general rule.
- Why removing the setting did not clear the process variable was not
  investigated. Only the behaviour was recorded.

## Related reports

- [anthropics/claude-code#63186](https://github.com/anthropics/claude-code/issues/63186)
  reports the override in the `settings.json` `env` block being ignored. In this
  session it was applied.
- [anthropics/claude-code#60485](https://github.com/anthropics/claude-code/issues/60485)
  reports the thrashing message on fresh sessions.
- [anthropics/claude-code#31806](https://github.com/anthropics/claude-code/issues/31806)
  reports that the override can lower the threshold but not raise it.
