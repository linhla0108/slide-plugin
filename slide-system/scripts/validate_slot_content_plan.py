#!/usr/bin/env python3
"""Validate job-local copy against a selected component's native text slots.

The shared library deliberately stores geometry and typography, not generated
copy. This gate keeps generated copy in a run-local plan and rejects a reuse
mapping that needs unreadable text or more lines than the native slot holds.
It is a pre-build capacity gate; browser render-legibility remains the final
post-capture proof.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

from _common import load_json, resolve_repo_path, write_json
from component_units import repeat_unit_slots, unfilled_units


CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
AVERAGE_GLYPH_WIDTH = 0.56
MIN_FONT_PX = {
    "heading": 36,
    "title": 36,
    "body": 18,
    "list-item": 18,
    "label": 16,
    "footer": 16,
}

# Readability budget for copy inside a *repeated* visual unit (card, step,
# column, strip cell). Physical capacity is the wrong ceiling there: a card is
# scanned in about a second from across a room, so filling it to the last
# printable line produces four narrow ragged columns that technically fit and
# are unreadable in projection. These caps are display *lines* after wrapping,
# split by the unit's own role structure — one prominent primary line plus a
# short caption — and apply to no other slot on the deck.
#
# Authoring guidance is stricter than the gate (one label + one compact support
# line); the gate allows one extra line so a support line that wraps by a word
# is not rejected, and only fails copy that is genuinely over-dense.
#
# The primary cap applies only where the unit actually has a support tier. A
# unit drawn entirely in one type size has no label/caption distinction, so
# only the total budget constrains it — otherwise a flat card would be held to
# a third of the density allowed to a card that happens to have two type sizes.
UNIT_PRIMARY_MAX_LINES = 1
UNIT_TOTAL_MAX_LINES = 3


def _entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    return report.get("slides", []) if isinstance(report.get("slides"), list) else [report]


def _copy_length(value: str) -> int:
    return len(re.sub(r"\s+", " ", value).strip())


def slot_capacity(slot: dict[str, Any], source_view_height: float = CANVAS_HEIGHT) -> dict[str, int | float]:
    """Estimate one native slot's readable capacity from its actual contract.

    The estimate is intentionally conservative: it never authorizes shrinking
    below the role floor and is only used before browser measurement catches
    actual collisions/contrast after rendering.
    """
    bounds = slot.get("bounds") or {}
    typography = slot.get("typography") or {}
    font_source = float(typography.get("font_size") or 0)
    source_height = float(source_view_height or CANVAS_HEIGHT)
    font_px = font_source * CANVAS_HEIGHT / source_height
    line_height = float(typography.get("line_height") or 1.0)
    width_px = float(bounds.get("width") or 0) * CANVAS_WIDTH
    height_px = float(bounds.get("height") or 0) * CANVAS_HEIGHT
    chars_per_line = max(1, math.floor(width_px / max(font_px * AVERAGE_GLYPH_WIDTH, 1)))
    max_lines = max(1, math.floor(height_px / max(font_px * line_height, 1)))
    return {
        "font_px": round(font_px, 2),
        "min_font_px": MIN_FONT_PX.get(str(slot.get("role") or "body"), 18),
        "chars_per_line": chars_per_line,
        "max_lines": max_lines,
        "max_characters": chars_per_line * max_lines,
    }


def _display_lines(copy: str, slot: dict[str, Any], view_height: float) -> int:
    """Wrapped display lines this copy needs in this slot, never below one."""
    capacity = slot_capacity(slot, view_height)
    chars_per_line = max(1, int(capacity["chars_per_line"]))
    return max(1, math.ceil(_copy_length(copy) / chars_per_line))


def overdense_units(contract: dict[str, Any], copy_by_slot: dict[str, str],
                    view_height: float) -> list[str]:
    """Repeated units whose mapped copy busts the readability budget.

    Reported per unit so the diagnostic can name the exact card and slots to
    compact, rather than blaming the component.
    """
    def measure(slots: list[dict[str, Any]]) -> tuple[int, list[str]]:
        filled = [(str(s.get("id")), copy_by_slot[str(s.get("id"))], s)
                  for s in slots if str(s.get("id")) in copy_by_slot]
        return (sum(_display_lines(copy, slot, view_height) for _, copy, slot in filled),
                [slot_id for slot_id, _, _ in filled])

    findings: list[str] = []
    for unit in repeat_unit_slots(contract):
        primary_lines, primary_ids = measure(unit["primary"])
        support_lines, support_ids = measure(unit["support"])
        if not primary_ids and not support_ids:
            continue
        where = f"{unit['label']} {unit['index']} of {unit['unit_count']}"
        if unit["support"] and primary_lines > UNIT_PRIMARY_MAX_LINES:
            findings.append(
                f"repeated {where}: label copy fills {primary_lines} display lines across "
                f"{', '.join(repr(i) for i in primary_ids)} (budget {UNIT_PRIMARY_MAX_LINES}); a repeated "
                f"unit is scanned, not read, so its label must be one short phrase and the rest of the "
                f"detail belongs in speaker notes"
            )
            continue  # one actionable finding per unit; compacting the label also relieves the total
        total = primary_lines + support_lines
        if total > UNIT_TOTAL_MAX_LINES:
            findings.append(
                f"repeated {where}: copy fills {total} display lines across "
                f"{', '.join(repr(i) for i in primary_ids + support_ids)} (budget "
                f"{UNIT_TOTAL_MAX_LINES}); keep one short label plus at most one compact support line "
                f"per unit and move the detail to speaker notes"
            )
    return findings


def validate_plan(plan: dict[str, Any], selection_report: dict[str, Any],
                  contracts: dict[str, dict[str, Any]]) -> list[str]:
    """Return all actionable contract failures without mutating a run."""
    errors: list[str] = []
    plan_slides = plan.get("slides") if isinstance(plan.get("slides"), list) else []
    by_request = {entry.get("request_id"): entry for entry in plan_slides
                  if isinstance(entry, dict) and entry.get("request_id")}
    for selected in _entries(selection_report):
        decision = selected.get("decision") or {}
        if decision.get("action") != "reuse":
            continue
        request_id = selected.get("request_id")
        item_id = decision.get("item_id")
        entry = by_request.get(request_id)
        prefix = f"slide {request_id!r}"
        if not entry:
            errors.append(f"{prefix}: missing a reuse entry in slot-content-plan.json")
            continue
        if entry.get("item_id") != item_id:
            errors.append(f"{prefix}: plan item_id {entry.get('item_id')!r} does not match selected {item_id!r}")
            continue
        contract = contracts.get(str(item_id))
        if not contract:
            errors.append(f"{prefix}: text-slot contract for {item_id!r} is unavailable")
            continue
        source = contract.get("source") or {}
        view_box = source.get("view_box") if isinstance(source, dict) else None
        view_height = view_box[3] if isinstance(view_box, list) and len(view_box) == 4 else CANVAS_HEIGHT
        known_slots = {slot.get("id"): slot for slot in contract.get("slots", []) if isinstance(slot, dict)}
        used_slots: set[str] = set()
        copy_by_slot: dict[str, str] = {}
        for mapping in entry.get("slots") or []:
            slot_id = mapping.get("slot_id") if isinstance(mapping, dict) else None
            copy = mapping.get("display_copy") if isinstance(mapping, dict) else None
            if not slot_id or not isinstance(copy, str) or not copy.strip():
                errors.append(f"{prefix}: every plan slot needs non-empty slot_id and display_copy")
                continue
            if slot_id in used_slots:
                errors.append(f"{prefix}: slot {slot_id!r} is mapped more than once")
                continue
            used_slots.add(slot_id)
            slot = known_slots.get(slot_id)
            if not slot:
                errors.append(f"{prefix}: slot {slot_id!r} is not in selected component {item_id!r}")
                continue
            copy_by_slot[str(slot_id)] = copy
            capacity = slot_capacity(slot, view_height)
            if capacity["font_px"] < capacity["min_font_px"]:
                errors.append(
                    f"{prefix}: slot {slot_id!r} native font {capacity['font_px']}px is below the projection floor "
                    f"{capacity['min_font_px']}px; choose another slot/component"
                )
            actual = _copy_length(copy)
            if actual > capacity["max_characters"]:
                errors.append(
                    f"{prefix}: slot {slot_id!r} copy ({actual} chars) exceeds native capacity "
                    f"({capacity['max_characters']} chars, {capacity['max_lines']} line(s)); shorten it or choose another component"
                )
        # Per-unit readability. Per-slot capacity authorizes copy up to the last
        # line that physically fits, which is far past the point where a
        # repeated card stays scannable in projection.
        for finding in overdense_units(contract, copy_by_slot, view_height):
            errors.append(f"{prefix}: {finding}")
        # Visual-unit completeness. Per-slot capacity is blind to the fact that
        # a component draws its cards/steps/columns whether or not copy lands in
        # them, so a plan can pass every slot check and still ship a half-empty
        # grid. Once a repeated unit is engaged, every drawn sibling must carry
        # copy; units the plan never touched stay free to be left empty.
        for finding in unfilled_units(contract, used_slots):
            missing = "; ".join(
                f"unit {u['index']} [{', '.join(u['slot_ids'])}]" for u in finding["empty_units"]
            )
            errors.append(
                f"{prefix}: repeated {finding['label']} is unfinished — "
                f"{finding['filled_units']} of {finding['unit_count']} native unit(s) carry copy, so "
                f"{len(finding['empty_units'])} drawn unit(s) would ship blank. Fill every unit, or "
                f"reselect a component that repeats {finding['filled_units']} unit(s). "
                f"Empty: {missing}"
            )
    return errors


def _contracts_from_registry(registry: dict[str, Any], selected_ids: set[str]) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for item in registry.get("items", []):
        item_id = item.get("id")
        if item_id not in selected_ids:
            continue
        slots_path = (item.get("paths") or {}).get("text_slots")
        if not slots_path:
            continue
        # Registry paths are repo-relative. Resolving against the repo root
        # rather than the CWD keeps the gates that depend on these contracts
        # from silently degrading to "no contract, nothing to check".
        path = resolve_repo_path(slots_path)
        if path.is_file():
            contracts[item_id] = load_json(path)
    return contracts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate run-local component copy against native slot capacity.")
    parser.add_argument("--plan", required=True, help="analysis/slot-content-plan.json")
    parser.add_argument("--selection-report", required=True)
    parser.add_argument("--registry", default=str(Path(__file__).resolve().parents[1] / "registries" / "visual-library.json"))
    parser.add_argument("--out", default=None, help="Write a JSON validation report here")
    args = parser.parse_args()
    plan = load_json(args.plan)
    report = load_json(args.selection_report)
    selected_ids = {
        entry.get("decision", {}).get("item_id") for entry in _entries(report)
        if entry.get("decision", {}).get("action") == "reuse"
    }
    contracts = _contracts_from_registry(load_json(args.registry), {x for x in selected_ids if x})
    errors = validate_plan(plan, report, contracts)
    payload = {"pass": not errors, "errors": errors, "reuse_count": len(selected_ids)}
    if args.out:
        write_json(args.out, payload)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if not errors:
        print(f"slot-content-plan: PASS ({len(selected_ids)} reuse slide(s))")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
