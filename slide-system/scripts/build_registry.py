#!/usr/bin/env python3
"""build_registry.py — Reconcile visual-library.json with disk and regenerate
the compact projection deterministically.

Why reconcile, not rebuild: published library folders do NOT retain
`mapping.json` (`publish_extraction.py` copies only artifact/preview/evidence),
so the semantic metadata (intent, tags, content_structure) lives
ONLY in `visual-library.json`. That file is therefore the metadata authority and
cannot be regenerated from disk. This tool keeps it honest against disk:

  * DANGLING — a registry entry whose `paths.artifact` no longer exists. With
    --write these are dropped (a deleted folder self-heals out of the registry).
  * ZOMBIE  — a stable_id that extraction-history records as `published` but that
    is absent from the registry (a renamed-away or deleted item). The registry is
    the single source of truth, so these history records are pure noise that make
    agents misread current state. With --write they are PURGED outright (every
    attempt for that id removed) — no tombstone, no alias left behind.
  * ORPHAN  — a library folder containing `visual.svg` that no entry references.
    Reported, never auto-deleted: deletion is an explicit, separate action, and
    an orphan usually means "publish it" or "register it", not "destroy it".
  * COMPACT — `visual-library-compact.json` (what `score_visual_items.py` reads)
    is regenerated as a deterministic projection of the full registry, so it can
    never drift from it and is never hand-maintained.

    python3 slide-system/scripts/build_registry.py --check   # gate: exit 1 on drift
    python3 slide-system/scripts/build_registry.py --write    # drop dangling + purge zombie history + rebuild compact
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import load_json, now_iso, resolve_repo_path, write_json
import build_component_retrieval_index as retrieval

SYSTEM_ROOT = Path(__file__).resolve().parents[1]
LIBRARY = SYSTEM_ROOT / "library"
REGISTRY = SYSTEM_ROOT / "registries/visual-library.json"
COMPACT = SYSTEM_ROOT / "registries/visual-library-compact.json"
RETRIEVAL = SYSTEM_ROOT / "registries/component-retrieval-index.jsonl"
HISTORY = SYSTEM_ROOT / "registries/extraction-history.json"

# Keys the scorer's compact registry carries (see score_visual_items.py). Keep
# this list in lockstep with what the scorer actually reads.
COMPACT_KEYS = [
    "id", "type", "brand", "intent", "tags", "status",
    "density", "content_structure", "limitations",
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


def retrieval_jsonl(items: list[dict]) -> str:
    records = retrieval.build_records({"items": items})
    return "".join(
        json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n"
        for record in records
    )


def history_zombie_ids(registry_ids: set[str]) -> list[str]:
    """stable_ids that extraction-history records as `published` in ANY attempt
    but which are absent from the registry. Using "ever published" (not just the
    latest status) is deliberate: a tombstoned id whose latest status was flipped
    to `unpublished` is still a zombie if it is not in the registry. The registry
    is the single source of truth, so these are stale records to be purged."""
    if not HISTORY.exists():
        return []
    ever_published: set[str] = set()
    for attempt in load_json(HISTORY).get("attempts", []):
        sid = attempt.get("stable_id")
        if sid and attempt.get("status") == "published":
            ever_published.add(sid)
    return sorted(sid for sid in ever_published if sid not in registry_ids)


def purge_history(zombie_ids: list[str]) -> int:
    """Remove EVERY extraction-history attempt for the given zombie ids. No
    tombstone, no alias — the registry is authority, so a record for an id that
    is not in the registry is noise. Returns the count of attempts removed."""
    if not zombie_ids or not HISTORY.exists():
        return 0
    history = load_json(HISTORY)
    attempts = history.get("attempts", [])
    drop = set(zombie_ids)
    kept = [a for a in attempts if a.get("stable_id") not in drop]
    removed = len(attempts) - len(kept)
    if removed:
        history["attempts"] = kept
        history["updated_at"] = now_iso()
        write_json(HISTORY, history)
    return removed


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

    # Zombie history: ids published in extraction-history but absent from the
    # registry (renamed-away or deleted). The registry is authority, so these are
    # gated AND purged — they were the root cause of "ghost published" items.
    zombies = history_zombie_ids({i["id"] for i in kept})

    for z in zombies:
        print(f"ZOMBIE    {z} (published in history, absent from registry)")

    if args.check:
        drift = len(dangling) + len(orphans) + len(zombies)
        desired_retrieval = retrieval_jsonl(kept)
        retrieval_stale = (
            not RETRIEVAL.exists()
            or RETRIEVAL.read_text(encoding="utf-8") != desired_retrieval
        )
        if retrieval_stale:
            print(f"STALE     {RETRIEVAL.relative_to(SYSTEM_ROOT.parent)}")
            drift += 1
        print(f"{'DRIFT' if drift else 'clean'}: {len(dangling)} dangling, "
              f"{len(orphans)} orphan, {len(zombies)} zombie, {len(kept)} valid items")
        return 1 if drift else 0

    if args.write:
        if dangling:
            registry["items"] = kept
            write_json(REGISTRY, registry)
        # Recompute zombies against the post-drop registry, then purge their
        # history records outright (dropping a dangling entry can create a new
        # zombie for that id).
        zombies = history_zombie_ids({i["id"] for i in kept})
        purged = purge_history(zombies)
        write_json(COMPACT, project_compact(kept))
        RETRIEVAL.write_text(retrieval_jsonl(kept), encoding="utf-8", newline="\n")
        print(f"wrote compact ({len(kept)} items); dropped {len(dangling)} dangling; "
              f"purged {purged} zombie history record(s); "
              f"{len(orphans)} orphan folder(s) left for review")
        return 0

    # default: report only
    print(f"{len(kept)} valid items, {len(dangling)} dangling, {len(orphans)} orphan "
          f"(use --write to apply, --check to gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
