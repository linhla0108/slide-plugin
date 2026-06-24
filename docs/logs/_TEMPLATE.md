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

Number entries with a single running integer (`1`, `2`, `3`, …) — never mix
`§`, `Task:`, or restart numbering. One heading level (`##`) for every entry.

```markdown
## <N> — <Short imperative title>

**When:** <YYYY-MM-DD HH:MM>   (optional; include only if actually known)
**Request:** <what the user asked, verbatim or faithful paraphrase>
**Actions:**
- <concrete steps: files created/modified/deleted, commands run, decisions + why>
**Result:** <outcome + verification run (tests/gates/scans) and their status>
**State:** Committed <hash> | Committed in entry <N>'s batch | Not committed

---
```

## Rules

- **Faithfulness:** log only what actually happened — no invented steps, no
  guessed outcomes. If a step was skipped or failed, say so.
- Ground file/line/count claims in real `git status` / command output, not memory.
- If a later entry overturns an earlier one, add a short `> ⚠️ SUPERSEDED by
  entry <N>:` note to the old entry rather than rewriting history.
- Record each task as soon as it is completed or meaningfully advanced.
