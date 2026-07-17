#!/usr/bin/env python3
"""Score published visual items for a normalized slide need.

v3.2 hybrid retrieval: alongside the canonical intent/tags overlap, the scorer
optionally reads the published-only `component-retrieval-index.jsonl`
projection to broaden lexical matching (keywords, component_type, layout_role,
visual_summary, retrieval_notes, use_cases, ...). Broadened matches earn
reduced, capped credit that stays below the semantic floor, so generic
metadata overlap alone can never make an item selectable. Anti-use-case hits,
set-of-N count mismatches, and zero editable text slots apply bounded score
penalties with explicit reasons (selection score != buildability). No
embeddings, vector DB, network calls, or new dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, Iterable

from _common import (load_json, now_iso, write_json, SHAPE_TYPE_MAP, shape_eligible,
                     derive_content_shape)


SCORER_VERSION = "3.2.0"

WEIGHTS = {
    "semantic_intent": 35,
    "content_structure": 20,
    "density": 10,
    "brand": 10,
    "export_compatibility": 15,
    "accessibility": 10,
}

TEMPLATE_WEIGHTS = {
    **WEIGHTS,
    "content_structure": 25,
    "density": 5,
}

SYNONYMS: dict[str, set[str]] = {
    "cover": {"opening", "title-page", "hero", "intro", "bia", "trang-bia", "first-slide", "start", "beginning", "first-page", "welcome", "landing", "splash-screen"},
    "closing": {"thank-you", "end", "farewell", "goodbye", "final", "last", "last-page", "conclusion", "ket-thuc", "cam-on", "wrap-up", "end-slide", "cuoi", "tam-biet"},
    "timeline": {"roadmap", "milestones", "schedule", "phases", "lich-trinh", "ke-hoach", "lo-trinh", "tien-do", "chronology"},
    "comparison": {"versus", "side-by-side", "contrast", "pros-cons", "trade-offs", "evaluation", "advantages", "disadvantages", "so-sanh"},
    "statistics": {"metrics", "numbers", "data", "kpi", "figures", "results", "thong-ke", "so-lieu", "chi-so", "ket-qua"},
    "checklist": {"action-items", "todo", "requirements", "next-steps", "danh-sach"},
    "agenda": {"outline", "program", "table-of-contents", "schedule", "chuong-trinh"},
    "faq": {"questions", "answers", "q-and-a", "help", "hoi-dap", "cau-hoi"},
    "divider": {"section-break", "separator", "transition", "chapter-header", "phan-cach"},
    "chart": {"graph", "visualization", "rating", "analytics", "bieu-do", "scores"},
    "quote": {"testimonial", "highlight", "pullquote", "trich-dan", "loi-noi"},
    "callout": {"scan-me", "attention", "important", "note", "qr-code"},
    "instructions": {"steps", "how-to", "procedure", "process", "guide", "huong-dan"},
    "layout": {"two-column", "split-layout", "content", "information"},
    "overview": {"summary", "recap", "key-points", "tong-quan"},
}

# --- Hybrid retrieval (v3.2) -------------------------------------------------
# Broadened lexical matches earn SECONDARY_WEIGHT credit per matched request
# term, capped at SECONDARY_CAP of total semantic coverage. The cap is chosen
# so pure-secondary evidence maxes at 0.25 * 35 = 8.75 points — below the 10.5
# semantic floor — meaning an item can never become selectable on broadened
# metadata overlap alone; it needs at least one canonical intent/tags match.
SECONDARY_WEIGHT = 0.5
SECONDARY_CAP = 0.25

# Bounded post-criteria adjustments (same pattern as the +5 set bonus, always
# surfaced in `reasons`). Floors (65/75) and the semantic floor are unchanged.
ANTI_USE_CASE_PENALTY = 15
COUNT_FIT_PENALTY = 10
NO_TEXT_SLOT_PENALTY = 10

# Automatic-reuse confidence bar (product decision 2026-07-13.20). A component is
# auto-reused ONLY when it clears BOTH gates — a high TOTAL score AND a strong
# SEMANTIC sub-score. The ~45-pt baseline (density+brand+export+accessibility)
# inflates the total, so the total alone cannot tell a genuine match from a
# keyword-lucky one; the semantic sub-score (primary intent overlap) is the real
# discriminator. Calibrated from the live registry (scratchpad/calibrate.py): true
# strong matches land >=78 total / >=24.5 semantic with 3-4 primary intent hits,
# while mediocre "matches" fall below on semantic and now become needs_component.
# Materially stricter than the retired adapt band (65) and old reuse band (75).
AUTO_REUSE_MIN = 78
SEMANTIC_CONFIDENCE_FRAC = 0.70  # * WEIGHTS["semantic_intent"] (=24.5)

# Type-intent bias. When a request explicitly asks for a reusable COMPONENT, a
# full-slide `template` is demoted by this modest amount so a genuinely relevant
# component is not out-ranked by a whole-slide layout in all-types scoring.
# It only fires on explicit component intent; template-intent and neutral
# requests are untouched, and component-only scoring never sees a template, so
# that path is unchanged.
TEMPLATE_DEMOTION = 15

# Markers that let a request declare which item *kind* it wants. Matched as
# substrings against `prefer_type` / free-text `query` / intent / tags.
# Template intent takes precedence: an explicit "template"/"full slide" ask
# means a whole-slide layout even if component words also appear.
TEMPLATE_INTENT_MARKERS = (
    "template", "full slide", "full-slide", "cover slide", "cover-slide",
    "slide template", "slide-template", "whole slide", "whole-slide",
)
COMPONENT_INTENT_MARKERS = (
    "reusable component", "reusable-component", "component-set", "component",
    "card set", "card-set", "icon reference", "icon-reference",
    "metric strip", "metric-strip", "badge set", "badge-set",
)

DEFAULT_RETRIEVAL_INDEX = (
    Path(__file__).resolve().parents[1] / "registries/component-retrieval-index.jsonl"
)

# Same token shape as build_component_retrieval_index.py (input lowercased).
TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?")
SET_SIZE_RE = re.compile(r"\bset-of-(\d+)\b")

# Filler words that dominate prose metadata (use_cases / anti_use_cases
# sentences) but carry no retrieval signal.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "do", "for",
    "from", "has", "in", "is", "it", "its", "not", "of", "on", "or", "so",
    "the", "this", "to", "use", "when", "with", "without",
}

# Positive-evidence fields of a retrieval-index record. anti_use_cases is
# deliberately excluded here (and matched separately as a penalty): the index's
# own search_text/retrieval_terms concatenate anti text, so matching those
# verbatim would credit an item for the very content it warns against.
ENRICH_POSITIVE_FIELDS = (
    "name", "component_type", "layout_role", "visual_summary",
    "retrieval_notes", "keywords", "use_cases", "intent", "tags",
    "content_structure",
)

_SYNONYM_MAP: dict[str, str] | None = None


def _build_synonym_map() -> dict[str, str]:
    global _SYNONYM_MAP
    if _SYNONYM_MAP is None:
        _SYNONYM_MAP = {}
        for canonical, syns in SYNONYMS.items():
            _SYNONYM_MAP[canonical] = canonical
            for s in syns:
                _SYNONYM_MAP[s] = canonical
    return _SYNONYM_MAP


def _canonicalize(terms: Iterable[str]) -> set[str]:
    smap = _build_synonym_map()
    result: set[str] = set()
    for t in terms:
        low = str(t).lower()
        canon = smap.get(low)
        if canon:
            result.add(canon)
        else:
            result.add(low)
    return result


def _norm_token(term: str) -> str:
    """Normalize one token for broadened matching: synonym map first, then a
    naive singular fold so `metric`/`metrics` or `circle`/`circles` compare
    equal. Primary intent/tags matching stays exact and is NOT folded."""
    smap = _build_synonym_map()
    low = str(term).lower()
    if low in smap:
        return smap[low]
    if low.endswith("s") and not low.endswith("ss") and len(low) > 3:
        base = low[:-1]
        return smap.get(base, base)
    return smap.get(low + "s", low)


def _concept_groups(request: dict) -> list[set[str]] | None:
    """Required semantic concept groups for a request, canonicalized. Each group is
    a set of OR-alternative concepts; the groups are AND requirements. Returns None
    when the request declares no `concepts`, so the flat `intent + tags` denominator
    applies unchanged — full backward compatibility for legacy requests."""
    raw = request.get("concepts")
    if not raw:
        return None
    groups = [g for g in (_canonicalize(group) for group in raw if group) if g]
    return groups or None


def _concept_coverage(groups: list[set[str]], item_terms: set[str],
                      record: dict | None) -> tuple[float, dict, set[str]]:
    """Semantic coverage over concept GROUPS (OR within a group, AND across groups):
    a group is satisfied when the item's canonical terms intersect any of its
    alternatives. Coverage = matched_groups / total_groups, so descriptor terms and
    synonyms never inflate the required denominator, while AND-across keeps a
    multi-concept slide (e.g. role AND card-layout) from matching on one concept
    alone. An unmatched group can still earn the SAME capped, below-floor secondary
    credit as the flat path (a broadened lexical hit can never buy a reuse on its
    own). Returns (semantic_fraction, report, secondary_terms)."""
    matched, missing = [], []
    for group in groups:
        hit = group & item_terms
        (matched if hit else missing).append((group, hit))
    semantic = len(matched) / len(groups) if groups else 1.0
    secondary: set[str] = set()
    if record and missing:
        sec_groups = 0
        for group, _ in missing:
            hits = {t for t in group if _norm_token(t) in record["positive"]}
            if hits:
                sec_groups += 1
                secondary |= hits
        if sec_groups:
            semantic = min(1.0, semantic + min(
                SECONDARY_WEIGHT * (sec_groups / len(groups)), SECONDARY_CAP))
    report = {
        "required": [sorted(group) for group in groups],
        "matched": [{"group": sorted(group), "via": sorted(hit)} for group, hit in matched],
        "missing": [sorted(group) for group, _ in missing],
    }
    return semantic, report, secondary


def _field_tokens(record: dict, fields: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for field in fields:
        value = record.get(field)
        values = value if isinstance(value, list) else [value]
        for entry in values:
            if entry:
                tokens.update(TOKEN_RE.findall(str(entry).lower()))
    return {_norm_token(t) for t in tokens if len(t) >= 2 and t not in STOPWORDS}


def build_enrichment(records: Iterable[dict]) -> dict[str, dict]:
    """Project retrieval-index records into per-item token sets for scoring.

    Only `published` records are accepted — the index is built published-only,
    but this guard keeps Draft/staging items out even from a stale or foreign
    file.
    """
    enrichment: dict[str, dict] = {}
    for record in records:
        item_id = record.get("id")
        if not item_id or record.get("status") != "published":
            continue
        enrichment[item_id] = {
            "positive": _field_tokens(record, ENRICH_POSITIVE_FIELDS),
            "anti": _field_tokens(record, ("anti_use_cases",)),
            "slot_count": record.get("slot_count"),
            # How many distinct content items this component can hold. None ==
            # unknown (no readable slot contract) -> the capacity gate stays silent.
            "content_blocks": record.get("content_blocks"),
        }
    return enrichment


def load_retrieval_index(path: str | Path) -> dict[str, dict]:
    """Load component-retrieval-index.jsonl; missing file → no enrichment."""
    index_path = Path(path)
    if not index_path.exists():
        return {}
    records = []
    try:
        with index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except (OSError, ValueError):
        return {}
    return build_enrichment(records)


def _set_sizes(item: dict) -> set[int]:
    """Declared set sizes (`set-of-N` / `repeatable-set-of-N`) from compact
    metadata. Empty when the item declares none (unknown ≠ mismatch)."""
    sizes: set[int] = set()
    for term in list(item.get("tags") or []) + list(item.get("content_structure") or []):
        match = SET_SIZE_RE.search(str(term).lower())
        if match:
            sizes.add(int(match.group(1)))
    return sizes


def request_type_intent(request: dict) -> str | None:
    """Which item kind the request explicitly wants: 'component', 'template',
    or None. Reads an explicit `prefer_type` first, then scans the free-text
    `query` plus intent/tags. Template intent wins ties so an explicit
    full-slide ask is never overridden by an incidental component word."""
    explicit = str(request.get("prefer_type") or "").strip().lower()
    if explicit in ("component", "template"):
        return explicit
    haystack = " ".join([
        str(request.get("query") or ""),
        " ".join(str(t) for t in (request.get("intent") or [])),
        " ".join(str(t) for t in (request.get("tags") or [])),
    ]).lower()
    if any(marker in haystack for marker in TEMPLATE_INTENT_MARKERS):
        return "template"
    if any(marker in haystack for marker in COMPONENT_INTENT_MARKERS):
        return "component"
    return None


def weights_for(item_type: str | None) -> dict[str, int]:
    return TEMPLATE_WEIGHTS if item_type == "template" else WEIGHTS


def overlap_score(left: Iterable[str], right: Iterable[str]) -> float:
    a = _canonicalize(left)
    b = _canonicalize(right)
    if not a:
        return 1.0
    return len(a & b) / len(a)


def _build_inverted_index(items: list[dict], enrichment: dict[str, dict] | None = None) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = {}
    smap = _build_synonym_map()
    for i, item in enumerate(items):
        terms = set()
        for t in item.get("intent", []) + item.get("tags", []):
            low = str(t).lower()
            terms.add(low)
            canon = smap.get(low)
            if canon:
                terms.add(canon)
        record = (enrichment or {}).get(item.get("id"))
        if record:
            terms |= record["positive"]
        for term in terms:
            idx.setdefault(term, []).append(i)
    return idx


def _prefilter(request: dict, items: list[dict], index: dict[str, list[int]]) -> list[dict]:
    req_terms = _canonicalize(request.get("intent", []) + request.get("tags", []))
    hit_indices: set[int] = set()
    for term in req_terms:
        for key in {term, _norm_token(term)}:
            if key in index:
                hit_indices.update(index[key])
    if not hit_indices or len(hit_indices) < 5:
        return items
    return [items[i] for i in sorted(hit_indices)]


_STABLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PROMPT_ID_RE = re.compile(r"\(([a-z0-9][a-z0-9._-]*)\)")


def _auto_reuse_ok(cand: dict) -> bool:
    """False only when the item records a FAILED full-slide materialization/render
    QA (`auto_reuse.eligible: false` in the registry). Absent metadata means
    eligible, so nothing needs backfilling to stay selectable."""
    return ((cand.get("retrieval") or {}).get("auto_reuse") or {}).get("eligible", True)


def _build_scope_ok(cand: dict) -> bool:
    """Whether the item is a GENERIC, auto-buildable template/component that a short
    unrelated brief can safely scaffold and fill — the buildability half of reuse
    (semantic relevance is the other half). Only an item REVIEWED as
    `build_scope.mode == "generic"` qualifies. CONSERVATIVE by design: an absent or
    "source-specific" verdict is NOT auto-buildable, so a high semantic score can
    never auto-reuse a specific published slide (dates, named people, source-context
    slots) merely because concepts match. Such items stay published and manually
    selectable — an explicit user pick still routes through the scaffold/fidelity
    gate, which fails closed if the request cannot fill the slots."""
    return ((cand.get("retrieval") or {}).get("build_scope") or {}).get("mode") == "generic"


def planned_item_count(request: dict) -> int | None:
    """How many distinct content items this slide's approved plan holds, or None
    when the request carries no plan.

    `content_plan` is the structured expansion of the user's brief — the actual
    planned items — so its LENGTH is the count, and it wins here: a bare number can
    never be more authoritative than the listed content it describes. `item_count`
    supplies the count only for a request that states one without listing the copy.

    The two may both appear only in agreement: `validate_batch_request` rejects a
    mismatch before scoring, so they can never silently disagree in the real flow.
    """
    plan = request.get("content_plan")
    if isinstance(plan, list) and plan:
        return len(plan)
    count = request.get("item_count")
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        return count
    return None


def _capacity_ok(cand: dict, planned_items: int | None) -> bool:
    """Whether this component can actually HOLD the slide's planned content.

    Capacity is `content_blocks` — how many distinct content items the component's
    own slot contract can carry (see `_common.content_blocks`). Semantic relevance
    is not evidence of fit: a one-statement CTA slide matches "next steps" perfectly
    and then forces a 4-action plan to be cut down to one vague line, which is the
    failure this gate exists to stop.

    A FLOOR, not a preference for big layouts: a 1-item plan still fits a 1-block
    component, so sparse-by-design covers/CTAs/closings keep working. Either side
    unknown -> True, so requests with no plan and components with no readable slot
    contract behave exactly as before (same conservative no-op rule as
    `shape_eligible`).
    """
    if planned_items is None:
        return True
    blocks = (cand.get("retrieval") or {}).get("content_blocks")
    if not isinstance(blocks, int):
        return True
    return blocks >= planned_items


def _immutable_contexts(immutable: dict) -> list[set[str]]:
    """The declared immutable contexts, canonicalized: a list of groups, each a set of
    terms that must ALL be present for that group to count."""
    return [_canonicalize(group) for group in (immutable.get("contexts") or [])
            if group]


def _immutable_context_matched(req_terms: set[str], contexts: list[set[str]]) -> set[str] | None:
    """The first COMPLETE context group the request satisfies, or None.

    All-of within a group, any-of across groups. A group is the whole context the
    fixed copy names — a programme AND its year, say — so a request that shares only
    part of it (a bare `2025`) is not about that subject and must fail closed. The
    earlier gate accepted any single overlapping term and let exactly that through."""
    for group in contexts:
        if group and group <= req_terms:
            return group
    return None


def _immutable_text_ok(cand: dict) -> bool:
    """Whether the item's immutable-text audit permits AUTOMATIC reuse here.

    - no audit recorded -> True (un-audited items keep their existing behaviour; the
                           compact projection the scorer reads stamps every published
                           item, so this only covers synthetic/unpublished ones);
    - `clean`           -> True (the empty-slot render showed no source-specific words);
    - `immutable`       -> only when the request satisfies a COMPLETE declared context
                           (see `_immutable_context_matched`);
    - `unresolved`      -> False, fail closed until a human resolves the audit.

    Purely metadata-driven: the contexts come from the item, the match comes from the
    request, and nothing here knows any component id or phrase."""
    imm = (cand.get("retrieval") or {}).get("immutable_text")
    if not imm:
        return True
    audit = imm.get("audit")
    if audit == "clean":
        return True
    if audit == "unresolved":
        return False
    return bool(imm.get("matched"))


def resolve_component_id(raw: str | None) -> str | None:
    """Resolve an explicit user component choice to a stable id. Accepts a bare id
    (`sun.component.foo`) or the catalog 'Copy prompt' text, which embeds the id in
    parentheses: `Use the published component "Name" (sun.component.foo) ...`.
    Deterministic: a bare id wins outright, else the LAST parenthesised id-shaped
    token; None when nothing id-shaped is present."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if _STABLE_ID_RE.match(s):
        return s
    hits = _PROMPT_ID_RE.findall(s)
    return hits[-1] if hits else None


