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
from typing import Iterable

from _common import load_json, now_iso, write_json


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
    except (OSError, json.JSONDecodeError):
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


def score_request(
    request: dict,
    registry_items: list[dict],
    weights: dict[str, int],
    prefer_set: str | None,
    top_n: int = 5,
    enrichment: dict[str, dict] | None = None,
) -> tuple[dict, list[dict]]:
    candidates = []
    req_terms = _canonicalize(request.get("intent", []) + request.get("tags", []))
    item_count = request.get("item_count")
    request_needs_text = bool(request.get("content_structure"))

    for item in registry_items:
        reasons: list[str] = []
        retrieval: dict = {}
        eligible = item.get("status") == "published"
        if not eligible:
            reasons.append(f"Rejected status: {item.get('status')}")

        item_terms = _canonicalize(item.get("intent", []) + item.get("tags", []))
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
    semantic_floor = weights["semantic_intent"] * 0.3
    ranked_best = next((item for item in candidates if item["eligible"]), None)
    best = next(
        (
            item for item in candidates
            if item["eligible"] and item["criteria"]["semantic_intent"] >= semantic_floor
        ),
        None,
    )
    chosen = best or ranked_best
    score = chosen["score"] if chosen else 0
    best_semantic = ranked_best["criteria"]["semantic_intent"] if ranked_best else 0
    if not ranked_best:
        action, reason = "blocked", "No published export-compatible item was eligible."
    elif not best:
        action, reason = "custom-local", f"Semantic intent too low ({best_semantic:.1f} < {semantic_floor:.1f}). No relevant component."
    elif score >= 75:
        action, reason = "reuse", "The best published item meets the reuse threshold."
    elif score >= 65:
        action, reason = "adapt-local", "Use a slide-local adaptation."
    else:
        action, reason = "custom-local", "No strong match (score < 65). Create a slide-local custom structure."

    # Below the adapt-local floor (65) there is no strong match, so recommend
    # extracting/authoring a new component rather than forcing a weak reuse.
    low_score = bool(best) and score < 65
    no_semantic_match = bool(ranked_best) and not best
    decision = {
        "action": action,
        "item_id": chosen["item_id"] if chosen else None,
        "score": score,
        "reason": reason,
        "extraction_recommended": (
            bool(request.get("recommend_extraction", False)) or low_score or no_semantic_match
        ),
    }
    top_candidates = candidates[:top_n]
    if chosen and all(item["item_id"] != chosen["item_id"] for item in top_candidates):
        top_candidates.append(chosen)
    return decision, top_candidates


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
    args = parser.parse_args()

    registry = load_json(args.registry)
    weights = weights_for(args.item_type)

    registry_items = [
        item
        for item in registry.get("items", [])
        if args.item_type is None or item.get("type") == args.item_type
    ]

    if args.retrieval_index.strip().lower() == "none":
        enrichment: dict[str, dict] = {}
    else:
        enrichment = load_retrieval_index(args.retrieval_index)
        if not enrichment:
            print(f"note: retrieval index empty or missing ({args.retrieval_index}); "
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
        job_id = batch.get("job_id", "batch")
        slide_results = []
        for slide_req in batch.get("slides", []):
            filtered = _prefilter(slide_req, registry_items, index)
            decision, candidates = score_request(slide_req, filtered, weights, args.prefer_set, args.top_n, enrichment)
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
            "slides": slide_results,
        }
        write_json(args.output, report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
