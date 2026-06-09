# Verify Render Parity

1. Capture approved HTML at `1920x1080` with fonts and images ready.
2. Render the candidate output with a verified renderer.
3. Run `scripts/compare_renders.py`.
4. Review side-by-side, overlay, and difference images.
5. Check key regions: base background, complex overlays, title, main content,
   primary visual, logo, and folio.
6. Run at least one fix-and-verify cycle.
7. Store the policy, metrics, reviewer notes, checksums, and final status.
8. Treat per-slide capture, render, overlay, and difference images as ephemeral.
   Once parity passes, keep only `qa-report.md` plus the metrics and checksums;
   delete `qa/export-renders/`. Keep the images only while a parity check is
   still failing.

Use `render-equivalent`, not `pixel-identical`, for cross-renderer acceptance.
