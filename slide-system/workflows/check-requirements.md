# Check Requirements

Run before planning or build.

1. Validate the job requirements against `job-requirements.schema.json`.
2. Read `registries/capabilities.json`.
3. Refresh a capability only when it is unknown, its path is missing, the
   environment fingerprint changed, or a real command failed.
4. Verify inputs, checksums, source authority, brand pack, fonts, export
   targets, editability, renderer support, and required approvals.
5. Classify findings as `pass`, `warning`, or `blocker`.
6. Stop on blockers unless the user approves an override.
7. Save results in the run analysis folder and include them in the approval
   package.

Do not probe every installed tool on every job.
