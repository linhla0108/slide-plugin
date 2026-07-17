#!/usr/bin/env python3
"""T3 — fidelity safety net: prove `reuse` slides actually use the component.

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
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import load_json, now_iso, write_json
import build_registry

_MEASURE_JS = Path(__file__).resolve().parent / "measure_deck_slots.js"

# Canvas the reuse pipeline renders every slide onto, and how much of a component's
# artwork may fall off it before automatic full-bleed reuse is unfit for an audience.
# 0.30 sits in the wide gap between the library's full-slide/near-16:9 items (<=0.16
# crop) and its wide-band strips (>=0.33) — see render_fitness.
CANVAS_W, CANVAS_H = 1920, 1080
MAX_COVER_CROP = 0.30


def _node_available() -> bool:
    return bool(shutil.which("node")) and _MEASURE_JS.exists()


def cover_crop_fraction(viewbox_w: float, viewbox_h: float,
                        canvas_w: int = CANVAS_W, canvas_h: int = CANVAS_H) -> float:
    """Fraction of an artwork's LONGER axis that a full-bleed `background-size:cover`
    materialization pushes outside the canvas. 0 when the artwork already matches the
    canvas aspect (full-slide 16:9 templates lose nothing); it grows as the aspect
    diverges. A wide band forced to fill 16:9 is scaled up until its height covers the
    frame, so a large slice of its width — its OUTER content — is simply not on the
    slide. Pure geometry: deterministic, no rendering, no dependency."""
    if viewbox_w <= 0 or viewbox_h <= 0:
        return 0.0
    art, can = viewbox_w / viewbox_h, canvas_w / canvas_h
    return 1.0 - min(can / art, art / can)


def _visual_viewbox(item: dict) -> tuple[float, float] | None:
    """The width/height of the item's visual.svg drawing space, from its viewBox (or
    width/height). None when the item declares no readable visual."""
    visual = (item.get("paths") or {}).get("visual")
    if not visual:
        return None
    target = build_registry.resolve_repo_path(visual)
    if not target.is_file():
        return None
    svg = target.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'viewBox\s*=\s*"([\d.\seE+-]+)"', svg)
    if m:
        parts = [float(x) for x in m.group(1).split()]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return parts[2], parts[3]
    w = re.search(r'\bwidth\s*=\s*"([\d.]+)', svg)
    h = re.search(r'\bheight\s*=\s*"([\d.]+)', svg)
    if w and h and float(w.group(1)) > 0 and float(h.group(1)) > 0:
        return float(w.group(1)), float(h.group(1))
    return None


def render_fitness(item: dict) -> list[str]:
    """Why this component's automatic full-bleed reuse would NOT be fit for a human
    audience, or []. This is DISTINCT from contract fidelity: fidelity proves the
    slide preserves the component's reference geometry (slot coverage/bounds), which
    says nothing about whether the rendered result is legible or whole. A component can
    pass fidelity and still be unfit — e.g. its outer artwork falls off the frame.

    Deterministic and advisory: it surfaces candidates for review, it does not by
    itself flip a registry flag (intentional edge-bleed layouts exist and must be
    confirmed by a human, not auto-rejected). The auto_reuse.eligible gate is where a
    confirmed-unfit component is actually blocked."""
    warns: list[str] = []
    vb = _visual_viewbox(item)
    if vb:
        crop = cover_crop_fraction(*vb)
        if crop > MAX_COVER_CROP:
            # Cover fills the SHORT canvas axis, so the artwork's LONG axis overflows:
            # a wide (landscape-er than 16:9) artwork loses its left+right, a tall one
            # loses its top+bottom. Report the axis that is actually cropped.
            wide = vb[0] / vb[1] > CANVAS_W / CANVAS_H
            dim = "width" if wide else "height"
            edges = "left and right edges" if wide else "top and bottom edges"
            warns.append(
                f"full-bleed cover materialization crops {crop:.0%} of the artwork's "
                f"{dim} off the {CANVAS_W}x{CANVAS_H} frame (artwork aspect "
                f"{vb[0]/vb[1]:.2f}:1); its outer content past the {edges} is not on the "
                f"slide. Contract fidelity cannot see this — review before automatic reuse.")
    return warns


def measure_rendered_slots(html_path: Path) -> dict | None:
    """Render the deck in Chromium (measure_deck_slots.js) and return, keyed by the
    UNIQUE per-occurrence instance id:
        { instance_id: {"component": id, "bg": {...}, "slots": {slot_id: rec}} }
    Two uses of the same component therefore live under distinct keys and can never
    overwrite each other's measurements. Returns None when node/playwright is
    unavailable or the measurement fails, so a non-release caller can degrade to
    static checks; the release gate treats None as a hard failure (--require-render)."""
    if not _node_available():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "slots.json"
        try:
            proc = subprocess.run(
                ["node", str(_MEASURE_JS), "--html", str(html_path), "--out", str(out)],
                capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"WARN: slot render measurement failed to run: {exc}", file=sys.stderr)
            return None
        if proc.returncode != 0 or not out.exists():
            print(f"WARN: slot render measurement error: {proc.stderr.strip()[:300]}",
                  file=sys.stderr)
            return None
        data = json.loads(out.read_text(encoding="utf-8"))
    result: dict = {}
    for inst in data.get("instances", []):
        result[inst.get("instance")] = {
            "component": inst.get("component"),
            "bg": inst.get("bg") or {},
            "slots": {s.get("slot"): s for s in inst.get("slots", [])},
        }
    return result

SLOT_ID_RE = re.compile(r'data-slot-id="([^"]+)"')
BG_RE = re.compile(r'class="[^"]*\bbg\b[^"]*"', re.IGNORECASE)
_SCAFFOLD_OPEN_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*\bslide-scaffold\b[^"]*"[^>]*>', re.IGNORECASE)
_DIV_TOKEN_RE = re.compile(r'<div\b|</div>', re.IGNORECASE)
_INSTANCE_ATTR_RE = re.compile(r'data-component-instance="([^"]+)"')
_BASE_ATTR_RE = re.compile(r'data-base-component="([^"]+)"')


def _instance_occurrences(html: str, item_id: str) -> list[tuple[str | None, str]]:
    """One (instance_id, subtree_html) per `.slide-scaffold` occurrence whose
    data-base-component == item_id, in document order. instance_id is the UNIQUE
    per-occurrence data-component-instance; None marks a legacy scaffold with no
    such attribute. Reusing the same component twice yields TWO occurrences with
    distinct ids, so fidelity validates each placement on its own — slot evidence,
    artifacts, and measurements are never pooled across occurrences."""
    out: list[tuple[str | None, str]] = []
    for m in _SCAFFOLD_OPEN_RE.finditer(html):
        tag = m.group(0)
        base = _BASE_ATTR_RE.search(tag)
        if not base or base.group(1) != item_id:
            continue
        depth, sub = 0, None
        for tok in _DIV_TOKEN_RE.finditer(html, m.start()):
            if tok.group(0).lower() == "</div>":
                depth -= 1
                if depth == 0:
                    sub = html[m.start():tok.end()]
                    break
            else:
                depth += 1
        if sub is None:
            continue
        inst = _INSTANCE_ATTR_RE.search(tag)
        out.append((inst.group(1) if inst else None, sub))
    return out

# The only slot-coverage bar there is: `reuse` is the sole action that builds from
# a published component. (The retired `adapt-local` action had a laxer bar; it is
# gone, so there is nothing left to choose between.)
REUSE_MIN = 0.70

# Slot-contract geometry: a bound slot box must stay within its declared bounds
# (normalized) with this tolerance, and two distinct slots must not overlap by
# more than SLOT_OVERLAP_MAX of the smaller box.
CANVAS_W, CANVAS_H = 1920, 1080
SLOT_GEOM_TOL = 0.03
SLOT_OVERLAP_MAX = 0.20

COMPONENT_SLOT_RE = re.compile(
    r'<[^>]*\bdata-component-slot="([^"]+)"[^>]*\bstyle="([^"]*)"', re.IGNORECASE)
_PX_RE = {k: re.compile(rf'\b{k}\s*:\s*(-?\d+(?:\.\d+)?)px', re.IGNORECASE)
          for k in ("left", "top", "width", "height")}
_ARTIFACT_REF_RE = re.compile(
    r'background-image\s*:\s*url\(["\']?([^"\')]+)["\']?\)'
    r'|<(?:img|object)\b[^>]*\b(?:src|data)="([^"]+)"', re.IGNORECASE)
_DATA_URI_RE = re.compile(r'data:image/[^;]+;base64,[A-Za-z0-9+/]{200,}')
_INLINE_SVG_RE = re.compile(r'<svg\b', re.IGNORECASE)


def _slot_ids(html: str) -> set[str]:
    return set(SLOT_ID_RE.findall(html))


def _entry_map(registry: dict) -> dict[str, dict]:
    return {it.get("id"): it for it in registry.get("items", []) if it.get("id")}


def declared_text_slots(entry: dict) -> dict[str, tuple[float, float, float, float]] | None:
    """{slot_id: (x, y, w, h) normalized} when the component is a text-FREE base
    whose editable copy lives in positioned slots (text_contract
    semantic_text_in_visual False + editable). Else None — such a component is
    NOT satisfied by a bare data-base-component marker."""
    contract = entry.get("text_contract") or {}
    if contract.get("semantic_text_in_visual") is not False or contract.get("editable") is False:
        return None
    ts = (entry.get("paths") or {}).get("text_slots")
    if not ts or not Path(ts).exists():
        return None
    data = load_json(ts)
    slots = data.get("slots", []) if isinstance(data, dict) else data
    out: dict[str, tuple[float, float, float, float]] = {}
    for s in slots:
        if isinstance(s, dict) and s.get("id") and isinstance(s.get("bounds"), dict):
            b = s["bounds"]
            try:
                out[str(s["id"])] = (float(b["x"]), float(b["y"]),
                                     float(b["width"]), float(b["height"]))
            except (KeyError, TypeError, ValueError):
                continue
    return out or None


def deck_slot_boxes(html: str) -> list[tuple[str, float, float, float, float]]:
    """(slot_id, x, y, w, h) normalized for each data-component-slot in the deck."""
    boxes = []
    for m in COMPONENT_SLOT_RE.finditer(html):
        sid, style = m.group(1), m.group(2)
        vals = {}
        for k, rx in _PX_RE.items():
            mm = rx.search(style)
            if mm:
                vals[k] = float(mm.group(1))
        if len(vals) == 4:
            boxes.append((sid, vals["left"] / CANVAS_W, vals["top"] / CANVAS_H,
                          vals["width"] / CANVAS_W, vals["height"] / CANVAS_H))
    return boxes


def _overlap_frac(a: tuple, b: tuple) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    small = min(aw * ah, bw * bh) or 1e-9
    return (ix * iy) / small


def _nonblank_artifact(html: str, html_path: Path | None) -> bool:
    """A rendered-non-blank base: inline SVG, a base64 data-URI image, or a
    referenced artifact file that exists and is non-trivial."""
    if _DATA_URI_RE.search(html) or _INLINE_SVG_RE.search(html):
        return True
    for a, b in _ARTIFACT_REF_RE.findall(html):
        ref = a or b
        if not ref or ref.startswith("http"):
            continue
        if ref.startswith("data:"):
            return True
        if html_path is not None:
            p = (html_path.parent / ref).resolve()
            if p.exists() and p.stat().st_size > 256:
                return True
    return False


def _rendered_text_overlaps(mslots: dict, declared: dict) -> list[str]:
    """Slot-id pairs whose ACTUAL rendered text ink boxes overlap by more than the
    component's own source-declared overlap. `_overlap_frac` is fraction-of-smaller
    (scale-free), so comparing px text rects against normalized declared bounds is
    valid. Only slots that actually rendered text are considered."""
    ids = [sid for sid, m in mslots.items()
           if m.get("textW", 0) > 0 and m.get("textH", 0) > 0]
    bad: list[str] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            si, sj = ids[i], ids[j]
            a, b = mslots[si], mslots[sj]
            frac = _overlap_frac((a["textX"], a["textY"], a["textW"], a["textH"]),
                                 (b["textX"], b["textY"], b["textW"], b["textH"]))
            designed = (_overlap_frac(declared[si], declared[sj])
                        if si in declared and sj in declared else 0.0)
            if frac - designed > SLOT_OVERLAP_MAX:
                bad.append(f"{si}~{sj}")
    return sorted(bad)


def _check_slot_contract(deck_html, html_path, declared, measure=None):
    """Return (pass, coverage, reason) for a text-slot-contract component instance.
    When `measure` (this instance's {"bg":..., "slots":{slot_id: rec}} browser
    record) is given, also fail on: text that overflows/clips or spills its wrapper;
    a bound slot that did not render; rendered text of two slots overlapping beyond
    the source-declared overlap; or base artwork that did not load/render. The fit
    policy is hard: overflow → fail (fall back to custom-local), never a silent
    shrink."""
    boxes = deck_slot_boxes(deck_html)
    bound = [b for b in boxes if b[0] in declared]
    bound_ids = {b[0] for b in bound}
    coverage = len(bound_ids) / len(declared) if declared else 0.0
    threshold = REUSE_MIN
    reasons: list[str] = []
    if not bound_ids:
        reasons.append("text-slot component but deck has no data-component-slot bindings "
                       "(a data-base-component marker alone is not fidelity)")
    elif coverage < threshold:
        reasons.append(f"slot coverage {coverage:.0%} < {threshold:.0%} "
                       f"({len(bound_ids)}/{len(declared)} declared slots bound)")
    outside = []
    for sid, x, y, w, h in bound:
        dx, dy, dw, dh = declared[sid]
        if not (x >= dx - SLOT_GEOM_TOL and y >= dy - SLOT_GEOM_TOL
                and x + w <= dx + dw + SLOT_GEOM_TOL and y + h <= dy + dh + SLOT_GEOM_TOL):
            outside.append(sid)
    if outside:
        reasons.append(f"slot text outside its declared bounds: {sorted(set(outside))[:5]}")
    overlaps = []
    for i in range(len(bound)):
        for j in range(i + 1, len(bound)):
            si, sj = bound[i][0], bound[j][0]
            if si == sj:
                continue
            authored = _overlap_frac(bound[i][1:], bound[j][1:])
            # Tolerate the component's OWN declared overlap (this artwork's text
            # boxes legitimately overlap); flag only NEW overlap the deck added.
            designed = (_overlap_frac(declared[si], declared[sj])
                        if si in declared and sj in declared else 0.0)
            if authored - designed > SLOT_OVERLAP_MAX:
                overlaps.append(f"{si}~{sj}")
    if overlaps:
        reasons.append(f"overlapping slot text: {overlaps[:3]}")
    if not _nonblank_artifact(deck_html, html_path):
        reasons.append("missing/blank base artifact (no rendered component visual)")
    if measure:
        mslots = measure.get("slots") or {}
        clipped = sorted({sid for sid, m in mslots.items()
                          if sid in declared and (m.get("overflowX") or m.get("overflowY")
                                                  or m.get("textOutsideWrapper"))})
        if clipped:
            reasons.append("rendered text overflows/clips its slot box (too long to fit; "
                           f"fall back to custom-local, do not shrink): {clipped[:5]}")
        invisible = sorted({sid for sid, m in mslots.items()
                            if sid in declared and m.get("textW", 0) > 0
                            and not m.get("textVisible", True)})
        if invisible:
            reasons.append(f"slot text present but not visible: {invisible[:5]}")
        zero = sorted({sid for sid, m in mslots.items()
                       if sid in declared and not m.get("rendered")})
        if zero:
            reasons.append(f"slot did not render (zero size): {zero[:5]}")
        overlaps = _rendered_text_overlaps(mslots, declared)
        if overlaps:
            reasons.append(f"rendered text of different slots overlaps: {overlaps[:3]}")
        bg = measure.get("bg") or {}
        if not (bg.get("present") and bg.get("loaded")
                and bg.get("w", 0) > 0 and bg.get("h", 0) > 0):
            reasons.append("base component artwork did not load/render for this instance")
    return (not reasons), round(coverage, 3), ("; ".join(reasons) if reasons else "slot fidelity ok")


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


def _validate_occurrence(scope_html: str, item_id: str, preview_map: dict,
                         entry_map: dict, html_path: Path | None, inst_measure: dict | None) -> dict:
    """Validate ONE component-instance subtree; return result fields (pass_/reason
    plus optional coverage/threshold/slot_contract). All evidence is drawn from
    `scope_html` (this instance only) and `inst_measure` (this instance's browser
    record), so nothing is pooled across occurrences."""
    # A component with a RECORDED full-slide QA failure (registry auto_reuse
    # eligible:false) can never produce a safe slide — fail closed for ANY reuse,
    # including an explicit user selection, so it cannot slip past the render gate.
    auto = (entry_map.get(item_id) or {}).get("auto_reuse") or {}
    if auto.get("eligible") is False:
        return {"pass_": False,
                "reason": f"component is marked not eligible for full-slide reuse "
                          f"(review-only): {auto.get('reason')}"}

    deck_slot_ids = _slot_ids(scope_html)
    deck_has_bg = bool(BG_RE.search(scope_html))

    preview_path = preview_map.get(item_id)
    if not preview_path:
        return {"pass_": False, "reason": f"item {item_id!r} missing paths.preview "
                "(pass the full registry, not compact)"}
    p = Path(preview_path)
    if not p.exists():
        return {"pass_": False, "reason": f"preview.html not found: {preview_path}"}

    comp_ids = _slot_ids(p.read_text(encoding="utf-8", errors="replace"))
    if not comp_ids:
        # No wired `.slot` in preview.html. A text-slot-contract base needs REAL
        # data-component-slot bindings + geometry (a bare marker is not fidelity);
        # a true raster with baked text falls back to the marker.
        declared = declared_text_slots(entry_map.get(item_id) or {})
        if declared:
            ok, cov, reason = _check_slot_contract(scope_html, html_path, declared,
                                                   inst_measure)
            return {"pass_": ok, "coverage": cov, "slot_contract": True, "reason": reason}
        used = f'data-base-component="{item_id}"' in scope_html
        return {"pass_": used, "coverage": None,
                "reason": "component has no slots; matched on data-base-component" if used
                else "no slots and no data-base-component marker in deck"}

    present = comp_ids & deck_slot_ids
    coverage = len(present) / len(comp_ids)
    threshold = REUSE_MIN
    reasons: list[str] = []
    if coverage < threshold:
        reasons.append(f"slot-id coverage {coverage:.0%} < {threshold:.0%} "
                       f"({len(present)}/{len(comp_ids)} ids present)")
    if not deck_has_bg:
        reasons.append("no .bg layer found in deck")
    if inst_measure:
        # Render-aware checks for a full-slide TEMPLATE occurrence: its `data-slot-id`
        # boxes carry real copy too, so the same fit policy applies — overflow fails,
        # nothing is silently shrunk. (Templates went unmeasured until the measurer
        # learned this slot dialect; cover/closing overflow needed a manual probe.)
        mslots = inst_measure.get("slots") or {}
        clipped = sorted({sid for sid, m in mslots.items()
                          if m.get("overflowX") or m.get("overflowY") or m.get("textOutsideWrapper")})
        if clipped:
            reasons.append(f"rendered text overflows/clips its slot box: {clipped[:5]}")
        invisible = sorted({sid for sid, m in mslots.items()
                            if m.get("textW", 0) > 0 and not m.get("textVisible", True)})
        if invisible:
            reasons.append(f"slot text present but not visible: {invisible[:5]}")
        zero = sorted({sid for sid, m in mslots.items()
                       if m.get("textW", 0) > 0 and not m.get("rendered")})
        if zero:
            reasons.append(f"slot did not render (zero size): {zero[:5]}")
        bg = inst_measure.get("bg") or {}
        if not (bg.get("present") and bg.get("loaded") and bg.get("w", 0) > 0 and bg.get("h", 0) > 0):
            reasons.append("base component artwork did not load/render for this instance")
    return {"pass_": not reasons, "coverage": round(coverage, 3), "threshold": threshold,
            "reason": "; ".join(reasons) if reasons else "fidelity ok"}


def check_fidelity(deck_html: str, report: dict, registry: dict,
                   html_path: Path | None = None,
                   measurements: dict | None = None,
                   require_instance_ids: bool = False) -> list[dict]:
    """One result per component OCCURRENCE (unique data-component-instance). Two
    uses of the same component are validated independently. `require_instance_ids`
    (release mode) fails a matched scaffold that lacks a unique instance id;
    legacy decks without instance ids are only tolerated when it is False."""
    preview_map = _preview_map(registry)
    entry_map = _entry_map(registry)
    results: list[dict] = []

    for rid, dec in _decisions(report):
        action = dec.get("action", "")
        item_id = dec.get("item_id")
        # Only `reuse` slides use a published component (adapt-local is retired;
        # needs_component/custom-local build no component). Explicit user reuse is
        # still `reuse`, so it is fidelity-checked here too.
        if action != "reuse" or not item_id:
            continue

        # An explicit selection whose artwork carries fixed text this deck does not
        # match (scorer-recorded `immutable_text_conflict`) can never produce a
        # correct slide — the copy is in the artwork and no slot can edit it. Fail
        # closed before any geometry check; the reviewer was warned at selection.
        conflict = dec.get("immutable_text_conflict")
        if conflict:
            results.append({"request_id": rid, "item_id": item_id, "action": action,
                            "instance": None, "pass_": False,
                            "reason": "component artwork carries fixed text that does not "
                                      f"match this deck: {conflict.get('reason')}"})
            continue

        # A selection report is a claim about artwork AS IT WAS WHEN SCORED. This gate
        # runs immediately before build/export, so it is the last chance to notice that
        # the artwork changed in between — a re-extraction can turn an audited-`clean`
        # component into one that ships a baked lockup while the report still says it
        # was safe. Re-check the recorded fingerprint against the bytes on disk NOW.
        # `immutable_text_drift` (not the full gate) is deliberate: it fires only on a
        # verdict that no longer matches its artifact, so an item that was never
        # audited is left to the selection-time rules rather than failed here.
        drift = build_registry.immutable_text_drift(entry_map.get(item_id) or {})
        if drift:
            results.append({"request_id": rid, "item_id": item_id, "action": action,
                            "instance": None, "pass_": False,
                            "reason": f"the immutable-text audit for this component is stale "
                                      f"— {drift}. It was selected against artwork that is no "
                                      f"longer on disk. Re-run audit_immutable_text.py and "
                                      f"re-score before building."})
            continue

        # One entry per marked occurrence; legacy decks with no marker at all fall
        # back to a single whole-deck occurrence (id=None), rejected under release.
        occurrences = _instance_occurrences(deck_html, item_id) or [(None, deck_html)]
        for inst_id, scope_html in occurrences:
            entry = {"request_id": rid, "item_id": item_id, "action": action,
                     "instance": inst_id}
            if require_instance_ids and inst_id is None:
                entry.update(pass_=False, reason="missing data-component-instance (fresh "
                             "release decks must scaffold each occurrence with a unique id)")
                results.append(entry)
                continue
            inst_measure = measurements.get(inst_id) if measurements is not None else None
            entry.update(_validate_occurrence(scope_html, item_id, preview_map,
                                              entry_map, html_path, inst_measure))
            results.append(entry)

    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate deck slides use their selected components.")
    ap.add_argument("--html", required=True)
    ap.add_argument("--selection-report", required=True)
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--warn", action="store_true",
                    help="Report failures but always exit 0 (rollout mode).")
    ap.add_argument("--render", action="store_true",
                    help="Also measure slot text in real Chromium (fail on overflow / "
                         "non-render). Requires node + playwright; falls back to static "
                         "checks with a warning when unavailable.")
    ap.add_argument("--require-render", action="store_true",
                    help="RELEASE GATE: measurement MUST run (fail closed if node/playwright "
                         "is unavailable or errors) and every reused component occurrence MUST "
                         "carry a unique data-component-instance. Implies --render.")
    args = ap.parse_args(argv)

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        print(f"ERROR: HTML not found: {html_path}", file=sys.stderr)
        return 1

    deck_html = html_path.read_text(encoding="utf-8", errors="replace")
    report = load_json(args.selection_report)
    registry = load_json(args.registry)

    want_render = args.render or args.require_render
    measurements = None
    if want_render:
        measurements = measure_rendered_slots(html_path)
        if measurements is None:
            if args.require_render:
                # Fail closed: a release gate cannot pass on absent render evidence.
                print("ERROR: --require-render but slot measurement is unavailable/failed; "
                      "refusing to pass on static checks alone.", file=sys.stderr)
                return 1
            print("WARN: --render requested but slot measurement unavailable; "
                  "static checks only", file=sys.stderr)

    results = check_fidelity(deck_html, report, registry, html_path, measurements,
                             require_instance_ids=args.require_render)
    failed = [r for r in results if not r["pass_"]]
    valid = not failed

    # Render-fitness ADVISORY, distinct from the contract pass/fail above: a reused
    # component can preserve its slot geometry (fidelity OK) yet render unfit for an
    # audience — e.g. a wide band whose outer artwork falls off the 16:9 frame. Surface
    # it per reused item so a QA reviewer sees the risk; it does not flip the contract
    # verdict (that stays geometry-only) — a confirmed-unfit component is blocked via
    # its registry auto_reuse.eligible flag, not here.
    entry_by_id = {i.get("id"): i for i in registry.get("items", [])}
    fitness: list[dict] = []
    for item_id in dict.fromkeys(r["item_id"] for r in results):
        for w in render_fitness(entry_by_id.get(item_id) or {}):
            fitness.append({"item_id": item_id, "warning": w})

    out = {
        "valid": valid,
        "checked_at": now_iso(),
        "html_path": str(html_path),
        "warn_only": args.warn,
        "require_render": bool(args.require_render),
        "render_measured": bool(want_render and measurements is not None),
        "results": results,
        "render_fitness_advisories": fitness,
    }
    write_json(html_path.parent / "qa" / "component-fidelity-report.json", out)

    status = "PASS" if valid else ("WARN" if args.warn else "FAIL")
    print(f"component_fidelity: {status} ({len(results)} reuse occurrence(s) checked)")
    for r in results:
        mark = "OK" if r["pass_"] else "FAIL"
        cov = f" cov={r['coverage']:.0%}" if r.get("coverage") is not None else ""
        inst = f" [{r['instance']}]" if r.get("instance") else ""
        print(f"  [{mark}] {r['request_id']} {r['item_id']}{inst} ({r['action']}){cov}: {r['reason']}")
    for adv in fitness:
        print(f"  [FITNESS] {adv['item_id']}: {adv['warning']}", file=sys.stderr)

    if valid or args.warn:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
