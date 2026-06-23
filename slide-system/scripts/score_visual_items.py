#!/usr/bin/env python3
"""Score published visual items for a normalized slide need."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from _common import load_json, now_iso, write_json


SCORER_VERSION = "3.1.0"

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


def weights_for(item_type: str | None) -> dict[str, int]:
    return TEMPLATE_WEIGHTS if item_type == "template" else WEIGHTS


def overlap_score(left: Iterable[str], right: Iterable[str]) -> float:
    a = _canonicalize(left)
    b = _canonicalize(right)
    if not a:
        return 1.0
    return len(a & b) / len(a)


def _build_inverted_index(items: list[dict]) -> dict[str, list[int]]:
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
        for term in terms:
            idx.setdefault(term, []).append(i)
    return idx


def _prefilter(request: dict, items: list[dict], index: dict[str, list[int]]) -> list[dict]:
    req_terms = _canonicalize(request.get("intent", []) + request.get("tags", []))
    hit_indices: set[int] = set()
    for term in req_terms:
        if term in index:
            hit_indices.update(index[term])
    if not hit_indices or len(hit_indices) < 5:
        return items
    return [items[i] for i in hit_indices]


def score_request(
    request: dict,
    registry_items: list[dict],
    weights: dict[str, int],
    prefer_set: str | None,
    top_n: int = 5,
) -> tuple[dict, list[dict]]:
    candidates = []

    for item in registry_items:
        reasons: list[str] = []
        eligible = item.get("status") == "published"
        if not eligible:
            reasons.append(f"Rejected status: {item.get('status')}")

        required_exports = request.get("required_exports", [])
        compat = item.get("compatibility", {})
        incompatible = [
            target
            for target in required_exports
            if compat.get(target, "supported") in {"unsupported", "untested"}
        ]
        if incompatible:
            eligible = False
            reasons.append(f"Unsupported or untested exports: {', '.join(incompatible)}")

        semantic = overlap_score(
            request.get("intent", []) + request.get("tags", []),
            item.get("intent", []) + item.get("tags", []),
        )
        structure = overlap_score(
            request.get("content_structure", []),
            item.get("content_structure", []),
        )
        density = 1.0 if item.get("density") in {"any", request.get("density", "any")} else 0.4
        brand = 1.0 if item.get("brand") in {None, request.get("brand")} else 0.0
        export = 1.0 if not incompatible else 0.0
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
        candidates.append(
            {
                "item_id": item["id"],
                "eligible": eligible,
                "score": score,
                "criteria": criteria,
                "reasons": reasons,
            }
        )

    candidates.sort(key=lambda item: (item["eligible"], item["score"]), reverse=True)
    best = next((item for item in candidates if item["eligible"]), None)
    score = best["score"] if best else 0
    semantic_floor = weights["semantic_intent"] * 0.3
    best_semantic = best["criteria"]["semantic_intent"] if best else 0
    if not best:
        action, reason = "blocked", "No published export-compatible item was eligible."
    elif best_semantic < semantic_floor:
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
    decision = {
        "action": action,
        "item_id": best["item_id"] if best else None,
        "score": score,
        "reason": reason,
        "extraction_recommended": bool(request.get("recommend_extraction", False)) or low_score,
    }
    top_candidates = candidates[:top_n]
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
    args = parser.parse_args()

    registry = load_json(args.registry)
    weights = weights_for(args.item_type)

    registry_items = [
        item
        for item in registry.get("items", [])
        if args.item_type is None or item.get("type") == args.item_type
    ]

    index = _build_inverted_index(registry_items)

    if args.request:
        request = load_json(args.request)
        filtered = _prefilter(request, registry_items, index)
        decision, candidates = score_request(request, filtered, weights, args.prefer_set, args.top_n)
        report = {
            "request_id": request.get("request_id", "visual-request"),
            "generated_at": now_iso(),
            "generated_by": "score_visual_items.py",
            "scorer_version": SCORER_VERSION,
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
            decision, candidates = score_request(slide_req, filtered, weights, args.prefer_set, args.top_n)
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
            "slides": slide_results,
        }
        write_json(args.output, report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
