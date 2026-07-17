#!/usr/bin/env python3
"""delivery_gate.py — a job with any UNRESOLVED slide is NOT a deliverable.

A selection decision of ``needs_component`` means the slide is UNRESOLVED: the
user has not yet chosen a published component, explicitly left it blank, or
approved a custom-local slide. Per ``.agents/skills/slide-generator/SKILL.md``
the system must NOT invent a layout or export a styled diagnostic placeholder
deck that leaks internal component ids / audit reasons / QA text — it takes the
job to the user for library review.

This gate reads a selection-report (batch or single) and fails closed on any
unresolved slide, so no final PPTX/PDF deliverable is produced until every slide
is explicitly resolved through one of exactly three user paths:

  * an explicit published component_id   -> decision.action == "reuse"
  * an explicit blank choice             -> decision.action == "blank"
  * an explicit custom-local approval    -> decision.action == "custom-local"

``selection-report.json`` (shortlist / reason / suggested_search / next_action)
is PRESERVED untouched for the catalog + resolution UI — it is the diagnostic
input that drives library review, never end-user slide content. The gate never
mutates the report and never emits the internal ``reason`` into any deliverable
or user-facing message.

Usage:
    delivery_gate.py --selection-report <run>/analysis/selection-report.json
    delivery_gate.py --deck <run>/deck.html   # gate the run at an output boundary
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# A terminal decision resolves the slide only when its provenance matches the
# product contract (see ``resolution_of``); every other decision keeps the job
# undeliverable. ``needs_component`` is the one automatic UNRESOLVED outcome.
#
#   * ``reuse``        — automatic scorer high-confidence OR explicit user pick;
#                        resolved ONLY when it names a non-empty component id.
#   * ``custom-local`` — explicit user approval ONLY (``selected_by == "user"``).
#   * ``blank``        — explicit user choice ONLY (``selected_by == "user"``).
#
# ``custom-local``/``blank`` are never scorer-automatic, so a hand-edited report
# that carries the action string without user provenance must NOT turn an
# unresolved job into a final delivery — those fail closed as ``unknown``.
USER_ONLY_ACTIONS = ("custom-local", "blank")
UNRESOLVED_ACTION = "needs_component"

AWAITING = "awaiting_component_selection"
COMPLETE = "complete"

# The published full registry is the delivery authority for reuse: a ``reuse``
# decision may only name a component that actually exists AND is ``published``
# there. Located the same way the rest of the pipeline locates it (relative to
# this script, no import of the heavy build_registry chain), so the gate stays
# pure-stdlib and can run standalone from the JS PDF exporter.
REGISTRY = Path(__file__).resolve().parents[1] / "registries" / "visual-library.json"


def published_item_ids(registry_path: str | Path | None = None) -> frozenset[str]:
    """IDs of ``published`` items in the full registry — the set a ``reuse``
    decision must name to be a valid deliverable. Defaults to the repo's
    ``visual-library.json``; tests pass a temporary/fixture registry so product
    code never carries a hardcoded component id. Fails closed (empty set) when
    the registry cannot be read, so a broken registry blocks reuse rather than
    silently accepting any id."""
    path = Path(registry_path) if registry_path is not None else REGISTRY
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    return frozenset(
        it["id"] for it in registry.get("items", [])
        if isinstance(it, dict) and it.get("id") and it.get("status") == "published")


def slide_decisions(report: dict) -> list[tuple[str | None, dict | None]]:
    """(request_id, decision) pairs for a batch OR a single selection-report.

    For a batch (``slides`` is a list), an invalid (non-dict) slide record yields
    ``(None, None)`` instead of being silently dropped, so the caller can fail it
    closed as ``unknown`` rather than treat the job as vacuously deliverable."""
    if "slides" in report:
        if not isinstance(report["slides"], list):
            return [(None, None)]
        return [(s.get("request_id"), s.get("decision") or {})
                if isinstance(s, dict) else (None, None)
                for s in report["slides"]]
    if not isinstance(report.get("request_id"), str) or not report["request_id"].strip():
        return [(None, None)]
    if not isinstance(report.get("decision"), dict):
        return [(None, None)]
    return [(report["request_id"], report["decision"])]


def resolution_of(decision: dict, published_ids: frozenset[str] | None = None) -> str:
    """Classify one decision: a resolved action name, "unresolved", or "unknown".

    Fails closed on malformed / non-explicit decisions so a hand-edited
    selection-report cannot promote an unresolved job to a deliverable:
      * ``reuse`` resolves ONLY with a non-empty string ``item_id`` that names a
        component present AND ``published`` in the full registry (when
        ``published_ids`` is supplied); an arbitrary / staging / unpublished id
        fails closed as ``unknown``. Legitimate scorer-automatic reuse and
        explicit user reuse both name a real published id, so both still pass;
      * ``custom-local`` / ``blank`` resolve ONLY as an explicit user choice
        (``selected_by == "user"``) — they are never scorer-automatic;
      * ``needs_component`` is UNRESOLVED; anything else is ``unknown``.
    Every non-conforming decision returns ``unknown`` and blocks delivery.

    ``published_ids`` is the resolved published-id set; ``None`` skips the
    registry check (callers that want it pass the set — ``delivery_state`` loads
    the real registry by default).
    """
    decision = decision or {}
    action = decision.get("action")
    if action == "reuse":
        item_id = decision.get("item_id")
        if isinstance(item_id, str) and item_id.strip():
            if published_ids is not None and item_id.strip() not in published_ids:
                return "unknown"
            return action
        return "unknown"
    if action in USER_ONLY_ACTIONS:
        if decision.get("selected_by") == "user":
            return action
        return "unknown"
    if action == UNRESOLVED_ACTION:
        return "unresolved"
    return "unknown"


def _catalog_hint(rid: str | None, decision: dict) -> dict:
    """The catalog/UI-safe pointer for one unresolved slide. Deliberately EXCLUDES
    the internal diagnostic ``reason`` so it can never leak into anything
    end-user-facing — only the fields the schema marks for the catalog/UI."""
    return {
        "request_id": rid,
        "suggested_search": decision.get("suggested_search", []),
        "next_action": decision.get("next_action", ""),
        "shortlist": [c.get("item_id") for c in decision.get("shortlist", [])
                      if isinstance(c, dict)],
    }


def delivery_state(report: dict, published_ids: frozenset[str] | None = None) -> dict:
    """Whole-job resolution state derived from the selection-report.

    ``published_ids`` defaults to the published ids in the repo's full registry
    so a ``reuse`` decision must name a real published component; tests inject a
    fixture set."""
    if published_ids is None:
        published_ids = published_item_ids()
    slides: list[dict] = []
    unresolved: list[dict] = []
    unknown: list[str | None] = []
    for rid, dec in slide_decisions(report):
        if not isinstance(dec, dict):
            # Invalid slide record (non-dict) — fail closed, never drop silently.
            slides.append({"request_id": rid, "resolution": "unknown"})
            unknown.append(rid)
            continue
        res = resolution_of(dec, published_ids)
        slides.append({"request_id": rid, "resolution": res})
        if res == "unresolved":
            unresolved.append(_catalog_hint(rid, dec))
        elif res == "unknown":
            unknown.append(rid)
    # Fail closed on a report with zero usable slide records: an empty/wholly
    # malformed job is NOT vacuously deliverable. (A single-report input always
    # yields exactly one record, so that supported form is unaffected.)
    empty = not slides
    deliverable = bool(slides) and not unresolved and not unknown
    return {
        "status": COMPLETE if deliverable else AWAITING,
        "deliverable": deliverable,
        "slides": slides,
        "unresolved": unresolved,
        "unknown_actions": unknown,
        "empty": empty,
    }


def assert_deliverable(report: dict, published_ids: frozenset[str] | None = None) -> dict:
    """Return the state when the job is deliverable; else raise ``SystemExit`` with
    a catalog-safe message (never containing the internal diagnostic ``reason``)."""
    state = delivery_state(report, published_ids)
    if state["deliverable"]:
        return state
    if state.get("empty"):
        raise SystemExit(
            "delivery blocked: selection-report has no usable slide records "
            "(empty or malformed) — regenerate it with score_visual_items.py.")
    if state["unknown_actions"]:
        raise SystemExit(
            "delivery blocked: selection-report carries unknown decision action(s) for "
            f"slide(s) {state['unknown_actions']} — regenerate it with score_visual_items.py.")
    ids = [u["request_id"] for u in state["unresolved"]]
    raise SystemExit(
        f"delivery blocked: {len(ids)} slide(s) are UNRESOLVED (needs_component): {ids}. "
        "Per slide-generator/SKILL.md an unresolved job is NOT a deliverable — no deck / PPTX / "
        "PDF is produced. Resolve each slide in analysis/visual-requests.json (an explicit "
        "component_id, `unresolved_policy: \"blank\"`, or `unresolved_policy: \"custom-local\"`) "
        "and re-run the scorer. Preview the shortlist / suggested_search in the catalog.")


def find_selection_report(deck_html: str | Path) -> Path | None:
    """The run's scorer output lives at ``<run>/analysis/selection-report.json``,
    next to ``<run>/deck.html``. Returns the path if present, else None."""
    candidate = Path(deck_html).resolve().parent / "analysis" / "selection-report.json"
    return candidate if candidate.is_file() else None


def enforce_deck_deliverable(deck_html: str | Path,
                             published_ids: frozenset[str] | None = None) -> dict | None:
    """Export-time guard: block a final deliverable when the run's selection-report
    has any unresolved slide. No report next to the deck => nothing to gate here
    (a custom deck with no scorer output is exported by the normal QA gates)."""
    report_path = find_selection_report(deck_html)
    if report_path is None:
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return assert_deliverable(report, published_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--selection-report",
                        help="Gate a selection-report directly (batch or single).")
    source.add_argument("--deck",
                        help="Gate a run's deck.html via its sibling "
                             "analysis/selection-report.json — the guard the PDF/PPTX "
                             "output boundary uses. A deck with no sibling report "
                             "(external/custom) is not gated here.")
    args = parser.parse_args(argv)
    if args.deck:
        # Raises SystemExit with a catalog-safe message (never the internal
        # `reason`) on an unresolved/unknown job; returns on a deliverable or an
        # ungated external deck.
        state = enforce_deck_deliverable(args.deck)
        print(json.dumps({"deliverable": True, "gated": state is not None},
                         indent=2, ensure_ascii=False))
        return 0
    report = json.loads(Path(args.selection_report).read_text(encoding="utf-8"))
    state = delivery_state(report)
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0 if state["deliverable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
