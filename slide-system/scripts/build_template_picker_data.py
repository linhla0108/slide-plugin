#!/usr/bin/env python3
"""Build the template-picker data file from the published visual library.

Reads ONLY ``visual-library.json`` (never ``catalog-data.json`` — the catalog
build normalizes 14 ``sun-goal-*`` pages into ``template`` and they must not
leak into the user-facing picker). Filters to ``status == "published"`` and
``type == "template"`` and emits a slim per-card record for the static UI.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from _common import REPO_ROOT, load_json, now_iso, write_json

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "registries/visual-library.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "template-picker/picker-data.json"
# The picker page lives here; emitted asset paths are made relative to it so the
# static UI resolves them no matter what directory the HTTP server roots at.
PICKER_DIR = Path(__file__).resolve().parents[1] / "template-picker"


def to_page_relative(repo_rel: str | None) -> str | None:
    """Convert a repo-root-relative path to one relative to the picker page dir
    (e.g. ``slide-system/library/templates/x/preview/thumbnail.png`` ->
    ``../library/templates/x/preview/thumbnail.png``)."""
    if not repo_rel:
        return repo_rel
    return os.path.relpath((REPO_ROOT / repo_rel).resolve(), PICKER_DIR).replace(os.sep, "/")

# Intent keyword -> use-case bucket. Order matters: the first bucket whose
# keyword set intersects the item's intent/tags wins. "Other" is the fallback.
USE_CASE_RULES: list[tuple[str, set[str]]] = [
    ("Cover", {"cover", "title", "opening", "hero", "intro", "front"}),
    ("Section", {"section", "divider", "agenda", "chapter", "toc",
                 "table-of-contents", "contents", "transition"}),
    ("Data", {"data", "chart", "metric", "metrics", "stat", "stats",
              "table", "graph", "kpi", "comparison", "dashboard", "number"}),
    ("Closing", {"closing", "close", "thanks", "thank-you", "summary",
                 "conclusion", "cta", "contact", "end", "outro", "wrap"}),
    ("Content", {"content", "body", "list", "cards", "card", "columns",
                 "column", "feature", "features", "detail", "details",
                 "text", "bullets", "grid", "image", "quote", "process"}),
]


def derive_use_case(intent: list[str], tags: list[str]) -> str:
    """Bucket an item by its semantic intent (falling back to tags)."""
    terms = {str(t).lower().strip() for t in [*intent, *tags] if t}
    for bucket, keywords in USE_CASE_RULES:
        if terms & keywords:
            return bucket
        # Substring match catches compounds like "section-header" or "cover-title".
        for term in terms:
            if any(keyword in term for keyword in keywords):
                return bucket
    return "Other"


def derive_thumbnail(preview: str | None) -> str | None:
    """Prefer ``<preview-dir>/thumbnail.png`` when it exists on disk."""
    if not preview:
        return preview
    preview_path = (REPO_ROOT / preview)
    base_dir = preview_path if preview_path.is_dir() else preview_path.parent
    thumb = base_dir / "thumbnail.png"
    if thumb.exists():
        try:
            return str(thumb.relative_to(REPO_ROOT))
        except ValueError:
            return str(thumb)
    return preview


def derive_deck(item: dict) -> dict:
    """Identify the source deck a template slide belongs to, from its source
    file. Slides extracted from the same original deck form one full set."""
    src = item.get("source") or {}
    path = src.get("path") or ""
    base = os.path.basename(path)
    stem = re.sub(r"\.(pdf|pptx|key|svg|png|jpe?g)$", "", base, flags=re.I) or base or "Other"
    # Keep dotted brand names as-is (SUN.SLIDE); prettify underscore_case decks.
    name = stem.replace("_", " ").title() if "_" in stem else stem
    deck_id = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "deck"
    return {"deck_id": deck_id, "name": name, "source": base}


def build_card(item: dict) -> dict:
    intent = item.get("intent") or []
    tags = item.get("tags") or []
    preview = (item.get("paths") or {}).get("preview")
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("id"),
        "intent": intent,
        "tags": tags,
        "content_structure": item.get("content_structure") or [],
        "slide_number": (item.get("source") or {}).get("slide"),
        "preview": to_page_relative(preview),
        "thumbnail": to_page_relative(derive_thumbnail(preview)),
        "use_case": derive_use_case(intent, tags),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="Path to visual-library.json (default: slide-system registry).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to write picker-data.json (default: template-picker dir).",
    )
    args = parser.parse_args()

    registry = load_json(args.registry)
    published_templates = [
        item
        for item in registry.get("items", [])
        if item.get("status") == "published" and item.get("type") == "template"
    ]

    # Group slides into their source deck (a full set), ordered by slide number.
    decks: dict[str, dict] = {}
    cards = []
    for item in published_templates:
        card = build_card(item)
        cards.append(card)
        deck = derive_deck(item)
        bucket = decks.setdefault(deck["deck_id"], {**deck, "slides": []})
        bucket["slides"].append(card)

    deck_list = list(decks.values())
    for deck in deck_list:
        deck["slides"].sort(
            key=lambda c: (c.get("slide_number") is None, c.get("slide_number") or 0)
        )
        deck["slide_count"] = len(deck["slides"])
    # Full sets (more slides) first, then alphabetical.
    deck_list.sort(key=lambda d: (-d["slide_count"], d["name"].lower()))

    write_json(
        args.output,
        {
            "generated_at": now_iso(),
            "source": "visual-library.json",
            "count": len(cards),
            "deck_count": len(deck_list),
            "decks": deck_list,
            "templates": cards,
        },
    )

    summary = ", ".join(f"{d['name']}:{d['slide_count']}" for d in deck_list) or "none"
    print(f"picker-data: {len(cards)} templates in {len(deck_list)} deck(s) ({summary}) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
