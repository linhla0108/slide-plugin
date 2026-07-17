#!/usr/bin/env python3
"""Resolve a per-user style profile against a scorer-owned selection report and
write a design-plan artifact.

The profile influences ONE behaviour: how the agent composes a slide the user has
already approved as `custom-local`. `score_visual_items.py` does NOT read the
profile, so nothing here changes a selection; `tie_break_advisories` are recorded
notes only. This script is the honest recorder of that influence: it validates the
profile, hashes it, and writes which preferences were APPLIED (to custom-local
composition) and
which were REJECTED (with reasons) because a higher-precedence layer wins — most
importantly, a profile may NOT drop a component the scorer already selected for a
`reuse` slide (fidelity-bound). `selection-report.json` is read ONLY and never
mutated. No new dependency, no network. See `rules/style-profiles.md`.

Usage:
  <project-python> slide-system/scripts/resolve_style_profile.py \
    --profile slide-system/style-profiles/<id>.json \
    --selection-report <run>/analysis/selection-report.json \
    --registry slide-system/registries/visual-library.json \
    --output <run>/analysis/design-plan.json
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from _common import load_json, now_iso, write_json
from validate_style_profile import validate_profile, ENUMS, ARRAY_KEYS

PRECEDENCE = ("approved-content/source-authority > brand-pack + accessibility/layout > "
              "component contracts + fidelity > user style profile > agent defaults "
              "(slide-system/rules/style-profiles.md)")

# Composition preferences that safely bias custom-local slides.
_COMPOSITION = set(ENUMS) | {"layout_families", "preferred_component_intents"}


def _intent_map(registry: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for it in registry.get("items", []):
        iid = it.get("id")
        if iid:
            out[iid] = {str(t).lower() for t in (it.get("intent") or []) + (it.get("tags") or [])}
    return out


def _decisions(report: dict) -> list[dict]:
    slides = report.get("slides")
    if isinstance(slides, list):
        return [s for s in slides if isinstance(s, dict)]
    return [report] if report.get("decision") or report.get("request_id") else []


def resolve(profile: dict, report: dict, intents: dict[str, set[str]]) -> dict:
    prefs = profile.get("preferences") or {}
    applied: list[dict] = []
    rejected: list[dict] = []
    tie_breaks: list[dict] = []

    # Which component intents are locked in by a scorer-selected `reuse` slide?
    # A profile cannot drop those (fidelity-bound). Collect per selected item.
    locked_intents: set[str] = set()
    for s in _decisions(report):
        dec = s.get("decision") or {}
        if dec.get("action") == "reuse" and dec.get("item_id"):
            locked_intents |= intents.get(dec["item_id"], set())

    for key, val in prefs.items():
        if key == "avoided_component_intents":
            for intent in val:
                if intent in locked_intents:
                    rejected.append({"preference": key, "value": intent,
                                     "reason": "a scorer-selected reuse component declares "
                                     "this intent; a style profile cannot drop a fidelity-bound "
                                     "component (component fidelity outranks the profile)"})
                else:
                    applied.append({"preference": key, "value": intent,
                                    "scope": "avoid this intent when composing custom-local slides"})
        elif key in _COMPOSITION:
            applied.append({"preference": key, "value": val,
                            "scope": "custom-local composition (user-approved slides only)"})
        else:  # unknown keys are already rejected by validation; keep defensive.
            rejected.append({"preference": key, "value": val,
                             "reason": "not an honoured preference key"})

    # Non-binding tie-break advisories: only where the scorer emitted >=2 equally
    # scored candidates in the SAME action band. A profile can nudge among ties,
    # never across the reuse / needs_component / custom-local thresholds.
    preferred = set(prefs.get("preferred_component_intents") or [])
    avoided = set(prefs.get("avoided_component_intents") or [])
    if preferred or avoided:
        for s in _decisions(report):
            rid = s.get("request_id", "?")
            dec = s.get("decision") or {}
            cands = s.get("candidates") or []
            top = [c for c in cands if isinstance(c, dict) and c.get("score") == dec.get("score")]
            if len(top) < 2:
                continue
            for c in top:
                cint = intents.get(c.get("item_id"), set())
                if (preferred & cint) and c.get("item_id") != dec.get("item_id"):
                    tie_breaks.append({"request_id": rid, "prefer_item": c.get("item_id"),
                                       "over_item": dec.get("item_id"), "binding": False,
                                       "note": "equally-scored candidate matches a preferred "
                                       "intent; advisory only — re-score to apply, never forces "
                                       "an incompatible or below-threshold item"})
                    break
    return {"applied_preferences": applied, "rejected_preferences": rejected,
            "tie_break_advisories": tie_breaks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record a style profile's influence in a design plan.")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--selection-report", required=True)
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)

    ppath = Path(args.profile)
    if not ppath.exists():
        print(f"ERROR: style profile not found: {ppath}", file=sys.stderr)
        return 1
    profile = load_json(ppath)
    errors = validate_profile(profile)
    if errors:
        print(f"ERROR: invalid style profile {ppath}:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    report = load_json(args.selection_report)
    registry = load_json(args.registry) if Path(args.registry).exists() else {"items": []}
    sha = hashlib.sha256(ppath.read_bytes()).hexdigest()

    resolved = resolve(profile, report, _intent_map(registry))
    plan = {
        "generated_at": now_iso(),
        "style_profile": {"profile_id": profile.get("profile_id"),
                          "version": profile.get("version"), "sha256": sha,
                          "path": str(ppath)},
        "precedence": PRECEDENCE,
        "selection_report": str(args.selection_report),
        "selection_report_mutated": False,
        **resolved,
        "notes": "selection-report.json is scorer-owned; read only, never modified. "
                 "The profile influences ONLY how a user-approved custom-local slide is "
                 "composed; the scorer does not read it, so tie_break_advisories are "
                 "non-binding notes, not selections. It never overrides brand tokens, "
                 "readability, canvas bounds, source content, or component fidelity.",
    }
    write_json(Path(args.output), plan)
    print(f"design-plan: {len(resolved['applied_preferences'])} applied, "
          f"{len(resolved['rejected_preferences'])} rejected, "
          f"{len(resolved['tie_break_advisories'])} tie-break advisory -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
