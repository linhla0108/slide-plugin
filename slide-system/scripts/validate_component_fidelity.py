#!/usr/bin/env python3
"""T3 — fidelity safety net: prove reuse/adapt-local slides actually use the component.

The signal is structural, not textual: a real preview.html has only `.bg` and
`.slot` classes, so class-name overlap is meaningless. Instead we match on the
component's `data-slot-id` set (preserved verbatim by the T2 scaffold) plus the
presence of a `.bg` layer. Slot IDs are language-independent because the
scaffold copies them from preview.html rather than regenerating them from the
(Vietnamese) deck copy.

Coverage is computed against the whole deck (a coarse safety net, per the plan):
the goal is to catch hand-drawn slides that ignored the component, not to police
exact per-slide placement. Run with --warn during rollout; drop --warn to make
it BLOCKING once a scaffold-built deck passes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import load_json, now_iso, write_json

SLOT_ID_RE = re.compile(r'data-slot-id="([^"]+)"')
BG_RE = re.compile(r'class="[^"]*\bbg\b[^"]*"', re.IGNORECASE)

REUSE_MIN = 0.70
ADAPT_MIN = 0.40


def _slot_ids(html: str) -> set[str]:
    return set(SLOT_ID_RE.findall(html))


def _preview_map(registry: dict) -> dict[str, str]:
    return {
        item.get("id"): (item.get("paths") or {}).get("preview")
        for item in registry.get("items", [])
        if (item.get("paths") or {}).get("preview")
    }


def _decisions(report: dict) -> list[tuple[str, dict]]:
    if isinstance(report.get("slides"), list):
        return [(s.get("request_id", "?"), s.get("decision") or {})
                for s in report["slides"] if isinstance(s, dict)]
    return [(report.get("request_id", "?"), report.get("decision") or {})]


def check_fidelity(deck_html: str, report: dict, registry: dict) -> list[dict]:
    preview_map = _preview_map(registry)
    deck_slot_ids = _slot_ids(deck_html)
    deck_has_bg = bool(BG_RE.search(deck_html))
    results: list[dict] = []

    for rid, dec in _decisions(report):
        action = dec.get("action", "")
        item_id = dec.get("item_id")
        if action not in ("reuse", "adapt-local") or not item_id:
            continue

        preview_path = preview_map.get(item_id)
        entry = {"request_id": rid, "item_id": item_id, "action": action}

        if not preview_path:
            entry.update(pass_=False, reason=f"item {item_id!r} missing paths.preview "
                         f"(pass the full registry, not compact)")
            results.append(entry)
            continue

        p = Path(preview_path)
        if not p.exists():
            entry.update(pass_=False, reason=f"preview.html not found: {preview_path}")
            results.append(entry)
            continue

        comp_ids = _slot_ids(p.read_text(encoding="utf-8", errors="replace"))
        if not comp_ids:
            # No slots to match on — fall back to data-base-component presence.
            used = f'data-base-component="{item_id}"' in deck_html
            entry.update(pass_=used, coverage=None,
                         reason="component has no slots; matched on data-base-component"
                         if used else "no slots and no data-base-component marker in deck")
            results.append(entry)
            continue

        present = comp_ids & deck_slot_ids
        coverage = len(present) / len(comp_ids)
        threshold = REUSE_MIN if action == "reuse" else ADAPT_MIN
        ok = coverage >= threshold and deck_has_bg
        reasons = []
        if coverage < threshold:
            reasons.append(f"slot-id coverage {coverage:.0%} < {threshold:.0%} "
                           f"({len(present)}/{len(comp_ids)} ids present)")
        if not deck_has_bg:
            reasons.append("no .bg layer found in deck")
        entry.update(pass_=ok, coverage=round(coverage, 3),
                     threshold=threshold,
                     reason="; ".join(reasons) if reasons else "fidelity ok")
        results.append(entry)

    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate deck slides use their selected components.")
    ap.add_argument("--html", required=True)
    ap.add_argument("--selection-report", required=True)
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--warn", action="store_true",
                    help="Report failures but always exit 0 (rollout mode).")
    args = ap.parse_args()

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        print(f"ERROR: HTML not found: {html_path}", file=sys.stderr)
        return 1

    deck_html = html_path.read_text(encoding="utf-8", errors="replace")
    report = load_json(args.selection_report)
    registry = load_json(args.registry)

    results = check_fidelity(deck_html, report, registry)
    failed = [r for r in results if not r["pass_"]]
    valid = not failed

    out = {
        "valid": valid,
        "checked_at": now_iso(),
        "html_path": str(html_path),
        "warn_only": args.warn,
        "results": results,
    }
    write_json(html_path.parent / "qa" / "component-fidelity-report.json", out)

    status = "PASS" if valid else ("WARN" if args.warn else "FAIL")
    print(f"component_fidelity: {status} ({len(results)} reuse/adapt slide(s) checked)")
    for r in results:
        mark = "OK" if r["pass_"] else "FAIL"
        cov = f" cov={r['coverage']:.0%}" if r.get("coverage") is not None else ""
        print(f"  [{mark}] {r['request_id']} {r['item_id']} ({r['action']}){cov}: {r['reason']}")

    if valid or args.warn:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
