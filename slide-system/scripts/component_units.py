#!/usr/bin/env python3
"""Infer repeatable visual units from a published component's slot geometry.

A published component is a visual grammar. Most of them repeat one small unit —
a card, a step node, a column, a tier row — and the artwork for every repeat is
already drawn. Slot-level capacity checks cannot see that: each mapped slot can
fit its copy perfectly while half the drawn cards ship blank.

This module derives the repeat structure from the component's own text-slot
contract (normalized bounds + typography), so it works for any published item
and knows nothing about item ids, page ids, component names, or source decks.

Model, in three steps:

1. ``content_slots`` drops page chrome. Chrome is defined geometrically: a slot
   that starts inside the top or bottom page margin is a running header, footer,
   or page number, never a content unit.
2. ``cluster_units`` groups the remaining slots into units by spatial adjacency.
   Slots that sit within ``MERGE_GAP`` of each other belong to the same drawn
   unit; the visible gutters between cards/columns/rows are wider than that.
3. ``repeat_groups`` collects units that are congruent — same anchor typography
   and anchor height — into repeat groups of two or more. A slide title, a
   standalone kicker, or a decorative label has no congruent sibling, so it
   forms no group and stays free to be left empty.

The two consumers are ``validate_selection_report`` (is this component's unit
model compatible with the requested item count?) and
``validate_slot_content_plan`` (does the plan fill every unit it engages?).
"""

from __future__ import annotations

from typing import Any, Iterable

# Page chrome bands. A slot whose top edge starts inside either margin is a
# running header/footer/page number rather than part of a content unit.
CHROME_TOP_Y = 0.10
CHROME_BOTTOM_Y = 0.88

# Normalized gap that still counts as "the same drawn unit". Real card gutters,
# column gutters, and row gaps in published slides are wider than this; lines
# inside one card are closer.
MERGE_GAP = 0.030

# Two units are congruent when their anchor slots share typography and height.
FONT_TOLERANCE = 0.75
HEIGHT_TOLERANCE = 0.004

# Display-surface detection. A quote/callout panel is a short, non-repeating
# unit set in display type next to a much denser working surface. All three
# conditions are required, because each alone has honest counter-examples:
# a section label is large but not isolated, a column header is short but not
# display type, and a sparse unit is short but not typographically dominant.
TITLE_BAND_Y = 0.25          # above this is the slide's own title, not content
DISPLAY_FONT_RATIO = 1.4     # vs the densest content surface's own type
DISPLAY_MIN_FONT_PX = 40.0   # below this it is a header/label, not display type
DISPLAY_MAX_SLOTS = 3        # a pull-quote is short by construction
DISPLAY_DENSITY_RATIO = 2    # the working surface must be clearly denser

CANVAS_HEIGHT = 1080.0


def _view_height(contract: dict[str, Any]) -> float:
    source = contract.get("source")
    view_box = source.get("view_box") if isinstance(source, dict) else None
    if isinstance(view_box, list) and len(view_box) == 4:
        try:
            height = float(view_box[3])
        except (TypeError, ValueError):
            return CANVAS_HEIGHT
        if height > 0:
            return height
    return CANVAS_HEIGHT


def _font_px(slot: dict[str, Any], view_height: float) -> float:
    typography = slot.get("typography") or {}
    try:
        raw = float(typography.get("font_size") or 0)
    except (TypeError, ValueError):
        raw = 0.0
    return raw * CANVAS_HEIGHT / (view_height or CANVAS_HEIGHT)


