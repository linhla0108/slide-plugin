## Karpathy Guidelines (always active)

Follow `/karpathy-guidelines` for all coding work: think before coding,
simplicity first, surgical changes, goal-driven execution.

## Task Logging (required)

Maintain a detailed, append-only work log. Full rule in `AGENTS.md` →
"Task Logging". In short: for every task you complete, append an entry to
`docs/logs/SESSION-LOG-<YYYY-MM-DD>.md` (all logs live in `docs/logs/`)
recording the request, the concrete actions
(files/commands/decisions), the result + verification, and whether it was
committed. Log only what actually happened — no invented steps.

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tools** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them. `codegraph_node` returns one symbol's source + callers, or reads a whole file with line numbers. If the tools are listed but deferred, load them by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` and `codegraph node <symbol-or-file>` print the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