def _suggested_search(request: dict) -> list[str]:
    """Plain search terms for a needs_component slide, from its own intent/tags."""
    terms: list[str] = []
    shape = request.get("content_shape")
    if shape:
        terms.append(str(shape).lower())
    for t in (request.get("intent") or []) + (request.get("tags") or []):
        t = str(t).strip().lower()
        if t and t not in terms:
            terms.append(t)
    return terms[:6]


_NEXT_ACTION = ("Open the SUN.STUDIO catalog, search/preview published components, "
                "copy a component's ID (or its prompt), and set `component_id` on this "
                "slide to reuse it; or set `unresolved_policy: \"custom-local\"` to "
                "approve a custom slide as a last resort.")


def _needs_component_decision(request: dict, selectable: list[dict], any_published: bool,
                              req_shape: str | None, blocker: Callable[[dict], str | None]) -> dict:
    """Unresolved: no candidate could be automatically reused and the user has not
    chosen. Build nothing — hand back a plain reason, suggested search terms, and the
    exact next action. The ranked safe candidates stay in the report's `candidates`.

    The reason names the ACTUAL blocker for the best candidate, taken from the same
    function the reuse gate uses, so the report can never explain a decision by a rule
    that did not cause it."""
    top = selectable[0] if selectable else None
    if not any_published:
        reason = "No published component is eligible for this slide."
    elif not selectable:
        reason = (f"No published component matches the required content_shape {req_shape!r}."
                  if req_shape else "No published component is a semantic fit for this slide.")
    else:
        reason = (f"Best candidate {top['item_id']} {blocker(top).rstrip('. ')}. "
                  f"Not confident enough to auto-reuse.")
    return {
        "action": "needs_component",
        "item_id": None,
        "score": top["score"] if top else 0,
        "reason": reason,
        "extraction_recommended": True,
        "suggested_search": _suggested_search(request),
        "shortlist": _safe_shortlist(request, selectable, blocker),
        "next_action": _NEXT_ACTION,
    }