def _box(slot: dict[str, Any]) -> tuple[float, float, float, float]:
    bounds = slot.get("bounds") or {}

    def num(key: str) -> float:
        try:
            return float(bounds.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return num("x"), num("y"), num("width"), num("height")


def content_slots(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Slots that can carry unit content, with page chrome removed."""
    out: list[dict[str, Any]] = []
    for slot in contract.get("slots") or []:
        if not isinstance(slot, dict) or not slot.get("id"):
            continue
        _, y, _, _ = _box(slot)
        if y <= CHROME_TOP_Y or y >= CHROME_BOTTOM_Y:
            continue
        out.append(slot)
    return out


def _adjacent(a: dict[str, Any], b: dict[str, Any], gap: float) -> bool:
    ax, ay, aw, ah = _box(a)
    bx, by, bw, bh = _box(b)
    return (ax - gap < bx + bw and bx - gap < ax + aw
            and ay - gap < by + bh and by - gap < ay + ah)


def cluster_units(slots: list[dict[str, Any]], gap: float = MERGE_GAP) -> list[list[dict[str, Any]]]:
    """Group slots into drawn units by spatial adjacency (union-find)."""
    parent = list(range(len(slots)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(slots)):
        for j in range(i + 1, len(slots)):
            if _adjacent(slots[i], slots[j], gap):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    buckets: dict[int, list[dict[str, Any]]] = {}
    for i, slot in enumerate(slots):
        buckets.setdefault(find(i), []).append(slot)
    units = list(buckets.values())
    # Deterministic reading order: top-to-bottom, then left-to-right.
    units.sort(key=lambda unit: (round(min(_box(s)[1] for s in unit), 3),
                                 round(min(_box(s)[0] for s in unit), 3)))
    return units


def _anchor(unit: list[dict[str, Any]], view_height: float) -> dict[str, Any]:
    """The unit's most prominent slot — largest type, then tallest box."""
    return max(unit, key=lambda s: (_font_px(s, view_height), _box(s)[3]))


def repeat_groups(units: list[list[dict[str, Any]]], view_height: float = CANVAS_HEIGHT) -> list[dict[str, Any]]:
    """Congruent units, grouped. Only groups of two or more are repeats."""
    buckets: list[dict[str, Any]] = []
    for unit in units:
        anchor = _anchor(unit, view_height)
        font_px = _font_px(anchor, view_height)
        height = _box(anchor)[3]
        for bucket in buckets:
            if (abs(bucket["font_px"] - font_px) <= FONT_TOLERANCE
                    and abs(bucket["height"] - height) <= HEIGHT_TOLERANCE):
                bucket["units"].append(unit)
                break
        else:
            buckets.append({"font_px": font_px, "height": height, "units": [unit]})
    groups = [b for b in buckets if len(b["units"]) >= 2]
    for group in groups:
        group["label"] = f"{round(group['font_px'])}px unit"
        group["slot_ids"] = [[str(s.get("id")) for s in unit] for unit in group["units"]]
    return groups


def unit_model(contract: dict[str, Any]) -> dict[str, Any]:
    """Full unit model for one text-slot contract.

    ``primary_unit_count`` is the repeat count a request's ``item_count`` must
    match: the largest repeat group, breaking ties by total slot count so the
    denser (more content-bearing) grammar wins. ``None`` means the component
    declares no repeat structure, which is unknown rather than incompatible.
    """
    view_height = _view_height(contract)
    units = cluster_units(content_slots(contract))
    groups = repeat_groups(units, view_height)
    primary = None
    if groups:
        primary = max(groups, key=lambda g: (len(g["units"]),
                                             sum(len(u) for u in g["units"])))
    return {
        "unit_count": len(units),
        "groups": groups,
        "primary": primary,
        "primary_unit_count": len(primary["units"]) if primary else None,
    }


def display_surface(contract: dict[str, Any]) -> dict[str, Any] | None:
    """A dominant non-repeating quote/callout panel, or None.

    This is the grammar behind a two-panel editorial slide: a short pull-quote
    or statement set in display type on one side, and a dense working surface
    on the other. Such a component hosts a *statement*, not a set of parallel
    items — pointing a four-principle brief at it leaves the display panel
    mostly empty while the principles pile into the dense side.

    Detected from typography and slot counts only. The slide's own title is
    excluded by band, repeat-group members are excluded because they are the
    component's parallel grammar, and the densest unit is excluded because it
    is the working surface being compared against.
    """
    view_height = _view_height(contract)
    units = cluster_units(content_slots(contract))
    repeating = {id(unit) for group in repeat_groups(units, view_height)
                 for unit in group["units"]}
    content = [u for u in units if min(_box(s)[1] for s in u) >= TITLE_BAND_Y]
    if len(content) < 2:
        return None
    densest = max(content, key=len)
    body_px = _font_px(_anchor(densest, view_height), view_height)
    candidates = [u for u in content if id(u) not in repeating and u is not densest]
    if not candidates:
        return None
    panel = max(candidates, key=lambda u: _font_px(_anchor(u, view_height), view_height))
    panel_px = _font_px(_anchor(panel, view_height), view_height)
    if (panel_px < DISPLAY_MIN_FONT_PX
            or panel_px < DISPLAY_FONT_RATIO * body_px
            or len(panel) > DISPLAY_MAX_SLOTS
            or len(densest) < DISPLAY_DENSITY_RATIO * len(panel)):
        return None
    return {
        "font_px": round(panel_px, 1),
        "slot_ids": [str(s.get("id")) for s in panel],
        "body_font_px": round(body_px, 1),
        "body_slot_count": len(densest),
    }


def unit_profile(contract: dict[str, Any]) -> dict[str, Any]:
    """The layout-grammar facts selection needs from one component."""
    model = unit_model(contract)
    return {
        "unit_count": model["primary_unit_count"],
        "group_sizes": sorted(len(group["units"]) for group in model["groups"]),
        "display_surface": display_surface(contract),
    }


def primary_unit_counts(contracts: dict[str, dict[str, Any]]) -> dict[str, int]:
    """item_id -> primary repeat count, skipping items with no repeat model."""
    counts: dict[str, int] = {}
    for item_id, contract in contracts.items():
        count = unit_model(contract).get("primary_unit_count")
        if isinstance(count, int):
            counts[str(item_id)] = count
    return counts


def repeat_unit_slots(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Every drawn unit of every repeat group, split into primary and support.

    A repeated card/step/column is scanned, not read: the eye lands on one
    prominent line and takes the rest as a caption. ``primary`` holds the label
    slots — everything set in the same type as the unit's anchor, the same
    anchor ``repeat_groups`` uses to decide congruence — and ``support`` holds
    the rest. Several slots can share the anchor's type when a component was
    extracted with alternate label variants stacked in one unit, so primary is
    a list rather than a single slot. Consumers use this to budget copy per
    role instead of per raw slot.

    Non-repeating units (a slide title, a lone kicker, a pull-quote) are absent
    by construction, so a long-form or headline slot is never budgeted here.
    """
    view_height = _view_height(contract)
    units = cluster_units(content_slots(contract))
    out: list[dict[str, Any]] = []
    for group in repeat_groups(units, view_height):
        for index, unit in enumerate(group["units"], start=1):
            anchor = _anchor(unit, view_height)
            anchor_px, anchor_h = _font_px(anchor, view_height), _box(anchor)[3]
            primary = [s for s in unit
                       if abs(_font_px(s, view_height) - anchor_px) <= FONT_TOLERANCE
                       and abs(_box(s)[3] - anchor_h) <= HEIGHT_TOLERANCE]
            out.append({
                "label": group["label"],
                "index": index,
                "unit_count": len(group["units"]),
                "primary": primary,
                "support": [slot for slot in unit if slot not in primary],
            })
    return out


def unfilled_units(contract: dict[str, Any], filled_slot_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Repeat groups the plan engaged but did not finish.

    A group is *engaged* when at least one of its units carries copy. Once a
    repeated grammar is engaged, every drawn sibling must carry copy too —
    otherwise the deck ships visibly blank cards, columns, or steps. Groups the
    plan never touched are untouched by design and are not reported here.
    """
    filled = {str(s) for s in filled_slot_ids}
    findings: list[dict[str, Any]] = []
    for group in unit_model(contract)["groups"]:
        states = [bool(filled & {str(s.get("id")) for s in unit}) for unit in group["units"]]
        if not any(states) or all(states):
            continue
        findings.append({
            "label": group["label"],
            "unit_count": len(group["units"]),
            "filled_units": sum(states),
            "empty_units": [{"index": i + 1, "slot_ids": ids}
                            for i, (ids, state) in enumerate(zip(group["slot_ids"], states))
                            if not state],
        })
    return findings
