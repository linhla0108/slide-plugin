#!/usr/bin/env python3
"""Metadata quality gate for reusable components before publish/retrieval.

Retrieval (the hybrid scorer, and any later RAG) can only be as good as the
metadata it reads. Auto-staged Docling drafts and thin manual extractions can
carry OCR noise, generic "review and publish this" placeholders, empty
keyword/use-case lists, or missing retrieval fields — all of which make a
published component either unselectable or wrongly selectable.

This gate enforces a small, honest metadata contract for `type == "component"`
items (the registry's reusable components and component-sets). It is used two
ways:

  * publish-time — `publish_extraction.py` calls `validate_item()` before it
    mutates any registry/library state, so a draft with weak metadata cannot be
    published.
  * registry audit — `--registry` validates every published component and exits
    non-zero (with plain-language errors) when any fails.

No new dependencies, no network, no embeddings. Scope is deliberately narrow:
non-component item types (templates, assets, characters) are never gated here.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import load_json


# Only reusable components are gated. In this registry both plain components and
# component-sets carry type == "component" (category distinguishes them), so the
# single type check covers both; templates/assets/characters are out of scope.
GATED_TYPE = "component"

# Retrieval-ready contract. Lists must be non-empty; strings must be non-blank.
# Minimum list length is 1 (presence, not padding) so honest single-term
# metadata passes and only empty/missing fields fail.
REQUIRED_LIST_FIELDS = ("intent", "tags", "content_structure", "keywords",
                        "use_cases", "anti_use_cases")
REQUIRED_STRING_FIELDS = ("component_type", "layout_role", "visual_summary",
                          "retrieval_notes", "quality_notes")

# Placeholder / auto-stage / OCR-provenance phrases that must never survive as
# final published metadata. Matched case-insensitively as substrings across all
# metadata strings. These are the SPECIFIC boilerplate phrases the auto-stage
# and grouping steps emit — not the bare word "docling", which legitimately
# appears in honest notes like "not a Docling auto-detected candidate".
BOILERPLATE_PHRASES = (
    "detected visual region",
    "candidate detected by docling",
    "picture candidate detected",
    "table candidate detected",
    "figure candidate detected",
    "auto-staged",
    "auto staged",
    "generated from docling",
    "generated from region text",
    "review and publish this",
    "review and publish related",
    "do not use before the draft",
    "before every carousel variant is reviewed",
    "auto-generated from pdf",
    "auto-grouped from related",
    "group metadata is generated from",
    "related detected components",
    "region cue:",
)

# An intent term longer than this reads as raw slide text / OCR noise rather
# than a semantic retrieval label (honest intents are short: "timeline",
# "ranking", "process"). --strict lowers the ceiling.
INTENT_TERM_MAXLEN = 48
INTENT_TERM_MAXLEN_STRICT = 32

# Purely positional / generic names carry no retrieval signal.
GENERIC_NAME_RE = re.compile(
    r"^(component|region|group|item|slide|page|visual|figure|candidate)"
    r"[\s._-]*\d*$",
    re.IGNORECASE,
)

# Tokens that expose a repeated-part shape (set-of-N). Used by the --strict
# multiplicity check for component-set items.
SET_SHAPE_RE = re.compile(r"(set-of-\d+|repeatable|\bset\b|two-column|three-column|"
                          r"four-column|grid|carousel|cards)", re.IGNORECASE)


def is_gated(item: dict) -> bool:
    """True when this item is a reusable component subject to the gate."""
    return item.get("type") == GATED_TYPE


def _is_set_like(item: dict) -> bool:
    if item.get("category") == "component-set":
        return True
    ident = f"{item.get('id', '')} {item.get('name', '')}".lower()
    return ident.rstrip().endswith("set") or ident.endswith("-set") or "card-set" in ident


def _all_strings(item: dict) -> list[str]:
    """Every human-readable metadata string on the item (for phrase scanning)."""
    out: list[str] = []
    for field in REQUIRED_LIST_FIELDS:
        for value in item.get(field) or []:
            out.append(str(value))
    for field in (*REQUIRED_STRING_FIELDS, "name"):
        value = item.get(field)
        if value:
            out.append(str(value))
    return out


def metadata_from_mapping(mapping: dict, stable_id: str | None = None) -> dict:
    """Project an extraction `mapping.json` onto the registry-item metadata
    shape this gate validates. Keeps publish_extraction and the validator in
    lockstep on field names (mapping uses `semantic_intent`; the item uses
    `intent`) without duplicating the mapping there."""
    return {
        "id": stable_id or mapping.get("candidate_stable_id") or mapping.get("item_id"),
        "type": mapping.get("type"),
        "category": mapping.get("category"),
        "name": mapping.get("name"),
        "intent": mapping.get("semantic_intent") or [],
        "tags": mapping.get("tags") or [],
        "content_structure": mapping.get("content_structure") or [],
        "component_type": mapping.get("component_type"),
        "layout_role": mapping.get("layout_role"),
        "visual_summary": mapping.get("visual_summary"),
        "keywords": mapping.get("keywords") or [],
        "use_cases": mapping.get("use_cases") or [],
        "anti_use_cases": mapping.get("anti_use_cases") or [],
        "quality_notes": mapping.get("quality_notes"),
        "retrieval_notes": mapping.get("retrieval_notes"),
        "text_contract": mapping.get("text_contract"),
    }


def validate_item(item: dict, strict: bool = False) -> list[str]:
    """Return plain-language error strings for one item (empty list == valid).

    Non-gated item types return no errors — the caller may still choose to skip
    them, but this keeps the function safe to call on any item.
    """
    if not is_gated(item):
        return []

    errors: list[str] = []
    item_id = item.get("id", "<unknown>")

    # 1. Required lists present and non-empty.
    for field in REQUIRED_LIST_FIELDS:
        value = item.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"{item_id}: '{field}' is empty or missing (needs >=1 term)")
            continue
        if any(not str(v).strip() for v in value):
            errors.append(f"{item_id}: '{field}' contains a blank term")

    # 2. Required strings present and non-blank.
    for field in REQUIRED_STRING_FIELDS:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{item_id}: '{field}' is blank or missing")

    # 3. No auto-stage / Docling / OCR-provenance boilerplate anywhere.
    blob = " ||| ".join(_all_strings(item)).lower()
    for phrase in BOILERPLATE_PHRASES:
        if phrase in blob:
            errors.append(
                f"{item_id}: metadata still carries auto-stage/placeholder text "
                f"({phrase!r}); author real semantic metadata before publish"
            )

    # 4. Intent terms must be short semantic labels, not raw slide text / OCR.
    maxlen = INTENT_TERM_MAXLEN_STRICT if strict else INTENT_TERM_MAXLEN
    for term in item.get("intent") or []:
        if len(str(term)) > maxlen:
            errors.append(
                f"{item_id}: intent term {str(term)[:40]!r}... is too long "
                f"(>{maxlen} chars) — reads as raw slide text/OCR, not a label"
            )

    # 5. Name must not be blank or purely positional/generic.
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{item_id}: 'name' is blank or missing")
    elif GENERIC_NAME_RE.match(name.strip()):
        errors.append(f"{item_id}: 'name' {name!r} is generic/positional")

    # 6. Do not invent slot counts, but if a text contract exists its slot_count
    #    must be a real non-negative integer.
    contract = item.get("text_contract")
    if isinstance(contract, dict):
        slot_count = contract.get("slot_count")
        if not isinstance(slot_count, int) or isinstance(slot_count, bool) or slot_count < 0:
            errors.append(
                f"{item_id}: text_contract.slot_count must be a non-negative "
                f"integer (got {slot_count!r})"
            )

    # 7. (--strict) A set-like component should expose its repeated-part shape.
    if strict and _is_set_like(item):
        shape_blob = " ".join(
            str(v) for field in ("tags", "content_structure", "use_cases")
            for v in (item.get(field) or [])
        )
        if not SET_SHAPE_RE.search(shape_blob):
            errors.append(
                f"{item_id}: set-like component does not expose a set-of-N / "
                f"multiplicity shape in tags/content_structure/use_cases"
            )

    return errors


def validate_registry(registry: dict, strict: bool = False) -> dict[str, list[str]]:
    """Return {item_id: [errors]} for every gated component that fails."""
    failures: dict[str, list[str]] = {}
    for item in registry.get("items", []):
        if not is_gated(item):
            continue
        errs = validate_item(item, strict=strict)
        if errs:
            failures[item.get("id", "<unknown>")] = errs
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_registry = str(Path(__file__).resolve().parents[1]
                           / "registries/visual-library.json")
    parser.add_argument("--registry", default=default_registry,
                        help="Full visual-library.json to audit.")
    parser.add_argument("--item-id", default=None,
                        help="Validate only this registry item id.")
    parser.add_argument("--mapping", default=None,
                        help="Validate a single extraction mapping.json instead "
                             "of the registry.")
    parser.add_argument("--strict", action="store_true",
                        help="Tighten heuristics (shorter intent terms; require "
                             "set-of-N shape on set-like components).")
    args = parser.parse_args(argv)

    if args.mapping:
        item = metadata_from_mapping(load_json(args.mapping))
        errors = validate_item(item, strict=args.strict)
        if errors:
            print(f"FAIL: component metadata gate ({len(errors)} error(s))")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(f"PASS: {item.get('id')} metadata is retrieval-ready")
        return 0

    registry = load_json(args.registry)
    gated = [i for i in registry.get("items", []) if is_gated(i)]

    if args.item_id:
        item = next((i for i in registry.get("items", []) if i.get("id") == args.item_id), None)
        if item is None:
            print(f"ERROR: item id {args.item_id!r} not found in {args.registry}")
            return 2
        if not is_gated(item):
            print(f"SKIP: {args.item_id} is type {item.get('type')!r}, not a gated component")
            return 0
        errors = validate_item(item, strict=args.strict)
        if errors:
            print(f"FAIL: {args.item_id} ({len(errors)} error(s))")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(f"PASS: {args.item_id} metadata is retrieval-ready")
        return 0

    failures = validate_registry(registry, strict=args.strict)
    if failures:
        total = sum(len(v) for v in failures.values())
        print(f"FAIL: {len(failures)}/{len(gated)} published components have weak "
              f"metadata ({total} error(s)):")
        for item_id in sorted(failures):
            print(f"  {item_id}:")
            for e in failures[item_id]:
                print(f"    - {e.split(': ', 1)[-1]}")
        return 1
    print(f"PASS: all {len(gated)} published components meet the metadata contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
