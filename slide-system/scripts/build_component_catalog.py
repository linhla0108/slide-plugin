#!/usr/bin/env python3
"""Generate catalog data from published/QA registry items and staging outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import load_json, now_iso, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"),
    )
    parser.add_argument(
        "--extractions",
        default=str(Path(__file__).resolve().parents[2] / "outputs/component-extractions"),
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "catalog/catalog-data.json"),
    )
    args = parser.parse_args()

    registry = load_json(args.registry)
    items = list(registry.get("items", []))
    extraction_root = Path(args.extractions)
    if extraction_root.exists():
        for mapping_path in extraction_root.glob("*/items/*/mapping.json"):
            mapping = load_json(mapping_path)
            if mapping.get("status") not in {"staging", "qa"}:
                continue
            item_dir = mapping_path.parent
            items.append(
                {
                    "id": mapping["candidate_stable_id"],
                    "version": "0.0.0",
                    "name": mapping.get("name", mapping["item_id"]),
                    "type": mapping["type"],
                    "category": mapping.get("category", mapping["type"]),
                    "status": "staging",
                    "brand": mapping.get("brand"),
                    "intent": mapping.get("semantic_intent", []),
                    "tags": mapping.get("tags", []),
                    "source": mapping["source"],
                    "paths": {
                        "artifact": str(item_dir / "artifact"),
                        "visual": str(item_dir / mapping["text_contract"]["visual"])
                        if mapping.get("text_contract")
                        else None,
                        "text_slots": str(item_dir / mapping["text_contract"]["slots"])
                        if mapping.get("text_contract")
                        else None,
                        "preview": str(item_dir / "preview"),
                        "detail": str(item_dir / "README.md"),
                        "evidence": str(item_dir / "evidence"),
                    },
                    "content_fields": mapping.get("content_fields", {}),
                    "text_contract": mapping.get("text_contract"),
                    "variants": mapping.get("variants", []),
                    "compatibility": mapping.get("compatibility", {}),
                    "limitations": mapping.get("limitations", []),
                }
            )

    data = {
        "generated_at": now_iso(),
        "counts": {
            "published": sum(item.get("status") == "published" for item in items),
            "staging": sum(item.get("status") in {"staging", "qa"} for item in items),
        },
        "items": items,
    }
    write_json(args.output, data)
    print(f"Catalog data: {len(items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