def _safe_shortlist(request: dict, selectable: list[dict],
                    blocker: Callable[[dict], str | None]) -> list[dict]:
    """A small ranked shortlist of SAFE near-matches for a non-technical reviewer:
    published + shape-compatible (already true of `selectable`) AND auto-reuse-
    eligible, immutable-clean, and slot-ready — everything the reuse gate needs
    EXCEPT the high-confidence concept/score bar. Each entry says what concept is
    missing and stays advisory: this never selects a component (the decision is
    already needs_component), it just tells the user which published components are
    worth previewing. Empty when nothing is a plausible, safe near-match."""
    request_needs_text = bool(request.get("content_structure"))
    shortlist: list[dict] = []
    for cand in selectable:
        retrieval = cand.get("retrieval") or {}
        if not (_auto_reuse_ok(cand) and _immutable_text_ok(cand)):
            continue
        if request_needs_text and retrieval.get("slot_count") == 0:
            continue
        concepts = retrieval.get("concepts") or {}
        # Only plausible near-matches: at least one primary concept matched (or, for
        # a flat request, a non-zero semantic sub-score).
        if not (concepts.get("matched") or cand["criteria"]["semantic_intent"] > 0):
            continue
        shortlist.append({
            "item_id": cand["item_id"],
            "score": cand["score"],
            "missing_concepts": concepts.get("missing", []),
            "why": (blocker(cand) or "").rstrip(". "),
        })
        if len(shortlist) >= 3:
            break
    return shortlist


