#!/usr/bin/env python3
"""Build a deterministic component retrieval index for hybrid lexical search.

No embeddings, vector DB, network calls, or new dependencies are used here. The
output is JSONL so a later RAG layer can add embeddings next to the same stable
records without changing the extraction/publish contract.

`score_visual_items.py` consumes this index to broaden lexical matching beyond
compact intent/tags and to read compact buildability facts (`slot_count`).

Record schema v2 adds `slot_count` (from the registry `text_contract`; null
when the item has no text contract). v1 consumers are unaffected — the change
is additive.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _common import load_json

SYSTEM_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = SYSTEM_ROOT / "registries/visual-library.json"
DEFAULT_OUTPUT = SYSTEM_ROOT / "registries/component-retrieval-index.jsonl"
TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?", re.I)

TEXT_FIELDS = (
    "id", "name", "type", "category", "brand", "component_type",
    "layout_role", "visual_summary", "quality_notes", "retrieval_notes",
)
LIST_FIELDS = (
    "intent", "tags", "keywords", "content_structure", "use_cases",
    "anti_use_cases", "limitations", "variants",
)


def _strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_strings(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_strings(item))
        return out
    return [str(value)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = str(value).strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _terms(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in TOKEN_RE.findall(text.lower()):
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def build_record(item: dict) -> dict:
    text_values: list[str] = []
    for field in TEXT_FIELDS:
        text_values.extend(_strings(item.get(field)))
    for field in LIST_FIELDS:
        text_values.extend(_strings(item.get(field)))
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    if isinstance(source, dict):
        text_values.extend(_strings(source.get("kind")))
    text_values = _dedupe(text_values)
    search_text = " ".join(text_values).lower()
    return {
        "schema_version": 2,
        "id": item.get("id"),
        "status": item.get("status"),
        "retrieval_mode": "lexical-ready",
        "slot_count": (item.get("text_contract") or {}).get("slot_count"),
        "type": item.get("type"),
        "brand": item.get("brand"),
        "name": item.get("name"),
        "component_type": item.get("component_type"),
        "layout_role": item.get("layout_role"),
        "intent": item.get("intent") or [],
        "tags": item.get("tags") or [],
        "keywords": item.get("keywords") or [],
        "content_structure": item.get("content_structure") or [],
        "use_cases": item.get("use_cases") or [],
        "anti_use_cases": item.get("anti_use_cases") or [],
        "visual_summary": item.get("visual_summary"),
        "retrieval_notes": item.get("retrieval_notes"),
        "paths": item.get("paths") or {},
        "source": item.get("source"),
        "search_text": search_text,
        "retrieval_terms": _terms(search_text),
    }


def build_records(registry: dict) -> list[dict]:
    records = [
        build_record(item)
        for item in registry.get("items", [])
        if item.get("status") == "published" and item.get("id")
    ]
    return sorted(records, key=lambda record: record["id"])


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 when the output JSONL is missing or stale.")
    args = parser.parse_args(argv)

    records = build_records(load_json(Path(args.registry)))
    output = Path(args.output)
    desired = "".join(
        json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n"
        for record in records
    )
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != desired:
            print(f"STALE retrieval index: {output}")
            return 1
        print(f"clean retrieval index: {len(records)} records")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(desired, encoding="utf-8", newline="\n")
    print(f"wrote {len(records)} retrieval records -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
