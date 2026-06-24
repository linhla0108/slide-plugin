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
    Dropping one ALSO appends a corrective `unpublished` record to
    extraction-history.json (see reconcile_history): the history log is
    append-only and previously kept claiming `published` for an item the
    registry had silently dropped, which is the root cause of "ghost published"
    zombies (published in history, absent from registry + disk). Reconciling on
    drop keeps history, registry, and disk from diverging at the one point where
    they used to.
  * ORPHAN  — a library folder containing `visual.svg` that no entry references.
    Reported, never auto-deleted: deletion is an explicit, separate action, and
    an orphan usually means "publish it" or "register it", not "destroy it".
  * COMPACT — `visual-library-compact.json` (what `score_visual_items.py` reads)
    is regenerated as a deterministic projection of the full registry, so it can
    never drift from it and is never hand-maintained.

    python3 slide-system/scripts/build_registry.py --check   # gate: exit 1 on drift
    python3 slide-system/scripts/build_registry.py --write    # drop dangling + reconcile history + rebuild compact
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import load_json, now_iso, resolve_repo_path

SYSTEM_ROOT = Path(__file__).resolve().parents[1]
LIBRARY = SYSTEM_ROOT / "library"
REGISTRY = SYSTEM_ROOT / "registries/visual-library.json"
COMPACT = SYSTEM_ROOT / "registries/visual-library-compact.json"
HISTORY = SYSTEM_ROOT / "registries/extraction-history.json"

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


def history_published_not_in_registry(registry_ids: set[str]) -> list[str]:
    """stable_ids whose LATEST extraction-history status is `published` but
    which are absent from the registry. This is a superset: it includes both
    genuine ghosts (folder gone) AND items republished under a renamed
    canonical id (the content is published, just under a different id). It is
    reported for observability but never auto-corrected in bulk — only the
    precise set dropped by THIS reconcile run is corrected (reconcile_history)."""
    if not HISTORY.exists():
        return []
    latest: dict[str, str] = {}
    for attempt in load_json(HISTORY).get("attempts", []):
        sid = attempt.get("stable_id")
        if sid:
            latest[sid] = attempt.get("status")
    return sorted(sid for sid, status in latest.items()
                  if status == "published" and sid not in registry_ids)


def reconcile_history(dropped_ids: list[str]) -> int:
    """Append a corrective `unpublished` record to extraction-history.json for
    each dropped dangling id whose latest history status still claims
    `published`. Append-only: past events are never rewritten, so the audit
    trail stays intact while stopping the log from lying about current state.
    Returns the count of records appended (0 if nothing needed correcting)."""
    if not dropped_ids or not HISTORY.exists():
        return 0
    history = load_json(HISTORY)
    attempts = history.setdefault("attempts", [])
    latest: dict[str, str] = {}
    for attempt in attempts:
        sid = attempt.get("stable_id")
        if sid:
            latest[sid] = attempt.get("status")
    appended = 0
    for sid in dropped_ids:
        if latest.get(sid) == "published":
            attempts.append({
                "attempted_at": now_iso(),
                "stable_id": sid,
                "status": "unpublished",
                "reason": "dangling artifact folder missing; dropped from "
                          "visual-library.json by build_registry --write",
            })
            appended += 1
    if appended:
        history["updated_at"] = now_iso()
        HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")
    return appended


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

    # History/registry drift: history-published ids absent from the registry.
    # Informational only — it conflates genuine ghosts with renamed-id republishes
    # and must not gate, but it makes the divergence visible instead of silent.
    ghosts = history_published_not_in_registry({i["id"] for i in kept})

    if args.check:
        drift = len(dangling) + len(orphans)
        print(f"{'DRIFT' if drift else 'clean'}: {len(dangling)} dangling, "
              f"{len(orphans)} orphan, {len(kept)} valid items")
        if ghosts:
            print(f"note: {len(ghosts)} history-published id(s) not in registry "
                  f"(ghosts and/or renamed-id republishes; not gated)")
        return 1 if drift else 0

    if args.write:
        reconciled = 0
        if dangling:
            registry["items"] = kept
            REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
            reconciled = reconcile_history([i["id"] for i in dangling])
        # Also reconcile ghost-published items: extraction-history says
        # "published" but the item is completely absent from the registry
        # (not even dangling). These are zombies from earlier runs where
        # extraction-history was updated but the registry entry was never
        # created or was already dropped by a previous reconcile.
        if ghosts:
            reconciled += reconcile_history(ghosts)
        COMPACT.write_text(json.dumps(project_compact(kept), ensure_ascii=False, indent=2) + "\n")
        print(f"wrote compact ({len(kept)} items); dropped {len(dangling)} dangling; "
              f"reconciled {reconciled} history record(s) to unpublished; "
              f"{len(orphans)} orphan folder(s) left for review")
        return 0

    # default: report only
    print(f"{len(kept)} valid items, {len(dangling)} dangling, {len(orphans)} orphan "
          f"(use --write to apply, --check to gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