def _explicit_decision(explicit_id: str, candidates: list[dict], req_shape: str | None,
                       request_needs_text: bool, planned_items: int | None = None) -> dict:
    """Validate an explicit user component choice. It may bypass the auto-confidence
    bar but must still be published, shape/type-compatible, and slot-ready (render
    fidelity is enforced later at build). On any failure the slide stays
    needs_component with a plain reason — never a silent substitution."""
    cand = next((c for c in candidates if c["item_id"] == explicit_id), None)

    def _fail(reason: str) -> dict:
        return {
            "action": "needs_component", "item_id": None,
            "score": (cand or {}).get("score", 0), "reason": reason,
            "selected_by": "user", "extraction_recommended": True,
            "suggested_search": [], "next_action": _NEXT_ACTION,
        }

    if cand is None:
        return _fail(f"Explicit component_id {explicit_id!r} is not in the published library.")
    if not cand["eligible"]:
        return _fail(f"Explicit component_id {explicit_id!r} is not published.")
    if req_shape and not cand.get("shape_eligible", True):
        return _fail(f"Explicit component_id {explicit_id!r} does not support content_shape "
                     f"{req_shape!r}.")
    if request_needs_text and (cand.get("retrieval") or {}).get("slot_count") == 0:
        return _fail(f"Explicit component_id {explicit_id!r} has no editable text slots for "
                     f"this slide's copy.")
    reason = (f"Explicit user selection of published component {explicit_id!r} "
              f"(bypasses the auto-confidence bar; still validated + fidelity-gated).")
    if not _auto_reuse_ok(cand):
        # Selectable for review, but never silently: carry the recorded QA failure so
        # the reviewer sees it, and the build/render gate fails this closed.
        qa = ((cand.get("retrieval") or {}).get("auto_reuse") or {}).get("reason")
        reason += (f" WARNING: this component is marked review-only after a failed "
                   f"full-slide QA ({qa}); the render fidelity gate will reject the build.")
    capacity_conflict = None
    if not _capacity_ok(cand, planned_items):
        # The user may deliberately want this component, but choosing it is NOT
        # evidence that the content fits. Say so plainly and record the conflict, so
        # the reviewer sees it and the downstream scaffold/fidelity/export gates
        # still decide the build on the rendered truth.
        blocks = (cand.get("retrieval") or {}).get("content_blocks")
        capacity_conflict = {"planned_items": planned_items, "content_blocks": blocks}
        reason += (f" WARNING: capacity mismatch — this component holds {blocks} content "
                   f"block(s) but this slide plans {planned_items} item(s). Reusing it "
                   f"means the approved content does not fit as planned; the scaffold and "
                   f"render-fidelity gates still apply and will fail a slide whose copy "
                   f"cannot be placed.")
    decision = {
        "action": "reuse", "item_id": explicit_id, "score": cand["score"],
        "reason": reason,
        "selected_by": "user", "extraction_recommended": False,
    }
    if capacity_conflict:
        decision["capacity_conflict"] = capacity_conflict
    if not _immutable_text_ok(cand):
        # The user may deliberately want this component, but its artwork would ship
        # visible copy about another subject (or its audit is unresolved, so nobody
        # knows). Warn plainly AND record the conflict on the decision so the
        # render/fidelity gate fails the build closed.
        imm = (cand.get("retrieval") or {}).get("immutable_text") or {}
        what = ("its immutable-text audit is unresolved"
                if imm.get("audit") == "unresolved"
                else "its artwork carries fixed text this deck does not match")
        decision["reason"] += (
            f" WARNING: {what} ({imm.get('reason')}); the render fidelity gate will "
            f"reject the build.")
        decision["immutable_text_conflict"] = {"contexts": imm.get("contexts") or [],
                                               "reason": imm.get("reason")}
    return decision


