#!/usr/bin/env python3
"""Validate visual registry IDs, paths, statuses, aliases, and contracts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import load_json, resolve_repo_path


ID_PATTERN = re.compile(r"^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+$")
VALID_STATUS = {"staging", "qa", "published", "deprecated", "rejected"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"),
    )
    parser.add_argument(
        "--aliases",
        default=str(Path(__file__).resolve().parents[1] / "registries/aliases.json"),
    )
    parser.add_argument("--allow-missing-paths", action="store_true")
    args = parser.parse_args()

    registry = load_json(args.registry)
    aliases = load_json(args.aliases).get("aliases", {})
    errors: list[str] = []
    ids: set[str] = set()

    for item in registry.get("items", []):
        item_id = item.get("id", "")
        if not ID_PATTERN.match(item_id):
            errors.append(f"Invalid ID: {item_id}")
        if item_id in ids:
            errors.append(f"Duplicate ID: {item_id}")
        ids.add(item_id)
        if item.get("status") not in VALID_STATUS:
            errors.append(f"Invalid status for {item_id}")
        for key in ("artifact", "preview"):
            value = item.get("paths", {}).get(key)
            if not value or args.allow_missing_paths:
                continue
            if not resolve_repo_path(value).exists():
                errors.append(f"Missing {key} path for {item_id}: {value}")

    for alias, item_id in aliases.items():
        if item_id not in ids:
            errors.append(f"Alias {alias} points to unknown ID {item_id}")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"Valid registry: {len(ids)} items, {len(aliases)} aliases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

