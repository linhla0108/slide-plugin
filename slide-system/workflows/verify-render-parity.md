# Verify Render Parity

1. Capture approved HTML at `1920x1080` with fonts and images ready.
2. Render the candidate output with a verified renderer.
3. Run `scripts/compare_renders.py`.
4. Review side-by-side, overlay, and difference images.
5. Check key regions: base background, complex overlays, title, main content,
   primary visual, logo, and folio.
6. Run at least one fix-and-verify cycle.
7. Store the policy, metrics, reviewer notes, checksums, and final status.

Use `render-equivalent`, not `pixel-identical`, for cross-renderer acceptance.