def score_request(
    request: dict,
    registry_items: list[dict],
    weights: dict[str, int],
    prefer_set: str | None,
    top_n: int | None = 5,
    enrichment: dict[str, dict] | None = None,
) -> tuple[dict, list[dict]]:
    """Returns (decision, candidates). `top_n=None` returns the FULL scored pool
    (used by the batch path for deck allocation); an int returns the compact
    report slice via `report_candidates`."""
    candidates = []
    # Required semantic concepts. When the request declares `concepts`, coverage is
    # measured over those OR-groups (AND across); `intent`/`tags` then feed retrieval
    # only. Absent `concepts`, `req_terms` IS the flat intent+tags denominator (legacy).
    concept_groups = _concept_groups(request)
    flat_terms = _canonicalize(request.get("intent", []) + request.get("tags", []))
    req_terms = (flat_terms | set().union(*concept_groups)) if concept_groups else flat_terms
    item_count = request.get("item_count")
    planned_items = planned_item_count(request)
    request_needs_text = bool(request.get("content_structure"))
    type_intent = request_type_intent(request)
    req_shape = request.get("content_shape")

    for item in registry_items:
        reasons: list[str] = []
        retrieval: dict = {}
        eligible = item.get("status") == "published"
        if not eligible:
            reasons.append(f"Rejected status: {item.get('status')}")

        # Copy the artwork bakes in and no slot can edit is genuinely part of what
        # this item says, so its terms match like any other vocabulary — that is what
        # lets a deck ABOUT that context reuse the item at full confidence. The gate
        # below is what stops every OTHER deck from doing so. Only an `immutable`
        # verdict carries contexts; `clean`/`unresolved` add no vocabulary.
        immutable = item.get("immutable_text") or {}
        immutable_contexts = (_immutable_contexts(immutable)
                              if immutable.get("audit") == "immutable" else [])
        immutable_terms = set().union(*immutable_contexts) if immutable_contexts else set()
        item_terms = _canonicalize(item.get("intent", []) + item.get("tags", [])) | immutable_terms
        record = (enrichment or {}).get(item.get("id"))
        primary_matched = req_terms & item_terms
        if concept_groups is not None:
            # Required concepts drive the denominator; the flat overlap above is kept
            # only as retrieval evidence (primary_matches).
            semantic, concept_report, secondary_matched = _concept_coverage(
                concept_groups, item_terms, record)
            retrieval["concepts"] = concept_report
            if secondary_matched:
                reasons.append(
                    "Broadened lexical match (retrieval index): "
                    + ", ".join(sorted(secondary_matched))
                )
        else:
            semantic = 1.0 if not req_terms else len(primary_matched) / len(req_terms)
            secondary_matched = set()
            if record and req_terms:
                remaining = req_terms - primary_matched
                secondary_matched = {t for t in remaining if _norm_token(t) in record["positive"]}
                if secondary_matched:
                    secondary_cov = len(secondary_matched) / len(req_terms)
                    semantic = min(1.0, semantic + min(SECONDARY_WEIGHT * secondary_cov, SECONDARY_CAP))
                    reasons.append(
                        "Broadened lexical match (retrieval index): "
                        + ", ".join(sorted(secondary_matched))
                    )
        if primary_matched:
            retrieval["primary_matches"] = sorted(primary_matched)
        if secondary_matched:
            retrieval["secondary_matches"] = sorted(secondary_matched)

        structure = overlap_score(
            request.get("content_structure", []),
            item.get("content_structure", []),
        )
        density = 1.0 if item.get("density") in {"any", request.get("density", "any")} else 0.4
        brand = 1.0 if item.get("brand") in {None, request.get("brand")} else 0.0
        export = 1.0  # per-item export support is no longer tracked; always passes
        limitations = " ".join(item.get("limitations", [])).lower()
        accessibility = 0.5 if "contrast" in limitations or "overflow" in limitations else 1.0
        criteria = {
            "semantic_intent": round(semantic * weights["semantic_intent"], 2),
            "content_structure": round(structure * weights["content_structure"], 2),
            "density": round(density * weights["density"], 2),
            "brand": round(brand * weights["brand"], 2),
            "export_compatibility": round(export * weights["export_compatibility"], 2),
            "accessibility": round(accessibility * weights["accessibility"], 2),
        }
        score = round(sum(criteria.values()), 2) if eligible else 0.0

        if eligible and score > 0:
            # Buildability/usability guards — bounded penalties, always
            # explained. Selection score != buildability: metadata overlap can
            # make an item selectable while count/slot/domain fit still makes
            # it a bad build, so mismatches must cost score visibly.
            # An anti mention of a concept the item also declares in its own
            # intent/tags is a usage caveat ("edit the metrics text"), not a
            # domain exclusion — only undeclared concepts count as hits.
            anti_hits = (
                {t for t in req_terms - primary_matched if _norm_token(t) in record["anti"]}
                if record else set()
            )
            if anti_hits:
                score = max(0.0, score - ANTI_USE_CASE_PENALTY)
                retrieval["anti_hits"] = sorted(anti_hits)
                reasons.append(
                    f"Anti-use-case match ({', '.join(sorted(anti_hits))}): "
                    f"-{ANTI_USE_CASE_PENALTY}"
                )
            sizes = _set_sizes(item)
            if sizes:
                retrieval["set_sizes"] = sorted(sizes)
            if isinstance(item_count, int) and sizes and item_count not in sizes:
                score = max(0.0, score - COUNT_FIT_PENALTY)
                reasons.append(
                    f"Count fit: request needs {item_count} items, component is "
                    f"set-of-{'/'.join(str(s) for s in sorted(sizes))}: -{COUNT_FIT_PENALTY}"
                )
            if record and record.get("slot_count") is not None:
                retrieval["slot_count"] = record["slot_count"]
            # Content capacity: how many distinct items this component can hold.
            # Recorded for EVERY candidate (not only mismatches) so a reviewer can
            # see the fit — including the over-capacity case this slice does not
            # gate (tiny content in a large layout).
            if record and isinstance(record.get("content_blocks"), int):
                retrieval["content_blocks"] = record["content_blocks"]
                if planned_items is not None and record["content_blocks"] < planned_items:
                    reasons.append(
                        f"Capacity: this slide plans {planned_items} content item(s) but "
                        f"the component holds {record['content_blocks']} — reusing it "
                        f"would force the approved content to be cut down to fit")
            if record and record.get("slot_count") == 0 and request_needs_text:
                score = max(0.0, score - NO_TEXT_SLOT_PENALTY)
                reasons.append(
                    f"Buildability: component has no editable text slots: "
                    f"-{NO_TEXT_SLOT_PENALTY}"
                )
            score = round(score, 2)

        if prefer_set and eligible and score > 0:
            # id convention is sun.<set>.<slide>, so segment [1] is always the
            # set regardless of how many dots follow. The +5 is applied here,
            # BEFORE the decision branch below, so it can lift an item over the
            # AUTO_REUSE_MIN total. It can never buy a reuse on its own: the
            # semantic sub-score is untouched, so a set-mate still has to clear
            # SEMANTIC_CONFIDENCE_FRAC. Surfaced in `reasons` either way.
            item_set = item["id"].split(".")[1] if item["id"].count(".") >= 2 else ""
            if item_set == prefer_set:
                score = min(100, score + 5)
                reasons.append("Set preference bonus: +5")

        # Type-intent bias: when the request explicitly wants a component, demote
        # full-slide templates so a relevant component is not out-ranked by a
        # whole-slide layout. One-directional and bounded; template-intent and
        # neutral requests never demote anything.
        if (type_intent == "component" and eligible and score > 0
                and item.get("type") == "template"):
            score = max(0.0, round(score - TEMPLATE_DEMOTION, 2))
            retrieval["type_bias"] = "template-demoted"
            reasons.append(
                f"Component intent: full-slide template demoted -{TEMPLATE_DEMOTION}")

        # Shape-aware eligibility (T1): a chosen component's intent/tags must be
        # compatible with the slide's content_shape. Incompatible items stay in
        # the report for auditability but are marked ineligible so they cannot be
        # selected — the scorer no longer ranks a generic badge/card into a
        # comparison/profile/timeline slide on generic keyword overlap alone.
        item_shape_ok = shape_eligible(
            req_shape, item.get("intent", []) + item.get("tags", []))
        # Deterministic shape derivation for auditability (no stored label): which
        # content_shape(s) this component fits, from its own intent/tags.
        derived_shapes = derive_content_shape(item.get("intent", []) + item.get("tags", []))
        if derived_shapes:
            retrieval["derived_shapes"] = derived_shapes
        if req_shape and not item_shape_ok:
            allowed = SHAPE_TYPE_MAP.get(req_shape)
            if allowed:
                reasons.append(
                    f"Shape mismatch: content_shape {req_shape!r} needs one of "
                    f"{sorted(allowed)}; item intent/tags carry none")
            else:
                reasons.append(
                    f"Shape mismatch: content_shape {req_shape!r} is outside the "
                    f"shape vocabulary {sorted(SHAPE_TYPE_MAP)}; no component can "
                    f"lock to it")
        # Automatic-reuse eligibility (registry `auto_reuse`): an item with a
        # recorded full-slide QA failure stays published + browseable and keeps its
        # score for review, but is barred from AUTOMATIC selection.
        auto = item.get("auto_reuse") or {}
        if auto.get("eligible") is False:
            retrieval["auto_reuse"] = {"eligible": False, "reason": auto.get("reason")}
            reasons.append(f"Not eligible for automatic reuse (review-only): {auto.get('reason')}")
        # Buildability scope (registry `build_scope`): is this a GENERIC template a
        # short unrelated brief can fill, or a SOURCE-SPECIFIC slide? Recorded so the
        # reuse gate and the reviewer both see it; absent == unreviewed == not
        # auto-buildable (conservative). Source-specific/unreviewed items stay
        # published + manually selectable.
        bscope = item.get("build_scope") or {}
        if bscope:
            retrieval["build_scope"] = {"mode": bscope.get("mode"), "reason": bscope.get("reason")}
            if bscope.get("mode") != "generic":
                reasons.append(f"Not a generic auto-buildable template "
                               f"[build_scope: {bscope.get('mode')}]: {bscope.get('reason')}")
        # Immutable-text audit (registry `immutable_text`): does the artwork name a
        # specific context in words no slot can edit? Record the verdict for THIS
        # request; `_immutable_text_ok` turns a miss (or an unresolved audit) into a
        # bar on automatic reuse, while the item stays published, scored and
        # browseable. An un-audited item records nothing and behaves as before.
        if immutable:
            audit = immutable.get("audit")
            rec = {"audit": audit, "reason": immutable.get("reason")}
            if audit == "immutable":
                group = _immutable_context_matched(req_terms, immutable_contexts)
                rec["contexts"] = [sorted(g) for g in immutable_contexts]
                rec["matched"] = group is not None
                if group is not None:
                    rec["matched_context"] = sorted(group)
                else:
                    reasons.append(
                        f"Fixed source text does not match this deck — it needs a COMPLETE "
                        f"context, one of {[sorted(g) for g in immutable_contexts]} "
                        f"(a partial match is not the same subject): {immutable.get('reason')}")
            elif audit == "unresolved":
                reasons.append(
                    f"Immutable-text audit unresolved — not safe for automatic reuse: "
                    f"{immutable.get('reason')}")
            retrieval["immutable_text"] = rec
        candidate = {
            "item_id": item["id"],
            "eligible": eligible,
            "score": score,
            "criteria": criteria,
            "reasons": reasons,
        }
        if req_shape is not None:
            candidate["shape_eligible"] = item_shape_ok
        if retrieval:
            candidate["retrieval"] = retrieval
        candidates.append(candidate)

    candidates.sort(key=lambda item: (item["eligible"], item["score"]), reverse=True)
    semantic_conf = weights["semantic_intent"] * SEMANTIC_CONFIDENCE_FRAC

    def _selectable(cand: dict) -> bool:
        # Published AND shape-compatible. shape_eligible defaults True when no
        # content_shape was declared, so shape-less requests behave as before.
        return cand["eligible"] and cand.get("shape_eligible", True)

    def _reuse_blocker(cand: dict) -> str | None:
        # Why this candidate cannot be AUTOMATICALLY reused, in the reader's words, or
        # None when it can. The AUTO-reuse bar: selectable, auto-reuse-eligible (no
        # recorded full-slide QA failure), context-compatible (no baked-in source copy
        # about another subject), high TOTAL score, strong SEMANTIC sub-score, and
        # slot-ready when the slide needs text. Deck-level de-duplication and render
        # fidelity are enforced later (deck assignment / build gate).
        #
        # Returning the reason rather than a bool is what keeps the decision and its
        # explanation honest: several of these blocks apply to candidates that clear
        # BOTH confidence bars, so a bool leaves the report guessing — and it used to
        # guess "score too low", sending the reader to raise a score that could never
        # unblock it.
        # Each string is a predicate, so it reads as "Best candidate <id> <blocker>."
        retrieval = cand.get("retrieval") or {}
        if not _selectable(cand):
            return "is not published, or is incompatible with the requested content_shape"
        if not _auto_reuse_ok(cand):
            return (f"is not eligible for automatic reuse (review-only): "
                    f"{(retrieval.get('auto_reuse') or {}).get('reason')}")
        if not _immutable_text_ok(cand):
            imm = retrieval.get("immutable_text") or {}
            return (f"carries fixed source text that does not fit this deck "
                    f"[audit: {imm.get('audit')}] — {imm.get('reason')}")
        if not _build_scope_ok(cand):
            bs = retrieval.get("build_scope") or {}
            mode = bs.get("mode") or "unreviewed"
            detail = bs.get("reason") or ("not reviewed as a generic auto-buildable template — "
                                          "source-specific/high-content items are manual selection only")
            return (f"is not a generic auto-buildable template [build_scope: {mode}] — {detail}. "
                    f"A semantic match is not proof this slide's slots can be filled from the brief")
        if not _capacity_ok(cand, planned_items):
            blocks = (cand.get("retrieval") or {}).get("content_blocks")
            return (f"holds {blocks} content block(s) but this slide plans "
                    f"{planned_items} item(s) — reusing it would force the approved "
                    f"content to be cut down to fit. A semantic match is not proof the "
                    f"content fits; pick a component that can hold the plan, or extract one")
        if cand["score"] < AUTO_REUSE_MIN or cand["criteria"]["semantic_intent"] < semantic_conf:
            return (f"scored {cand['score']} (semantic {cand['criteria']['semantic_intent']}) — "
                    f"below the high-confidence reuse bar (>= {AUTO_REUSE_MIN} total AND "
                    f">= {round(semantic_conf, 1)} semantic)")
        if request_needs_text and retrieval.get("slot_count") == 0:
            return "declares no editable text slots, and this slide needs text"
        return None

    def _reuse_ready(cand: dict) -> bool:
        return _reuse_blocker(cand) is None

    any_published = any(item["eligible"] for item in candidates)
    selectable = [c for c in candidates if _selectable(c)]
    reuse_ready = [c for c in selectable if _reuse_ready(c)]

    explicit_id = resolve_component_id(request.get("component_id"))
    unresolved_policy = request.get("unresolved_policy")

    if explicit_id:
        # Explicit user choice: validate, never silently substitute.
        decision = _explicit_decision(explicit_id, candidates, req_shape,
                                      request_needs_text, planned_items)
    elif reuse_ready:
        # Genuinely high-confidence automatic reuse (top-ranked ready candidate).
        top = reuse_ready[0]
        decision = {
            "action": "reuse", "item_id": top["item_id"], "score": top["score"],
            "reason": (f"High-confidence match: total {top['score']} >= {AUTO_REUSE_MIN} and "
                       f"semantic {top['criteria']['semantic_intent']} >= {round(semantic_conf, 1)}."),
            "extraction_recommended": bool(request.get("recommend_extraction", False)),
        }
    elif unresolved_policy == "custom-local":
        # The ONLY automatic-path to custom-local: the user pre-approved it.
        top = selectable[0] if selectable else None
        decision = {
            "action": "custom-local", "item_id": None,
            "score": top["score"] if top else 0,
            "reason": "User explicitly approved custom-local after reviewing the library.",
            "extraction_recommended": bool(request.get("recommend_extraction", False)),
            "selected_by": "user",
        }
    elif unresolved_policy == "blank":
        # Explicit user resolution: leave this slide deliberately blank after
        # library review. Like custom-local it is a user-only outcome (never
        # automatic), so an unresolved slide the user chose to skip resolves
        # instead of blocking delivery.
        top = selectable[0] if selectable else None
        decision = {
            "action": "blank", "item_id": None,
            "score": top["score"] if top else 0,
            "reason": "User explicitly chose to leave this slide blank after reviewing the library.",
            "extraction_recommended": bool(request.get("recommend_extraction", False)),
            "selected_by": "user",
        }
    else:
        # Unresolved: not confident enough, and the user has not chosen. Build
        # nothing; present the slide for library review.
        decision = _needs_component_decision(
            request, selectable, any_published, req_shape, _reuse_blocker)

    # top_n=None returns the FULL scored pool — the batch path needs it so deck
    # allocation can reach a valid candidate ranked below the report cut-off.
    if top_n is None:
        return decision, candidates
    return decision, report_candidates(candidates, decision, weights, top_n)


