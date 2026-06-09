# Legacy Agent Handoff

For a new job, hand off the job ID and run ID, then instruct the next agent to
use:

1. `.agents/skills/slide-generator/SKILL.md`
2. `slide-system/workflows/resume-job.md`
3. The run manifest under `outputs/slide-jobs/<job-id>/runs/<run-id>/`

For extraction, use `.agents/skills/component-extractor/SKILL.md` and the
staging manifest under `outputs/component-extractions/<extraction-id>/`.

