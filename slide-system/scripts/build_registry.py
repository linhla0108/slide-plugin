#!/usr/bin/env python3
"""build_registry.py — Reconcile visual-library.json with disk and regenerate
the compact projection deterministically.

Why reconcile, not rebuild: published library folders do NOT retain
`mapping.json` (`publish_extraction.py` copies only artifact/preview/evidence),
so the semantic metadata (intent, tags, compatibility, content_structure) lives
ONLY in `visual-library.json`. That file is therefore the metadata authority and
cannot be regenerated from disk. This tool keeps it honest against disk:

  * DANGLING — a registry entry whose `paths.artifact` no longer exists. With
    --write these are dropped (a deleted folder self-heals out of the registry).
  * ORPHAN  — a library folder containing `visual.svg` that no entry references.
    Reported, never auto-deleted: deletion is an explicit, separate action, and
    an orphan usually means "publish it" or "register it", not "destroy it".
  * COMPACT — `visual-library-compact.json` (what `score_visual_items.py` reads)
    is regenerated as a deterministic projection of the full registry, so it can
    never drift from it and is never hand-maintained.

    python3 slide-system/scripts/build_registry.py --check   # gate: exit 1 on drift
    python3 slide-system/scripts/build_registry.py --write    # drop dangling + rebuild compact
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import load_json, resolve_repo_path

SYSTEM_ROOT = Path(__file__).resolve().parents[1]
LIBRARY = SYSTEM_ROOT / "library"
REGISTRY = SYSTEM_ROOT / "registries/visual-library.json"
COMPACT = SYSTEM_ROOT / "registries/visual-library-compact.json"

# Keys the scorer's compact registry carries (see score_visual_items.py). Keep
# this list in lockstep with what the scorer actually reads.
COMPACT_KEYS = [
    "id", "type", "brand", "intent", "tags", "status",
    "density", "content_structure", "compatibility", "limitations",
]


def library_item_dirs() -> set[Path]:
    """Every folder under library/ that holds a reusable visual (its own
    `visual.svg`). This is the publish layout for both flat items
    (library/<type>/<id>/) and templates (library/templates/<set>/<slide>/)."""
    return {svg.parent.resolve() for svg in LIBRARY.rglob("visual.svg")}


def registry_artifact_dirs(items: list[dict]) -> set[Path]:
    dirs = set()
    for item in items:
        art = item.get("paths", {}).get("artifact")
        if art:
            dirs.add(resolve_repo_path(art).resolve())
    return dirs


def project_compact(items: list[dict]) -> dict:
    return {"items": [{k: item.get(k) for k in COMPACT_KEYS} for item in items]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true",
                       help="report drift and exit 1 if any; write nothing.")
    group.add_argument("--write", action="store_true",
                       help="drop dangling entries and rewrite the compact projection.")
    args = parser.parse_args()

    registry = load_json(REGISTRY)
    items = registry.get("items", [])

    dangling = [i for i in items
                if i.get("paths", {}).get("artifact")
                and not resolve_repo_path(i["paths"]["artifact"]).exists()]
    kept = [i for i in items if i not in dangling]

    art_dirs = registry_artifact_dirs(kept)
    orphans = sorted(str(d.relative_to(SYSTEM_ROOT.parent))
                     for d in library_item_dirs() - art_dirs)

    for i in dangling:
        print(f"DANGLING  {i['id']} -> {i['paths']['artifact']} (folder missing)")
    for o in orphans:
        print(f"ORPHAN    {o} (visual.svg present, no registry entry)")

    if args.check:
        drift = len(dangling) + len(orphans)
        print(f"{'DRIFT' if drift else 'clean'}: {len(dangling)} dangling, "
              f"{len(orphans)} orphan, {len(kept)} valid items")
        return 1 if drift else 0

    if args.write:
        if dangling:
            registry["items"] = kept
            REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
        COMPACT.write_text(json.dumps(project_compact(kept), ensure_ascii=False, indent=2) + "\n")
        print(f"wrote compact ({len(kept)} items); dropped {len(dangling)} dangling; "
              f"{len(orphans)} orphan folder(s) left for review")
        return 0

    # default: report only
    print(f"{len(kept)} valid items, {len(dangling)} dangling, {len(orphans)} orphan "
          f"(use --write to apply, --check to gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