def report_candidates(candidates: list[dict], decision: dict, weights: dict[str, int],
                      top_n: int) -> list[dict]:
    """Compact, user-visible candidate slice: the ranked top-N PLUS the selected
    item when it ranks below the cut-off (deck de-dup can pick a lower-ranked
    candidate), plus the best safe candidate for an unresolved slide. `top_n` is a
    presentation limit only — it never constrains selection or deck allocation."""
    shown = candidates[:top_n]
    chosen_id = decision.get("item_id")
    if chosen_id and all(item["item_id"] != chosen_id for item in shown):
        chosen = next((c for c in candidates if c["item_id"] == chosen_id), None)
        if chosen:
            shown = shown + [chosen]
    elif decision.get("action") == "needs_component":
        # Surface the best SAFE (selectable + above the semantic floor) candidate for
        # the user to consider, even when floor-failing lures out-rank it by total.
        semantic_floor = weights["semantic_intent"] * 0.3
        relevant = next((c for c in candidates
                         if c.get("eligible") and c.get("shape_eligible", True)
                         and (c.get("criteria") or {}).get("semantic_intent", 0) >= semantic_floor),
                        None)
        if relevant and all(c["item_id"] != relevant["item_id"] for c in shown):
            shown = shown + [relevant]
    return shown


_BATCH_TOP_FIELDS = {"job_id", "brief", "note", "slides"}
_SLIDE_REQUEST_FIELDS = {
    "request_id", "intent", "tags", "content_structure", "content_shape", "item_count",
    "density", "brand", "required_exports", "query", "prefer_type", "recommend_extraction",
    "component_id", "allow_component_reuse", "unresolved_policy", "concepts", "content_plan",
}
_STRING_LIST_FIELDS = ("intent", "tags", "content_structure", "required_exports",
                       "content_plan")
# Optional string-or-null fields. `content_shape` is the one that mattered: a list
# passed validation and then raised `TypeError: unhashable type: 'list'` deep inside
# _common.shape_eligible(), after scoring had already started.
_NULLABLE_TEXT_FIELDS = ("content_shape", "density", "brand", "prefer_type")
_TEXT_FIELDS = ("query",)          # string, and not nullable (mirrors the schema)
_TOP_TEXT_FIELDS = ("brief", "note")


