# Log format & naming standard

This file is the template/reference for session logs. It is **not** a log itself
(the `_` prefix keeps it sorted apart). Rule of record: `AGENTS.md` → "Task Logging".

## Naming

- **One file per day:** `docs/logs/SESSION-LOG-<YYYY-MM-DD>.md` (date from the
  `currentDate` context). This is the **only** log filename pattern.
- All logs live under `docs/logs/` — never loose in `docs/` or the repo root.
- Do **not** create per-topic log files (e.g. `LOG-<date>-<topic>.md`,
  `REPORT-*.md`). An audit/report is just a task entry inside that day's session log.

## File header

```markdown
# Session Log — <YYYY-MM-DD>

Branch: `<branch>`.
Append-only record, one entry per task in request order. Format per
`docs/logs/_TEMPLATE.md` (rule: `AGENTS.md` → "Task Logging").

---
```

## Entry template

Number entries **per day** as `<YYYY-MM-DD>.<n>` (e.g. `2026-06-24.1`,
`2026-06-24.2`, …) — `<n>` restarts at 1 each day's file. This avoids a global
running counter that breaks across sessions/agents. Never mix `§`, `Task:`, or a
single global integer. One heading level (`##`) for every entry.

`Files:` and `Symbols:` are **required** machine-readable fields — they feed
`docs/logs/INDEX.jsonl` (see `slide-system/scripts/build_log_index.py`) so an
agent can locate relevant entries with one `rtk grep` before reading any prose.
List real paths and, where a code symbol changed, its name (resolvable via
`codegraph node <symbol>`). Use `none` if genuinely not applicable.

```markdown
## <YYYY-MM-DD>.<n> — <Short imperative title>

**When:** <YYYY-MM-DD HH:MM>   (optional; include only if actually known)
**Request:** <what the user asked, verbatim or faithful paraphrase>
**Actions:**
- <concrete steps: files created/modified/deleted, commands run, decisions + why>
**Result:** <outcome + verification run (tests/gates/scans) and their status>
**Files:** <comma-separated paths touched, or `none`>
**Symbols:** <comma-separated code symbols changed, or `none`>
**State:** Committed <hash> | Committed in entry <id>'s batch | Not committed

---
```

After appending an entry, regenerate the index:
`python3 slide-system/scripts/build_log_index.py --write`

## Rules

- **Faithfulness:** log only what actually happened — no invented steps, no
  guessed outcomes. If a step was skipped or failed, say so.
- Ground file/line/count claims in real `git status` / command output, not memory.
- If a later entry overturns an earlier one, add a short `> ⚠️ SUPERSEDED by
  entry <N>:` note to the old entry rather than rewriting history.
- Record each task as soon as it is completed or meaningfully advanced.
