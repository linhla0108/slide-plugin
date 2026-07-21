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

v3.3 adds visual-unit fit. For a request with `item_count` >= 2, a candidate's
repeated-unit count — derived by `component_units` from the component's own
published slot geometry — must equal the requested count, otherwise the
component would ship visibly blank cards/steps/columns. The candidate keeps its
rank and carries an explicit reason, but is not buildable, so selection falls
through to the next compatible published component or to text-only. Components
with no repeat structure declare no unit count and stay compatible. Score
weights, floors, and the retrieval index format are unchanged.

v3.4 adds layout-grammar fit. A component built around a display/quote panel
beside a much denser working surface hosts one statement, not N parallel items.
When a request explicitly wants N>=2 parallel items and such a component offers
no N-unit repeat group, it takes a bounded DISPLAY_SURFACE_PENALTY so a
better-matched published candidate can win. It stays eligible on purpose: when
nothing better is published the existing fallback is preserved, and the
decision carries a warning instead of silently shipping the mismatch.

v3.5 widens T1 shape-lock with the parallel-set allowance. A request that
explicitly declares N parallel peer items (`repeatable-set-of-N` in
content_structure AND `item_count` of N) may also accept a published component
declaring the same set size, even when that component names its grammar
(`role-cards`, `levels`) rather than the request's shape label. Both sides use
the same declared vocabulary, the shape must be one whose content is genuinely
a set of peers, and the count/visual-unit gates still apply — so a generic
checklist request can never absorb an arbitrary card set. `shape_lock_ok` owns
the whole rule and `validate_selection_report` imports it, so the two cannot
drift.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from _common import load_json, now_iso, resolve_repo_path, write_json
from component_units import unit_profile


SCORER_VERSION = "3.5.0"

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
    # Shapes that validate_selection_report.SHAPE_TYPE_MAP already accepts but
    # the scorer had no canonical vocabulary for. Without an entry here a
    # request carrying one of these shapes has no canonical token to match, so
    # it can never clear the semantic floor no matter what the library holds.
    # Tokens are taken from SHAPE_TYPE_MAP, which is sourced from real
    # published-item intent/tags. `test_gates` fails if the two drift apart.
    # A token may only resolve to one canonical, so tokens SHAPE_TYPE_MAP
    # shares with an existing entry (`evaluation` -> comparison, `questions`
    # -> faq, `steps` -> instructions) are deliberately not repeated here.
    # Kept narrow on purpose: `team` and `contributors` are common independent
    # tags, and folding them in here would make every team-tagged item score
    # identically to a true profile-set, destroying discrimination.
    "profile": {"profile-layout", "profile-circles", "roles", "personas", "vai-tro"},
    "tiers": {"levels", "ranking", "maturity-model", "capability-ladder", "ladder", "phan-cap"},
    "icons": {"icon-reference", "icon-library", "reference-sheet", "glyph-grid"},
    "review": {"check-in", "assessment", "quarterly-review", "progress-check"},
}
# `stats` is the shape name for the existing `statistics` canonical. `grid`
# is deliberately NOT folded in: a grid is a layout, not a statistics slide.
SYNONYMS["statistics"] |= {"stats"}

# T1 selection-lock: each content_shape maps to the intent/tag tokens a chosen
# item must carry, matched against the registry item's intent + tags. Synonyms
# are included so the map is lenient on phrasing but strict on category (a
# `timeline` shape can never lock to a `cover` item).
#
# Owned by the scorer, imported by validate_selection_report. It used to live
# in the validator only, so the scorer could happily select an item the gate
# then rejected — the two must not drift. Every token is drawn from real
# published-item intent/tags or the canonical vocabulary above; `test_gates`
# fails if a shape here has no canonical SYNONYMS entry.
SHAPE_TYPE_MAP: dict[str, set[str]] = {
    "cover": {"cover", "hero", "title", "opening", "intro"},
    "closing": {"closing", "thanks", "thank-you", "end", "end-slide", "farewell",
                "conclusion", "outro", "final-slide", "ket-thuc", "cam-on"},
    "stats": {"statistics", "data", "metrics", "kpi", "numbers", "figures", "grid"},
    "comparison": {"comparison", "versus", "do-dont", "what-how", "pros-cons", "contrast"},
    "timeline": {"timeline", "schedule", "roadmap", "process", "milestones", "phases", "instructions"},
    "checklist": {"checklist", "preparation", "steps", "action-items", "todo", "requirements"},
    "two-column": {"two-column", "split", "split-layout", "layout"},
    "profile": {"team", "profile", "profile-layout", "profile-circles", "contributors", "roles", "personas"},
    "tiers": {"levels", "tiers", "ranking", "maturity-model", "capability-ladder"},
    "icons": {"icons", "icon-reference", "icon-library", "reference-sheet", "glyph-grid"},
    "review": {"review", "check-in", "evaluation", "assessment", "questions", "quarterly-review", "progress-check"},
}