def validate_batch_request(batch, require_concepts: bool = False) -> list[str]:
    """Plain-language validation of <run>/analysis/visual-requests.json — the artifact
    a user edits to submit per-slide selections. Returns [] when valid.

    `require_concepts` (the normal new-run contract, `--require-concepts`) makes a
    non-empty `concepts` list mandatory on every slide, so a fresh run always scores
    on concept groups rather than the legacy flat intent+tags dilution. It is left
    OFF by default as the deliberate, documented compatibility path for an old or
    resumed run whose requests predate concepts.

    This is a hand-written mirror of schemas/visual-requests.schema.json, not a
    JSON Schema evaluation: `jsonschema` is not a declared dependency of this repo
    (there is no Python dependency manifest at all), no script imports it, and it is
    not in the project venv these scripts pin. The two are held in lockstep by
    test_gates.test_batch_request_validator_matches_schema_field_by_field, which
    reads the schema and proves every field it declares is enforced here — a
    property that only the schema knows about must never reach the scorer. Two
    checks are deliberately code-only: duplicate `request_id` (JSON Schema cannot
    express it cleanly) and blank-only strings (stricter than `minLength: 1`)."""
    if not isinstance(batch, dict):
        return ["visual-requests must be a JSON object with 'job_id' and 'slides'"]
    errors: list[str] = []
    unknown = set(batch) - _BATCH_TOP_FIELDS
    if unknown:
        errors.append(f"unknown top-level key(s) {sorted(unknown)}; allowed: "
                      f"{sorted(_BATCH_TOP_FIELDS)}")
    if not isinstance(batch.get("job_id"), str) or not batch["job_id"].strip():
        errors.append("job_id is required and must be a non-empty string")
    for key in _TOP_TEXT_FIELDS:
        if key in batch and not isinstance(batch[key], str):
            errors.append(f"{key} must be text, got {batch[key]!r}")
    slides = batch.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides is required and must be a non-empty array")
        return errors

    seen: set[str] = set()
    for i, s in enumerate(slides):
        p = f"slides[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{p} must be an object (one per slide)")
            continue
        unk = set(s) - _SLIDE_REQUEST_FIELDS
        if unk:
            errors.append(f"{p}: unknown field(s) {sorted(unk)} — check the spelling; "
                          f"allowed: {sorted(_SLIDE_REQUEST_FIELDS)}")
        rid = s.get("request_id")
        if not isinstance(rid, str) or not rid.strip():
            errors.append(f"{p}: request_id is required and must be a non-empty string")
        elif rid in seen:
            errors.append(f"{p}: duplicate request_id {rid!r}; each slide needs its own")
        else:
            seen.add(rid)
        cid = s.get("component_id")
        if cid is not None and not isinstance(cid, str):
            errors.append(f"{p}: component_id must be a string (a stable published id, or "
                          f"the catalog 'Copy prompt' text) or null")
        if "allow_component_reuse" in s and not isinstance(s["allow_component_reuse"], bool):
            errors.append(f"{p}: allow_component_reuse must be true or false, got "
                          f"{s['allow_component_reuse']!r}")
        pol = s.get("unresolved_policy")
        if pol is not None and pol not in ("custom-local", "blank"):
            errors.append(f"{p}: unresolved_policy must be \"custom-local\", \"blank\", or omitted, "
                          f"got {pol!r} — resolving an unresolved slide (custom slide or an "
                          f"explicit blank) needs explicit user approval")
        if "recommend_extraction" in s and not isinstance(s["recommend_extraction"], bool):
            errors.append(f"{p}: recommend_extraction must be true or false, got "
                          f"{s['recommend_extraction']!r}")
        for key in _STRING_LIST_FIELDS:
            val = s.get(key)
            if val is not None and (not isinstance(val, list)
                                    or any(not isinstance(x, str) for x in val)):
                errors.append(f"{p}: {key} must be a list of strings")
        for key in _NULLABLE_TEXT_FIELDS:
            if s.get(key) is not None and not isinstance(s[key], str):
                errors.append(f"{p}: {key} must be one piece of text (or omitted), got "
                              f"{s[key]!r}")
        for key in _TEXT_FIELDS:
            if key in s and not isinstance(s[key], str):
                errors.append(f"{p}: {key} must be text, got {s[key]!r}")
        n = s.get("item_count")
        if n is not None and (isinstance(n, bool) or not isinstance(n, int)):
            errors.append(f"{p}: item_count must be a whole number")
        # content_plan IS the plan, so its length is the count. A request that also
        # restates item_count must agree: a disagreement is an authoring mistake, and
        # resolving it by precedence would let a slide claim one item while listing
        # several — sizing the capacity gate to the wrong number and waving through a
        # component that cannot hold the real content. Fail here, before scoring.
        plan = s.get("content_plan")
        if (isinstance(plan, list) and plan
                and isinstance(n, int) and not isinstance(n, bool) and n > 0
                and n != len(plan)):
            errors.append(
                f"{p}: item_count is {n} but content_plan lists {len(plan)} item(s) — "
                f"they must agree. content_plan is the plan, so its length is the "
                f"count: drop item_count, or correct one of them.")
        concepts = s.get("concepts")
        if require_concepts and not (isinstance(concepts, list) and concepts):
            errors.append(f"{p}: concepts is required (--require-concepts): each slide must "
                          f"declare >= 1 semantic concept group derived from its purpose/shape, "
                          f"so scoring uses concept coverage, not the legacy flat intent+tags path")
        if concepts is not None:
            if not isinstance(concepts, list):
                errors.append(f"{p}: concepts must be a list of concept groups "
                              f"(each a non-empty list of concept terms)")
            else:
                for gi, group in enumerate(concepts):
                    if (not isinstance(group, list) or not group
                            or any(not isinstance(t, str) or not t.strip() for t in group)):
                        errors.append(f"{p}: concepts[{gi}] must be a non-empty list of "
                                      f"non-empty concept terms (OR alternatives for one "
                                      f"required concept)")
    return errors


def _reuse_ready_ids(candidates: list[dict], request_needs_text: bool,
                     semantic_conf: float) -> list[str]:
    """Ranked ids of the candidates that clear the auto-reuse bar (same gate as
    score_request._reuse_ready), for deck-level de-duplication."""
    out: list[str] = []
    for c in candidates:
        if (c.get("eligible") and c.get("shape_eligible", True) and _auto_reuse_ok(c)
                and _immutable_text_ok(c)
                and c.get("score", 0) >= AUTO_REUSE_MIN
                and (c.get("criteria") or {}).get("semantic_intent", 0) >= semantic_conf
                and not (request_needs_text and (c.get("retrieval") or {}).get("slot_count") == 0)):
            out.append(c["item_id"])
    return out


def assign_deck_components(slide_results: list[dict], requests_by_id: dict,
                          semantic_conf: float) -> list[dict]:
    """Deck-aware de-duplication. A published component reserved by one slide is
    UNAVAILABLE to later AUTOMATIC selection. Explicit user selections reserve
    first; automatic reuse is then resolved most-constrained-first (fewest ready
    candidates) so a generic slide cannot consume the only component a constrained
    slide needs. Duplicate-only automatic reuse becomes needs_component unless the
    slide carries `allow_component_reuse: true` (recorded + surfaced)."""
    used: dict[str, str] = {}  # item_id -> request_id that owns it

    def _reserve(dec: dict, rid: str, req: dict, iid: str) -> bool:
        if iid in used and used[iid] != rid:
            if req.get("allow_component_reuse"):
                dec["allow_component_reuse"] = True
                dec["reason"] = (dec.get("reason", "")
                                 + f" [reuse override: also assigned to slide {used[iid]!r}]")
                return True
            return False
        used.setdefault(iid, rid)
        return True

    def _dup_needs(s: dict, ready: list[str]) -> None:
        rid = s["request_id"]
        owners = sorted({used[i] for i in ready if i in used})
        req = requests_by_id.get(rid, {})
        s["decision"] = {
            "action": "needs_component", "item_id": None,
            "score": s["decision"].get("score", 0),
            "reason": (f"All high-confidence candidates are already assigned to earlier "
                       f"slide(s) {owners}; no unused component fits this deck."),
            "extraction_recommended": True,
            "suggested_search": _suggested_search(req),
            "next_action": ("Set `allow_component_reuse: true` on this slide to reuse an "
                            "assigned component, pick a different published component, or set "
                            "`unresolved_policy: \"custom-local\"`."),
        }

    # Pass 1: explicit user reuse selections reserve their exact component.
    for s in slide_results:
        dec = s["decision"]
        if dec.get("action") == "reuse" and dec.get("selected_by") == "user":
            rid = s["request_id"]
            if not _reserve(dec, rid, requests_by_id.get(rid, {}), dec["item_id"]):
                _dup_needs(s, [dec["item_id"]])

    # Pass 2: automatic reuse, most-constrained-first (stable within equal counts).
    auto = [s for s in slide_results
            if s["decision"].get("action") == "reuse"
            and s["decision"].get("selected_by") != "user"]
    auto.sort(key=lambda s: len(_reuse_ready_ids(
        s["candidates"], bool(requests_by_id.get(s["request_id"], {}).get("content_structure")),
        semantic_conf)))
    for s in auto:
        dec = s["decision"]
        rid = s["request_id"]
        req = requests_by_id.get(rid, {})
        ready = _reuse_ready_ids(s["candidates"], bool(req.get("content_structure")), semantic_conf)
        if req.get("allow_component_reuse"):
            _reserve(dec, rid, req, dec["item_id"])
            continue
        pick = next((iid for iid in ready if iid not in used), None)
        if pick is None:
            _dup_needs(s, ready)
        elif pick != dec.get("item_id"):
            cand = next(c for c in s["candidates"] if c["item_id"] == pick)
            dec["item_id"] = pick
            dec["score"] = cand["score"]
            dec["reason"] = (f"High-confidence match (deck de-dup: earlier top pick was taken; "
                             f"using next unused ready candidate {pick}): total {cand['score']}.")
            used[pick] = rid
        else:
            used[pick] = rid
    return slide_results


