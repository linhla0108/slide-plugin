# Claude-Codex QA Loop

`slide-system/scripts/run_claude_codex_qa_loop.ps1` is an opt-in local runner
for a bounded implementation and review loop. It is intended for one scoped
task at a time, not for unattended repository maintenance.

## Safety Contract

- Default mode is `-Plan`; it never invokes Claude, Codex, or tests.
- A real run requires `-Run`, `-PromptFile`, and `-AllowedPath`.
- A dirty worktree fails by default. `-AllowDirtyBaseline` records the existing
  state in the run evidence; it never discards or stages that state.
- Source changes outside `-AllowedPath` stop the run.
- Claude runs through `claude -p`; Codex reviews through `codex exec` with a
  read-only sandbox and a structured `allow`/`block` verdict.
- Each Claude round is one smallest coherent implementation slice. A blocked
  Codex verdict becomes the next round's input; do not ask one Claude turn to
  complete a broad task before review.
- The runner stops after at most three rounds, on no source change, on an
  out-of-scope change, a Claude round timeout (10 minutes by default), or when
  a final review remains blocked. A timeout terminates only the runner's child
  process tree.
- It never commits, pushes, merges, rebases, resets, cleans, deletes source
  files, or enables the Codex plugin's global stop hook.

An `allow` verdict is accepted only after a code-changing round and after the
verification commands pass. It is not accepted for a status-only Claude turn.

## Use

First inspect the planned execution:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\slide-system\scripts\run_claude_codex_qa_loop.ps1 `
  -PromptFile .\path\to\task.md -Plan
```

Then run a narrow task. List every source/docs path the task may change. For an
already-dirty worktree, pass `-AllowDirtyBaseline` only after reviewing its
existing changes.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\slide-system\scripts\run_claude_codex_qa_loop.ps1 `
  -Run `
  -PromptFile .\path\to\task.md `
  -AllowedPath "slide-system/scripts,slide-system/schemas,.agents/skills/slide-generator,docs/flows,docs/logs" `
  -AllowDirtyBaseline `
  -RequiredArtifact outputs/slide-jobs/<job>/runs/<run>/qa/fidelity-report.txt
```

By default the successful final round runs `test_gates.py`,
`validate_registry.py`, `build_registry.py --check`, and `git diff --check`
with `.venv\Scripts\python.exe`. Use `-VerificationScript` for a task-specific
E2E verification script that also checks generated PPTX/PDF artifacts.

Evidence is written to `outputs/agent-qa-loops/<timestamp>/`. Review the final
artifact and evidence manually before committing or merging.

Use `-ClaudeTimeoutMinutes <1..15>` only when the task's expected reasoning and
test time justify a different per-round cap.
