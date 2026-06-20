#!/usr/bin/env python3
"""Score published visual items for a normalized slide need."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from _common import load_json, now_iso, write_json


WEIGHTS = {
    "semantic_intent": 35,
    "content_structure": 20,
    "density": 10,
    "brand": 10,
    "export_compatibility": 15,
    "accessibility": 10,
}

# Template selection rewards content structure over density. Sum stays 100.
TEMPLATE_WEIGHTS = {
    **WEIGHTS,
    "content_structure": 25,
    "density": 5,
}


def weights_for(item_type: str | None) -> dict[str, int]:
    return TEMPLATE_WEIGHTS if item_type == "template" else WEIGHTS


def overlap_score(left: Iterable[str], right: Iterable[str]) -> float:
    a = {str(value).lower() for value in left}
    b = {str(value).lower() for value in right}
    if not a:
        return 1.0
    return len(a & b) / len(a)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"),
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
    args = parser.parse_args()

    request = load_json(args.request)
    registry = load_json(args.registry)
    weights = weights_for(args.item_type)
    candidates = []

    for item in registry.get("items", []):
        if args.item_type is not None and item.get("type") != args.item_type:
            continue
        reasons: list[str] = []
        eligible = item.get("status") == "published"
        if not eligible:
            reasons.append(f"Rejected status: {item.get('status')}")

        required_exports = request.get("required_exports", [])
        incompatible = [
            target
            for target in required_exports
            if item.get("compatibility", {}).get(target) in {"unsupported", "untested", None}
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
        if args.prefer_set and eligible and score > 0:
            item_set = item["id"].split(".")[1] if item["id"].count(".") >= 2 else ""
            if item_set == args.prefer_set:
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
    if not best:
        action, reason = "blocked", "No published export-compatible item was eligible."
    elif score >= 75:
        action, reason = "reuse", "The best published item meets the reuse threshold."
    elif score >= 55:
        action, reason = "adapt-local", "Use a slide-local adaptation."
    else:
        action, reason = "custom-local", "Create a slide-local custom structure."

    report = {
        "request_id": request.get("request_id", "visual-request"),
        "generated_at": now_iso(),
        "decision": {
            "action": action,
            "item_id": best["item_id"] if best else None,
            "score": score,
            "reason": reason,
            "extraction_recommended": bool(request.get("recommend_extraction", False)),
        },
        "candidates": candidates,
    }
    write_json(args.output, report)
    print(f"{action}: {report['decision']['item_id']} ({score})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