# Shapes whose content is inherently a set of parallel peer items, and which may
# therefore use the parallel-set allowance in `shape_lock_ok`. A repeated card /
# tier / level / step grammar is a legitimate host for these. Single-statement
# shapes (`cover`, `closing`) and container shapes (`two-column`, `layout`) are
# deliberately excluded: a repeated set does not make a cover a cover.
PARALLEL_SET_SHAPES = frozenset({
    "checklist", "tiers", "timeline", "comparison", "profile", "stats",
})

# --- Hybrid retrieval (v3.2) -------------------------------------------------
# Broadened lexical matches earn SECONDARY_WEIGHT credit per matched request
# term, capped at SECONDARY_CAP of total semantic coverage. The cap is chosen
# so pure-secondary evidence maxes at 0.25 * 35 = 8.75 points. It remains
# weaker ranking evidence than canonical intent/tag overlap, but can still
# select a published component that passes the physical buildability gates.
SECONDARY_WEIGHT = 0.5
SECONDARY_CAP = 0.25

# Bounded post-criteria adjustments (same pattern as the +5 set bonus, always
# surfaced in `reasons`). Numeric score ranks published, physically buildable
# candidates; it is not an approval band.
ANTI_USE_CASE_PENALTY = 15
COUNT_FIT_PENALTY = 10
NO_TEXT_SLOT_PENALTY = 10
# Layout-grammar mismatch: a display/quote-panel component asked to host N
# parallel items. Same tier as the other structural-mismatch adjustments, and
# deliberately a penalty rather than an eligibility rule — when no better
# published candidate exists, the fallback must stay intact.
DISPLAY_SURFACE_PENALTY = 15

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

