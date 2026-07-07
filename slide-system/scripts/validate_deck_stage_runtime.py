#!/usr/bin/env python3
"""Post-build gate: the shipped deck must scale to the viewport.

Enforces the build rule that a deck uses a `<deck-stage>` backed by the
`deck_stage.js` runtime (letterboxed transform:scale for viewing, `noscale`
for 1:1 export capture) instead of a hand-rolled fixed-`px` static stage that
renders locked at 1080p and never scales.

FAILS when:
  1. no `<deck-stage>` element is present (hand-rolled stage), or
  2. `<deck-stage>` is present but its runtime is not loaded (no
     `<script src=...deck_stage.js>` and no inline `customElements.define`
     for `deck-stage`) — the element would render as an unscaled inert block.

Reports (does not fail on) a fixed-`px` static stage div as a diagnostic when
the primary checks already failed, to point at the likely culprit.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import now_iso, write_json

DECK_STAGE_EL_RE = re.compile(r"<deck-stage[\s>]", re.IGNORECASE)
RUNTIME_SRC_RE = re.compile(
    r"<script[^>]+src\s*=\s*['\"][^'\"]*deck[_-]stage[^'\"]*\.js['\"]",
    re.IGNORECASE,
)
RUNTIME_DEFINE_RE = re.compile(
    r"customElements\.define\(\s*['\"]deck-stage['\"]", re.IGNORECASE
)
# Hand-rolled static stage anti-pattern: an element with a fixed 1920px (or
# 1080px) dimension in an inline style or CSS rule, used as the slide canvas.
STATIC_STAGE_RE = re.compile(
    r"(width|height)\s*:\s*(1920|1080)px", re.IGNORECASE
)


def check_deck_stage(html: str) -> dict:
    has_el = bool(DECK_STAGE_EL_RE.search(html))
    has_runtime = bool(
        RUNTIME_SRC_RE.search(html) or RUNTIME_DEFINE_RE.search(html)
    )
    has_static_px = bool(STATIC_STAGE_RE.search(html))

    if has_el and has_runtime:
        return {
            "name": "deck_stage_runtime", "pass": True,
            "detail": "<deck-stage> present and runtime loaded — deck scales to viewport.",
            "has_deck_stage_element": True,
            "has_runtime": True,
            "static_px_dimensions": has_static_px,
        }

    if not has_el:
        detail = ("No <deck-stage> element — deck is a hand-rolled static stage "
                  "and will render locked at 1080p. Wrap slides in "
                  "<deck-stage width=\"1920\" height=\"1080\"> backed by deck_stage.js.")
    else:
        detail = ("<deck-stage> present but its runtime is not loaded (no "
                  "<script src=...deck_stage.js> and no inline "
                  "customElements.define('deck-stage')). Load the runtime so the "
                  "component applies letterboxed scaling and honours noscale on export.")

    return {
        "name": "deck_stage_runtime", "pass": False,
        "detail": detail,
        "has_deck_stage_element": has_el,
        "has_runtime": has_runtime,
        "static_px_dimensions": has_static_px,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the shipped deck uses the deck_stage.js scaling runtime."
    )
    parser.add_argument("--html", required=True, help="Path to the built HTML deck.")
    args = parser.parse_args()

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        print(f"ERROR: HTML file not found: {html_path}", file=sys.stderr)
        return 1

    html = html_path.read_text(encoding="utf-8", errors="replace")
    check = check_deck_stage(html)
    valid = check["pass"]

    report = {
        "valid": valid,
        "checked_at": now_iso(),
        "html_path": str(html_path),
        "checks": [check],
    }
    out_path = html_path.parent / "qa" / "deck-stage-report.json"
    write_json(out_path, report)

    status = "PASS" if valid else "FAIL"
    print(f"Deck-stage runtime: {status}")
    mark = "OK" if check["pass"] else "FAIL"
    print(f"  [{mark}] {check['name']}: {check['detail']}")
    if not valid and check["static_px_dimensions"]:
        print("  [HINT] Found fixed 1920/1080px dimension(s) — the likely "
              "hand-rolled static stage. Replace with the deck_stage.js runtime.")
    print(f"Report: {out_path}")

    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