def scoring_items(registry_path: str) -> list[dict]:
    """The items to score, with the immutable-text audit gate applied to every one.

    Two shapes reach this CLI and BOTH must be gated, or the safety rule would depend
    on which file the caller happened to pass:

      * the canonical compact projection (the default, and what the workflow runs) is
        GENERATED, so it can be stale — an artifact can change after it was built,
        leaving a `clean` verdict on disk that no longer describes the artwork. It
        cannot be re-derived from itself, so freshness is verified against the full
        registry and the artifact bytes, and stale input is REFUSED rather than scored.
      * a full registry (`--registry .../visual-library.json`) carries `paths`, so it
        is projected through the very same `gate_immutable_text` IN MEMORY. Nothing is
        written: scoring never mutates the registry.

    Any other input (a synthetic or hand-built compact, as the tests use) has no
    artifacts to be stale against and is scored as declared — `_immutable_text_ok`
    still fails `unresolved` closed. The pre-build fidelity gate re-checks every
    SELECTED item against the registry on disk, so that path cannot ship stale
    evidence either.

    Raises SystemExit with a remediation message rather than scoring on stale data."""
    import build_registry

    registry = load_json(registry_path)
    items = registry.get("items", [])
    # The canonical GENERATED compact is verified fresh FIRST — before the
    # full-registry re-projection below — and returned from here. It is the default
    # the workflow scores and cannot be re-derived from itself, so a stale `clean`
    # verdict must be REFUSED, never scored. Checking freshness ahead of the
    # `any("paths")` branch closes the bypass where a compact that carried a stray
    # `paths` key would be re-projected in memory (masking staleness) instead.
    if Path(registry_path).resolve() == build_registry.COMPACT.resolve():
        stale = build_registry.generated_projection_staleness()
        if stale:
            raise SystemExit(
                "Refusing to score: the generated projections no longer match the "
                "registry and the artifacts on disk, so their immutable-text audit "
                "verdicts cannot be trusted.\n  "
                + "\n  ".join(stale)
                + f"\n\nRegenerate them, then re-run:\n  {build_registry.REFRESH_HINT}\n"
                "Any item whose artwork changed will then project as "
                "immutable_text.audit=unresolved and stop auto-reusing until "
                "slide-system/scripts/audit_immutable_text.py has re-audited it."
            )
        return items
    if any("paths" in item for item in items):
        return build_registry.project_compact(items)["items"]
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--request", default=None)
    source_group.add_argument("--batch-request", default=None, metavar="PATH")
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library-compact.json"),
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--item-type",
        default=None,
        help="Restrict scoring to registry items whose type equals this value (e.g. template).",
    )
    parser.add_argument(
        "--prefer-set",
        default=None,
        help="Template-set slug: the `<set>` segment of a sun.<set>.<slide> id. "
             "Same-set items get a +5 bonus.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top candidates to include in output (default: 5).",
    )
    parser.add_argument(
        "--require-concepts",
        action="store_true",
        help="Normal new-run contract: every slide must declare a non-empty `concepts` list "
             "(concept-group scoring). Omit only for a legacy/resumed run whose requests "
             "predate concepts (documented compatibility path).",
    )
    parser.add_argument(
        "--retrieval-index",
        default=str(DEFAULT_RETRIEVAL_INDEX),
        help="Published-only retrieval projection (JSONL) used to broaden "
             "lexical matching. Pass 'none' to disable enrichment.",
    )
    args = parser.parse_args(argv)

    weights = weights_for(args.item_type)

    registry_items = [
        item
        for item in scoring_items(args.registry)
        if args.item_type is None or item.get("type") == args.item_type
    ]

    if args.retrieval_index.strip().lower() == "none":
        enrichment: dict[str, dict] = {}
    else:
        enrichment = load_retrieval_index(args.retrieval_index)
        if not enrichment:
            print(f"note: retrieval index empty, missing, or unreadable ({args.retrieval_index}); "
                  f"scoring without lexical enrichment", file=sys.stderr)
    retrieval_index_used = str(args.retrieval_index) if enrichment else None

    index = _build_inverted_index(registry_items, enrichment)

    if args.request:
        request = load_json(args.request)
        filtered = _prefilter(request, registry_items, index)
        decision, candidates = score_request(request, filtered, weights, args.prefer_set, args.top_n, enrichment)
        report = {
            "request_id": request.get("request_id", "visual-request"),
            "generated_at": now_iso(),
            "generated_by": "score_visual_items.py",
            "scorer_version": SCORER_VERSION,
            "retrieval_index": retrieval_index_used,
            "decision": decision,
            "candidates": candidates,
        }
        write_json(args.output, report)
        print(f"{decision['action']}: {decision['item_id']} ({decision['score']})")

    else:
        batch = load_json(args.batch_request)
        # Validate the user-editable selection artifact BEFORE any scoring, so a typo
        # in component_id / allow_component_reuse / unresolved_policy fails loudly
        # instead of being silently ignored.
        batch_errors = validate_batch_request(batch, require_concepts=args.require_concepts)
        if batch_errors:
            print(f"ERROR: invalid visual-requests batch ({args.batch_request}); "
                  f"see slide-system/schemas/visual-requests.schema.json", file=sys.stderr)
            for e in batch_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        job_id = batch.get("job_id", "batch")
        requests_by_id = {r.get("request_id", ""): r for r in batch.get("slides", [])}
        slide_results = []
        for slide_req in batch.get("slides", []):
            filtered = _prefilter(slide_req, registry_items, index)
            # An explicit user component choice must be scored even if the prefilter
            # dropped it (the user asked for this exact item on purpose).
            explicit = resolve_component_id(slide_req.get("component_id"))
            if explicit and not any(it.get("id") == explicit for it in filtered):
                match = next((it for it in registry_items if it.get("id") == explicit), None)
                if match:
                    filtered = filtered + [match]
            # Score with the FULL pool (top_n=None): deck allocation must be able to
            # reach a valid unused candidate ranked below the report cut-off.
            decision, candidates = score_request(slide_req, filtered, weights, args.prefer_set,
                                                 None, enrichment)
            slide_results.append(
                {
                    "request_id": slide_req.get("request_id", ""),
                    "decision": decision,
                    "candidates": candidates,
                }
            )
        # Deck-aware de-duplication (no component auto-reused on two slides), over
        # the full pool.
        assign_deck_components(slide_results, requests_by_id,
                               weights["semantic_intent"] * SEMANTIC_CONFIDENCE_FRAC)
        # Only now compact each slide's candidates for the public report; the
        # selected item is always kept even if it ranks below top-N.
        for s in slide_results:
            s["candidates"] = report_candidates(s["candidates"], s["decision"], weights,
                                                args.top_n)
        for s in slide_results:
            d = s["decision"]
            print(f"{s['request_id']}: {d['action']}: {d.get('item_id')} ({d.get('score')})")
        report = {
            "job_id": job_id,
            "generated_at": now_iso(),
            "generated_by": "score_visual_items.py",
            "scorer_version": SCORER_VERSION,
            "retrieval_index": retrieval_index_used,
            "slides": slide_results,
        }
        write_json(args.output, report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