# Visual-unit fit reads published slot geometry, which the compact registry does
# not carry. The full registry is consulted read-only for `paths.text_slots`;
# nothing here writes to the registry, the library, or the retrieval index.
DEFAULT_UNIT_REGISTRY = (
    Path(__file__).resolve().parents[1] / "registries/visual-library.json"
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

# Shape/geometry nouns that appear in item names to describe HOW something is
# drawn. They are structure, never subject matter, so `subject_tokens` ignores
# them — otherwise every component would look topic-bound.
STRUCTURAL_WORDS = {
    "set", "card", "cards", "badge", "circle", "circles", "grid", "strip",
    "diagram", "visual", "column", "columns", "row", "rows", "block", "blocks",
    "panel", "list", "table", "chart", "flow", "node", "item", "items",
    "overlap", "stack", "group", "box", "line", "bar", "ring", "hexagon",
    "sunriser", "studio", "sun", "slide", "page", "layout", "set-of",
    # Container words: a set literally named `deck`/`template` says nothing
    # about what the artwork is ABOUT.
    "deck", "template", "component", "master", "library", "asset",
    # Count and slot nouns describe capacity, not subject.
    "quad", "trio", "duo", "pair", "single", "slot", "slots", "cell", "tile",
}

# Placeholder markers. Artwork named after dummy copy carries no real subject
# matter, so it stays a generic reusable shell rather than a topic-bound one.
PLACEHOLDER_WORDS = {
    "lorem", "ipsum", "placeholder", "sample", "example", "untitled", "dummy",
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


def _semantic_terms(terms: Iterable[str]) -> set[str]:
    """Canonical terms for the semantic channel, with filler removed.

    `semantic` is a coverage ratio, so a prose token like "of" or "the" that no
    published item can ever carry only inflates the denominator and drags a
    genuine match below the reuse floor. `_field_tokens` has always applied
    this STOPWORDS/min-length rule to the index side; applying it to
    intent/tags too makes both sides of the comparison symmetric.

    Deliberately NOT used for `content_structure`, whose tokens are slot names
    rather than prose and must keep matching literally.
    """
    return _canonicalize(
        t for t in terms
        if str(t).lower() not in STOPWORDS and len(str(t).lower()) >= 2
    )


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


def normalize_intent(intent: Iterable[str]) -> tuple[set[str], list[str]]:
    """Split `intent` into scoring terms and dropped prose.

    `intent` is a canonical semantic retrieval field, not free text. `semantic`
    is a coverage ratio, so ANY word kept in it divides the score — and a word
    the corpus cannot answer ("real", "case") therefore penalises a genuine
    match for nothing. Dropping filler alone was not enough: the words that hurt
    most are ordinary nouns that simply are not vocabulary.

    Only terms that resolve to a canonical synonym are kept. Corpus membership
    is deliberately NOT an escape hatch: a junk word survives it whenever any
    one of the published items happens to carry that string ("what" did),
    which makes the guarantee probabilistic instead of exact. Literal item tags
    belong in `tags`, which is matched literally; prose belongs in `query`.

    Everything dropped is REPORTED, never silently discarded.

    Returns (scoring terms, dropped terms) — dropped is evidence, not garbage.
    """
    smap = _build_synonym_map()
    kept: set[str] = set()
    dropped: list[str] = []
    for raw in intent:
        low = str(raw).lower()
        if low in smap:
            kept.add(smap[low])
        else:
            dropped.append(low)
    return kept, sorted(set(dropped))


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


def wants_parallel_units(request: dict) -> bool:
    """True when a request asks for N>=2 parallel items, so unit fit applies."""
    count = request.get("item_count")
    return isinstance(count, int) and not isinstance(count, bool) and count >= 2


def load_unit_profiles(registry_path: str | Path,
                       item_ids: set[str] | None = None) -> dict[str, dict]:
    """Layout-grammar profile per published item, from its own slot geometry.

    Read-only: opens the full registry for `paths.text_slots`, then each
    candidate's published text-slot contract. Anything unreadable or
    contract-less is simply absent from the result — unknown is not a mismatch,
    exactly like the `set-of-N` rule.
    """
    try:
        registry = load_json(registry_path)
    except (OSError, ValueError):
        return {}
    profiles: dict[str, dict] = {}
    for item in registry.get("items", []):
        item_id = item.get("id")
        if not item_id or item.get("status") != "published":
            continue
        if item_ids is not None and item_id not in item_ids:
            continue
        slots_path = (item.get("paths") or {}).get("text_slots")
        if not slots_path:
            continue
        path = resolve_repo_path(slots_path)
        if not path.is_file():
            continue
        try:
            profiles[str(item_id)] = unit_profile(load_json(path))
        except (OSError, ValueError):
            continue
    return profiles


def load_unit_counts(registry_path: str | Path, item_ids: set[str] | None = None) -> dict[str, int]:
    """Primary repeat count per published item; absent when it has none."""
    return {
        item_id: profile["unit_count"]
        for item_id, profile in load_unit_profiles(registry_path, item_ids).items()
        if isinstance(profile.get("unit_count"), int)
    }


def declared_set_sizes(payload: dict) -> set[int]:
    """Declared set sizes (`set-of-N` / `repeatable-set-of-N`) from compact
    metadata. Empty when none is declared (unknown ≠ mismatch).

    Symmetric on purpose: requests and published items describe a repeated set
    with the same vocabulary in the same two fields, so one reader serves both
    sides of the parallel-set allowance below.
    """
    sizes: set[int] = set()
    for term in list(payload.get("tags") or []) + list(payload.get("content_structure") or []):
        match = SET_SIZE_RE.search(str(term).lower())
        if match:
            sizes.add(int(match.group(1)))
    return sizes


def parallel_set_request(request: dict) -> int | None:
    """N when the request is explicitly a set of N parallel peer items.

    Requires BOTH signals to agree: a declared `repeatable-set-of-N` and an
    `item_count` of N. One alone is not evidence — `item_count` is set on many
    ordinary requests, and a stray tag should not reclassify a slide.
    """
    count = request.get("item_count")
    if not (isinstance(count, int) and not isinstance(count, bool) and count >= 2):
        return None
    return count if count in declared_set_sizes(request) else None


def shape_lock_ok(shape: str | None, request: dict, item_terms: set[str],
                  item_set_sizes: set[int]) -> bool:
    """T1 selection-lock, owned here and imported by validate_selection_report.

    Base rule unchanged: the chosen item's intent/tags must carry one of the
    shape's tokens. The parallel-set allowance adds one narrow path — a request
    that explicitly declares N parallel peer items may also accept a component
    that declares the same set size, even when its own vocabulary names the
    grammar (`role-cards`, `levels`) rather than the shape label (`checklist`).

    Deliberately narrow. It needs declared repeated-item evidence on BOTH sides,
    an exact N match, and a shape whose content is genuinely a set of peers, so
    a generic checklist request can never absorb an arbitrary card set. Count
    and geometry stay enforced separately by the set-of-N and visual-unit gates.
    """
    allowed = SHAPE_TYPE_MAP.get(shape) if shape else None
    if not allowed:
        return True
    if allowed & item_terms:
        return True
    parallel = parallel_set_request(request)
    return bool(parallel and shape in PARALLEL_SET_SHAPES and parallel in item_set_sizes)


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
    req_terms = _semantic_terms(request.get("intent", []) + request.get("tags", []))
    hit_indices: set[int] = set()
    for term in req_terms:
        for key in {term, _norm_token(term)}:
            if key in index:
                hit_indices.update(index[key])
    if not hit_indices or len(hit_indices) < 5:
        return items
    return [items[i] for i in sorted(hit_indices)]


def subject_tokens(item_id: str, record: dict | None = None) -> set[str]:
    """Topic words baked into a published item's identity.

    Two metadata sources, both already in the registry/index:
      * the id — `sun.<set>.<name>`, where `<set>` names the source deck for a
        template and `<name>` names the artwork for a standalone component;
      * the index record's human `name`, which is where a themed capture
        announces its source ("01 - Cover: Goal Setting 2026").

    Whatever survives after canonical vocabulary, shape/geometry nouns,
    placeholder markers, and digits are removed is subject matter, not
    structure. An empty result means a generic, reusable shell.
    """
    parts = item_id.split(".")
    if len(parts) < 3:
        return set()
    segment = parts[-1] if parts[1] == "component" else parts[1]
    words = set(TOKEN_RE.findall(segment.replace("-", " ")))
    words |= set(TOKEN_RE.findall(str((record or {}).get("name") or "").lower()))
    smap = _build_synonym_map()
    return {
        token for token in words
        # Digits are years/versions; structural nouns describe the layout;
        # placeholder markers mean "this artwork carries no real content".
        if len(token) >= 3 and not token.isdigit()
        and token not in smap and token not in STOPWORDS
        and token not in STRUCTURAL_WORDS and token not in PLACEHOLDER_WORDS
    }


def topic_warning(item_id: str, request: dict, req_terms: set[str],
                  record: dict | None = None) -> str | None:
    """Return source-topic leakage warning, or None for a generic/on-topic item.

    Shape-lock proves an item has the right STRUCTURE. It cannot tell whether
    the artwork is about the right THING: a cover cut from a goal-setting deck
    fits a cover request perfectly and still ships the wrong subject, with the
    source deck's name baked into the pixels.

    This is advisory under the component-first policy: a published item that
    passes slot/count/shape gates remains selectable. The report must surface
    the source-topic leakage for review. A generic shell never warns, and an
    item does not warn for a topic the request explicitly asked for.
    """
    topic = subject_tokens(item_id, record)
    if not topic:
        return None
    haystack = {_norm_token(t) for t in req_terms}
    haystack |= {
        _norm_token(t)
        for field in ("query", "content_shape")
        for t in TOKEN_RE.findall(str(request.get(field) or "").lower())
    }
    haystack |= {_norm_token(str(t).lower()) for t in request.get("tags", [])}
    if topic & haystack or {_norm_token(t) for t in topic} & haystack:
        return None
    return ("Subject mismatch: artwork is about "
            f"{', '.join(sorted(topic))}, which this deck never mentions. "
            "Reused under the component-first policy; review baked source content.")


def score_request(
    request: dict,
    registry_items: list[dict],
    weights: dict[str, int],
    prefer_set: str | None,
    top_n: int = 5,
    enrichment: dict[str, dict] | None = None,
    unit_profiles: dict[str, dict] | None = None,
) -> tuple[dict, list[dict]]:
    candidates = []
    intent_terms, dropped_intent = normalize_intent(request.get("intent", []))
    # Tags stay literal: `set-of-3` / `quy-trinh` are real item tags, not prose.
    req_terms = intent_terms | _semantic_terms(request.get("tags", []))
    item_count = request.get("item_count")
    request_needs_text = bool(request.get("content_structure"))
    needs_parallel_units = wants_parallel_units(request)
    type_intent = request_type_intent(request)

    for item in registry_items:
        reasons: list[str] = []
        retrieval: dict = {}
        eligible = item.get("status") == "published"
        if not eligible:
            reasons.append(f"Rejected status: {item.get('status')}")

        item_terms = _semantic_terms(item.get("intent", []) + item.get("tags", []))
        primary_matched = req_terms & item_terms
        semantic = 1.0 if not req_terms else len(primary_matched) / len(req_terms)
        record = (enrichment or {}).get(item.get("id"))
        secondary_matched: set[str] = set()
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
            sizes = declared_set_sizes(item)
            if sizes:
                retrieval["set_sizes"] = sorted(sizes)
            if isinstance(item_count, int) and sizes and item_count not in sizes:
                score = max(0.0, score - COUNT_FIT_PENALTY)
                reasons.append(
                    f"Count fit: request needs {item_count} items, component is "
                    f"set-of-{'/'.join(str(s) for s in sorted(sizes))}: -{COUNT_FIT_PENALTY}"
                )
            # Visual-unit fit. A component draws its cards/steps/columns whether
            # or not copy lands in them, so hosting N parallel items needs N
            # native units. This is capacity like `set-of-N`, not preference:
            # it is recorded as evidence here and enforced in `buildable()`, so
            # the candidate keeps its rank and the reason travels in the report.
            profile = (unit_profiles or {}).get(str(item.get("id"))) or {}
            units = profile.get("unit_count")
            if units is not None:
                retrieval["unit_count"] = units
                if needs_parallel_units and units != item_count:
                    reasons.append(
                        f"Visual-unit fit: request needs {item_count} parallel item(s), "
                        f"component repeats {units} native unit(s); "
                        f"{abs(units - item_count)} unit(s) would ship "
                        f"{'blank' if units > item_count else 'unfilled'}: not buildable"
                    )
            # Layout-grammar fit. A component built around a display/quote panel
            # hosts one statement, not N parallel items. Penalised (never made
            # ineligible) only when the request explicitly wants N>=2 parallel
            # items AND the component offers no repeat group of that size, so a
            # better-matched published candidate can win while this one stays
            # available if nothing else fits.
            panel = profile.get("display_surface")
            if (needs_parallel_units and panel
                    and item_count not in (profile.get("group_sizes") or [])):
                score = max(0.0, score - DISPLAY_SURFACE_PENALTY)
                retrieval["display_surface"] = panel
                reasons.append(
                    f"Layout-grammar fit: component is built around a "
                    f"{panel['font_px']}px display/quote surface "
                    f"({', '.join(panel['slot_ids'])}) beside a {panel['body_slot_count']}-slot "
                    f"dense surface, and offers no {item_count}-unit repeat group; "
                    f"a statement layout is a weak host for {item_count} parallel items: "
                    f"-{DISPLAY_SURFACE_PENALTY}"
                )
            if record and record.get("slot_count") is not None:
                retrieval["slot_count"] = record["slot_count"]
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
            # BEFORE the decision branch below, so it can promote an item across
            # the 65 (adapt) / 75 (reuse) boundary. That is intentional but is
            # surfaced in `reasons` so the operator can see why the tier changed.
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
        candidate = {
            "item_id": item["id"],
            "eligible": eligible,
            "score": score,
            "criteria": criteria,
            "reasons": reasons,
        }
        if retrieval:
            candidate["retrieval"] = retrieval
        candidates.append(candidate)

    candidates.sort(key=lambda item: (item["eligible"], item["score"]), reverse=True)
    ranked_best = next((item for item in candidates if item["eligible"]), None)

    shape = request.get("content_shape")
    raw_item_terms = {
        item["id"]: {str(t).lower() for t in (item.get("intent", []) + item.get("tags", []))}
        for item in registry_items
    }

    def buildable(item: dict) -> bool:
        """Hard guards — these are physical or categorical, not preferences.

        A component with no text slots cannot host copy, and a set-of-3 cannot
        host 4 items. Both already cost score, but a penalty only reorders: a
        strong-metadata item can still win its band and ship a slide that
        structurally cannot hold the approved content. Capacity is therefore an
        eligibility question, while score stays a ranking question.

        The same applies to content_shape. validate_selection_report enforces
        T1 selection-lock and fails the run, so a candidate that cannot pass it
        must never be selected here — otherwise the scorer proposes decisions
        the very next gate rejects.
        """
        retrieval = item.get("retrieval") or {}
        if request_needs_text and retrieval.get("slot_count") == 0:
            return False
        sizes = retrieval.get("set_sizes")
        if isinstance(item_count, int) and sizes and item_count not in sizes:
            return False
        # Repeat structure is the same class of constraint as `set-of-N`, but
        # measured from the component's real geometry instead of a declared tag.
        # A 4-step flow cannot host 3 ideas without shipping a blank step, so it
        # is skipped here and the next compatible published candidate wins.
        units = retrieval.get("unit_count")
        if needs_parallel_units and isinstance(units, int) and units != item_count:
            return False
        if not shape_lock_ok(shape, request,
                             raw_item_terms.get(item["item_id"], set()),
                             set(retrieval.get("set_sizes") or [])):
            return False
        return True

    topic_warnings: dict[str, str] = {}
    for candidate in candidates:
        warning = topic_warning(candidate["item_id"], request, req_terms,
                                (enrichment or {}).get(candidate["item_id"]))
        if warning:
            candidate["reasons"].append(warning)
            topic_warnings[candidate["item_id"]] = warning

    # Generation is published-component-only. The top physically buildable
    # candidate is used directly; score ranks candidates rather than acting as
    # a semantic approval threshold.
    selectable = [
        item for item in candidates
        if item["eligible"]
        and buildable(item)
    ]
    chosen = selectable[0] if selectable else None
    score = chosen["score"] if chosen else 0
    warnings: list[str] = []
    blocked = [c for c in candidates if c.get("subject_safe") is False]
    if chosen:
        action, reason = "reuse", "Top published buildable component selected by retrieval ranking."
    elif not ranked_best:
        action, reason = "text-only", "No published export-compatible component was eligible; render approved text only."
    else:
        action, reason = (
            "text-only",
            "No published component passed the editable-content, count, visual-unit, and shape "
            "requirements; render approved text only.",
        )
    if dropped_intent:
        warnings.append(
            "intent carried non-canonical prose that was excluded from the "
            f"semantic ratio: {', '.join(dropped_intent)}. Use canonical "
            "retrieval tokens in `intent` and keep prose in `query`."
        )
    if chosen and chosen["item_id"] in topic_warnings:
        warnings.append(f"{chosen['item_id']}: {topic_warnings[chosen['item_id']]}")
    # A penalised layout-grammar mismatch can still win when nothing better is
    # published. That is the intended fallback, but the reviewer must see it.
    chosen_panel = (chosen or {}).get("retrieval", {}).get("display_surface")
    if chosen_panel:
        warnings.append(
            f"{chosen['item_id']}: selected despite a layout-grammar mismatch — it is a "
            f"{chosen_panel['font_px']}px display/quote layout with no {item_count}-unit "
            "repeat group, and no better published candidate was available. Review the "
            "rendered slide, or render text-only."
        )

    no_buildable_candidate = chosen is None
    decision = {
        "action": action,
        "item_id": chosen["item_id"] if chosen else None,
        "score": score,
        "reason": reason,
        "extraction_recommended": (
            bool(request.get("recommend_extraction", False)) or no_buildable_candidate
        ),
        "warnings": warnings,
        "evidence": {
            "scored_intent_terms": sorted(intent_terms),
            "dropped_intent_terms": dropped_intent,
            "subject_warnings": (
                [chosen["item_id"]]
                if chosen and chosen["item_id"] in topic_warnings else []
            ),
        },
    }
    top_candidates = candidates[:top_n]
    if chosen and all(item["item_id"] != chosen["item_id"] for item in top_candidates):
        top_candidates.append(chosen)
    return decision, top_candidates


# --- CLI input preflight ----------------------------------------------------
# A request that carries no canonical `intent` is not "a weak request" — it is
# an UNSCORABLE one. `overlap_score()` returns 1.0 for an empty request-term set
# (nothing asked for is trivially covered), so an empty or malformed payload
# earns FULL semantic credit, clears the reuse floor, and selects a generic
# published asset at score 90. That is how `{}` produced
# `reuse: sun.asset.logo (90.0)` and exited 0.
#
# There is no visual-requests.schema.json in this repo, so the contract below is
# derived from what `score_request()` actually reads plus the shape real jobs
# emit (analysis/visual-requests.json). Only `intent` is required: it is the one
# field whose absence silently inverts the score. Everything else is optional
# but type-checked when present, so a typo fails loudly instead of being ignored.
# Nothing is repaired or guessed.
_BATCH_MARKERS = ("slides", "requests")
_SINGLE_MARKERS = ("intent", "tags", "content_structure", "content_shape",
                   "request_id", "query")
_STR_FIELDS = ("request_id", "query", "content_shape", "density", "brand",
               "prefer_type")
_STR_LIST_FIELDS = ("intent", "tags", "content_structure", "required_exports")


def validate_single_request(payload: object, label: str) -> list[str]:
    """Plain-language errors for one visual request (empty list == valid)."""
    if not isinstance(payload, dict):
        return [f"{label}: expected a JSON object, got {type(payload).__name__}"]
    errors: list[str] = []
    batch_keys = [key for key in _BATCH_MARKERS if key in payload]
    if batch_keys:
        errors.append(
            f"{label}: carries {'/'.join(batch_keys)}, so this is a batch "
            "envelope, not a single request — re-run with --batch-request"
        )
    if not payload:
        return errors + [f"{label}: is an empty object; a request with no "
                         "`intent` scores every generic item at full semantic "
                         "credit, so it can never be scored honestly"]
    for field in _STR_LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list):
            errors.append(f"{label}: '{field}' must be a list of strings, got "
                          f"{type(value).__name__}")
        elif any(not isinstance(v, str) or not v.strip() for v in value):
            errors.append(f"{label}: '{field}' contains a non-string or blank entry")
    for field in _STR_FIELDS:
        if field in payload and not isinstance(payload[field], str):
            errors.append(f"{label}: '{field}' must be a string, got "
                          f"{type(payload[field]).__name__}")
    if "item_count" in payload:
        count = payload["item_count"]
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            errors.append(f"{label}: 'item_count' must be a positive integer, "
                          f"got {count!r}")
    if "recommend_extraction" in payload and not isinstance(
            payload["recommend_extraction"], bool):
        errors.append(f"{label}: 'recommend_extraction' must be true or false")
    intent = payload.get("intent")
    if not isinstance(intent, list) or not [v for v in intent
                                            if isinstance(v, str) and v.strip()]:
        errors.append(f"{label}: 'intent' is required and must be a non-empty "
                      "list of strings — without it every candidate scores full "
                      "semantic credit and a generic asset wins")
    return errors


def validate_batch_request(payload: object, label: str) -> list[str]:
    """Errors for a whole job envelope. Every slide is checked BEFORE scoring
    starts, so one bad slide can never leave a partial report on disk."""
    if not isinstance(payload, dict):
        return [f"{label}: expected a JSON object, got {type(payload).__name__}"]
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        if any(key in payload for key in _SINGLE_MARKERS):
            return [f"{label}: looks like a single visual request, not a job "
                    "envelope — re-run with --request"]
        return [f"{label}: 'slides' is missing, empty, or not a list"]
    errors: list[str] = []
    for position, slide in enumerate(slides, 1):
        slide_label = f"{label}: slide {position}"
        if isinstance(slide, dict) and slide.get("request_id"):
            slide_label = f"{label}: slide {position} ({slide['request_id']})"
        errors.extend(validate_single_request(slide, slide_label))
    return errors


def _reject(errors: list[str]) -> None:
    """Abort before any scoring or output write. Nothing is written on failure."""
    if errors:
        raise SystemExit(
            "Refusing to score: the request input is invalid (no output was "
            "written).\n  - " + "\n  - ".join(errors)
        )


def main() -> int:
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
        help="Template-set prefix (e.g. interview-workshop-sunriser). Same-set items get a +5 bonus.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top candidates to include in output (default: 5).",
    )
    parser.add_argument(
        "--retrieval-index",
        default=str(DEFAULT_RETRIEVAL_INDEX),
        help="Published-only retrieval projection (JSONL) used to broaden "
             "lexical matching. Pass 'none' to disable enrichment.",
    )
    parser.add_argument(
        "--unit-registry",
        default=str(DEFAULT_UNIT_REGISTRY),
        help="Full registry read (read-only) for published text-slot geometry, "
             "used to check that a component repeats as many native units as the "
             "request has parallel items. Pass 'none' to disable.",
    )
    parser.add_argument(
        "--reject-item", action="append", default=[], metavar="ITEM_ID",
        help="DIAGNOSTIC ONLY. Exclude a published item from selection, "
             "repeatable. Normal generation must not need this: if a candidate "
             "is unsafe, fix eligibility instead. The value is persisted to "
             "`rejected_items` in the report so a rerun is reproducible.",
    )
    args = parser.parse_args()

    registry = load_json(args.registry)
    weights = weights_for(args.item_type)

    rejected = set(args.reject_item)
    registry_items = [
        item
        for item in registry.get("items", [])
        if (args.item_type is None or item.get("type") == args.item_type)
        and item.get("id") not in rejected
    ]
    unknown = rejected - {item.get("id") for item in registry.get("items", [])}
    if unknown:
        raise SystemExit(f"--reject-item: not in registry: {', '.join(sorted(unknown))}")

    if args.retrieval_index.strip().lower() == "none":
        enrichment: dict[str, dict] = {}
    else:
        enrichment = load_retrieval_index(args.retrieval_index)
        if not enrichment:
            print(f"note: retrieval index empty, missing, or unreadable ({args.retrieval_index}); "
                  f"scoring without lexical enrichment", file=sys.stderr)
    retrieval_index_used = str(args.retrieval_index) if enrichment else None

    index = _build_inverted_index(registry_items, enrichment)

    def unit_profiles_for(requests: list[dict]) -> dict[str, dict]:
        """Load slot geometry once per run, and only when a request needs it."""
        if args.unit_registry.strip().lower() == "none":
            return {}
        if not any(wants_parallel_units(r) for r in requests if isinstance(r, dict)):
            return {}
        profiles = load_unit_profiles(args.unit_registry,
                                      {item.get("id") for item in registry_items})
        if not profiles:
            print(f"note: no published slot geometry available ({args.unit_registry}); "
                  f"scoring without the visual-unit and layout-grammar checks", file=sys.stderr)
        return profiles

    if args.request:
        request = load_json(args.request)
        _reject(validate_single_request(request, args.request))
        unit_profiles = unit_profiles_for([request])
        filtered = _prefilter(request, registry_items, index)
        decision, candidates = score_request(request, filtered, weights, args.prefer_set,
                                             args.top_n, enrichment, unit_profiles)
        report = {
            "request_id": request.get("request_id", "visual-request"),
            "generated_at": now_iso(),
            "generated_by": "score_visual_items.py",
            "scorer_version": SCORER_VERSION,
            "retrieval_index": retrieval_index_used,
            "rejected_items": sorted(rejected),
            "decision": decision,
            "candidates": candidates,
        }
        write_json(args.output, report)
        print(f"{decision['action']}: {decision['item_id']} ({decision['score']})")

    else:
        batch = load_json(args.batch_request)
        # Whole-batch preflight: every slide is validated before the FIRST one is
        # scored, so an invalid slide 9 cannot leave a report covering slides 1-8.
        _reject(validate_batch_request(batch, args.batch_request))
        slides = batch["slides"]
        job_id = batch.get("job_id", "batch")
        unit_profiles = unit_profiles_for(slides)
        slide_results = []
        for slide_req in slides:
            filtered = _prefilter(slide_req, registry_items, index)
            decision, candidates = score_request(slide_req, filtered, weights, args.prefer_set,
                                                 args.top_n, enrichment, unit_profiles)
            slide_results.append(
                {
                    "request_id": slide_req.get("request_id", ""),
                    "decision": decision,
                    "candidates": candidates,
                }
            )
            print(f"{slide_req.get('request_id', '?')}: {decision['action']}: {decision['item_id']} ({decision['score']})")
        report = {
            "job_id": job_id,
            "generated_at": now_iso(),
            "generated_by": "score_visual_items.py",
            "scorer_version": SCORER_VERSION,
            "retrieval_index": retrieval_index_used,
            "rejected_items": sorted(rejected),
            "slides": slide_results,
        }
        write_json(args.output, report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
