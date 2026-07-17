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
    never drift from it and is never hand-maintained. --check compares the
    on-disk compact against a freshly recomputed projection and fails on any
    mismatch, so a backfill that updates the full registry but forgets to
    regenerate compact can no longer pass the gate.

    python3 slide-system/scripts/build_registry.py --check   # gate: exit 1 on drift
    python3 slide-system/scripts/build_registry.py --write    # drop dangling + purge zombie history + rebuild compact
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from _common import load_json, now_iso, resolve_repo_path, sha256_file, write_json
import build_component_retrieval_index as retrieval
import materialize_component_visual as materialize

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
    "density", "content_structure", "limitations", "auto_reuse", "immutable_text",
    "build_scope",
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


# Every `paths.*` file whose bytes decide what the generated scaffold/render shows,
# paired with the fingerprint key it contributes. This is the ONE place that answers
# "which files decide the render", so the audit cannot fingerprint a different set than
# the scaffold reads. `scaffold_slide_from_component.py` reads all three at build time:
#   - `visual`     -> the `.bg` background artwork (materialize_component_visual);
#   - `preview`    -> preview.html, the source of the `.slot` markup AND geometry a
#                     TEMPLATE renders from (omitting it was the reported bypass: editing
#                     preview.html moved slots while the fingerprint stayed identical);
#   - `text_slots` -> the editable-slot contract (fallback geometry + font scale).
# A raster-only asset (no `visual`) carries its artwork in `preview`, so hashing the
# same fields still binds it correctly. Order is fixed so the projection is stable.
RENDER_INPUT_FIELDS: tuple[tuple[str, str], ...] = (
    ("visual", "visual_sha256"),
    ("preview", "preview_sha256"),
    ("text_slots", "slots_sha256"),
)


def render_input_files(item: dict) -> list[tuple[str, Path]]:
    """The render-input FILES this item declares that exist on disk, as
    (fingerprint_key, path). A `paths.*` that is missing or is a directory (Dio's
    character-art folder) contributes nothing — content only, no mtimes, no machine
    paths, so the same bytes fingerprint the same in any checkout."""
    paths = item.get("paths") or {}
    out: list[tuple[str, Path]] = []
    for key, field in RENDER_INPUT_FIELDS:
        value = paths.get(key)
        if not value:
            continue
        target = resolve_repo_path(value)
        if target.is_file():
            out.append((field, target))
    return out


def visual_dependencies(item: dict) -> tuple[list[tuple[str, Path]], list[str]]:
    """The local image files this item's `visual.svg` references — which
    `materialize_component_visual` base64-inlines into the rendered background, so they
    decide the render as much as visual.svg itself. Returns (safe, unresolved) using the
    SAME classifier materialization uses, so the audit and the render can never disagree
    on which references are safe/local/resolved. Empty when the item declares no visual
    file (raster-preview assets, Dio)."""
    visual = (item.get("paths") or {}).get("visual")
    if not visual:
        return [], []
    target = resolve_repo_path(visual)
    if not target.is_file():
        return [], []          # a missing visual is already a finding via visual_sha256
    svg = target.read_text(encoding="utf-8", errors="replace")
    return materialize.image_dependencies(svg, target.parent)


def _visual_dependency_fingerprint(item: dict) -> str | None:
    """A single stable aggregate over the SAFE local image dependencies of visual.svg:
    sha256 of sorted `<reference-identity>\\t<content-hash>` lines. The identity is the
    reference string as written in the SVG (repo-relative to the component), so the
    aggregate is content-only and machine-independent — no mtimes, no absolute paths.
    None when there are no safe dependencies. Unsafe/missing references are handled by
    `gate_immutable_text` (fail closed), not silently folded in here."""
    safe, _unresolved = visual_dependencies(item)
    if not safe:
        return None
    lines = sorted(f"{ref}\t{sha256_file(path)}" for ref, path in safe)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def immutable_text_fingerprint(item: dict) -> dict:
    """Content hashes of every file that decides what the empty-slot render shows —
    `visual.svg`, `preview.html`, `text-slots.json` (see `RENDER_INPUT_FIELDS`), PLUS a
    `deps_sha256` aggregate over the local image files visual.svg references and
    materialization inlines into the background. Binding the verdict to ALL of them means
    changing any one — including a referenced tile.png — invalidates the audit, so no
    render input can be edited past the gate."""
    out = {field: sha256_file(target) for field, target in render_input_files(item)}
    deps = _visual_dependency_fingerprint(item)
    if deps:
        out["deps_sha256"] = deps
    return out


def renders_as_slide(item: dict) -> bool:
    """Whether this item DECLARES artwork a verdict must be bound to — i.e. whether the
    audit gate applies. Deliberately about what the item claims, not about what is on
    disk right now: an item whose declared `visual` has gone missing is unverifiable,
    which is a finding, not an exemption (`immutable_text_fingerprint` returns {} in
    both cases, so testing the hash instead would silently exempt deleted artwork).

    False only for an item that can never name an artifact file: Dio's paths point at a
    DIRECTORY of character art, so there is nothing to hash and it cannot be scaffolded
    into a slide (audit_immutable_text.py records it `not-applicable`). It can bake no
    slide text, so demanding a fingerprint it can never produce would strand it as
    permanently `unresolved`. The moment it names a real file, the gate applies.

    Note the exemption is "names a directory", not "the file is absent" — a declared
    artifact that has gone missing is unverifiable, and must fail closed."""
    paths = item.get("paths") or {}
    if paths.get("visual"):
        return True
    preview = paths.get("preview")
    if not preview:
        return False
    return not resolve_repo_path(preview).is_dir()


def immutable_text_drift(item: dict) -> str | None:
    """Why this item's recorded audit no longer describes its artifact, or None.

    An audit verdict is evidence about ONE version of the artwork. A re-extraction
    that replaces visual.svg — or a change to which slots are editable — can turn a
    `clean` item into one that ships a baked lockup, while the stale verdict still
    says it is safe. Comparing the recorded fingerprint against the files on disk is
    what stops that."""
    imm = item.get("immutable_text") or {}
    recorded = imm.get("evidence")
    if not recorded:
        return None  # handled by the caller: no fingerprint at all is its own finding
    current = immutable_text_fingerprint(item)
    for field in ("visual_sha256", "slots_sha256", "preview_sha256", "deps_sha256"):
        was, now = recorded.get(field), current.get(field)
        if was == now:
            continue
        if now is None:
            return f"{field} was audited but the artifact file is missing now"
        if was is None:
            return f"{field} is not covered by the recorded audit evidence"
        return f"{field} changed since the audit ({was[:12]}… -> {now[:12]}…)"
    return None


def gate_immutable_text(item: dict) -> dict | None:
    """The `immutable_text` a PUBLISHED item projects into the compact registry — the
    file `score_visual_items.py` actually reads. Fails closed, so an item can only be
    automatically reused while its audit genuinely describes the artifact on disk:

      - never audited            -> unresolved (a newly published or re-extracted item
                                    cannot silently become automatically reusable);
      - audited without evidence -> unresolved (the verdict cannot be re-checked);
      - fingerprint drifted      -> unresolved (the verdict describes older artwork).

    Anything else passes through untouched. Unpublished items are left alone: they are
    not selectable anyway, and Draft/publish semantics are not this gate's business."""
    imm = item.get("immutable_text")
    if item.get("status") != "published":
        return imm
    # A visual that references a local image dependency which is missing or unsafe
    # cannot be materialized into a slide at all (materialization refuses it), so no
    # verdict about its render can hold — fail closed regardless of what was recorded.
    _safe, unresolved = visual_dependencies(item)
    if unresolved:
        return {"audit": "unresolved", "reason": (
            f"visual.svg references {len(unresolved)} local image dependency(ies) that are "
            f"missing or unsafe ({unresolved[:3]}); the component cannot be materialized, so "
            "its render — and any verdict about it — is invalid. Fix the reference and "
            "re-run audit_immutable_text.py.")}
    if not imm:
        return {"audit": "unresolved", "reason": (
            "No immutable-text audit recorded for this published item. Automatic reuse "
            "fails closed until slide-system/scripts/audit_immutable_text.py has rendered "
            "it with every slot empty and a human has classified the result.")}
    if not imm.get("evidence") and renders_as_slide(item):
        return {"audit": "unresolved", "reason": (
            "The immutable-text audit recorded no artifact fingerprint, so the verdict "
            f"cannot be bound to the artwork on disk (recorded: {imm.get('audit')!r}). "
            "Re-run audit_immutable_text.py.")}
    drift = immutable_text_drift(item)
    if drift:
        return {"audit": "unresolved", "reason": (
            f"The immutable-text audit is stale — {drift} — so the recorded verdict "
            f"({imm.get('audit')!r}) describes artwork that is no longer there. "
            "Re-run audit_immutable_text.py.")}
    return imm


def project_compact(items: list[dict]) -> dict:
    out = []
    for item in items:
        row = {k: item.get(k) for k in COMPACT_KEYS}
        row["immutable_text"] = gate_immutable_text(item)
        out.append(row)
    return {"items": out}


def compact_text(items: list[dict]) -> str:
    """Serialize the compact projection exactly as `write_json` writes it, so a
    text comparison in --check is faithful to what --write would produce."""
    return json.dumps(project_compact(items), ensure_ascii=True, indent=2) + "\n"


def _rel(path: Path) -> str:
    """Repo-relative display path, falling back to the raw path when the target
    lives outside the repo (e.g. a temp registry under test)."""
    try:
        return str(path.relative_to(SYSTEM_ROOT.parent))
    except ValueError:
        return str(path)


def retrieval_jsonl(items: list[dict]) -> str:
    records = retrieval.build_records({"items": items})
    return "".join(
        json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n"
        for record in records
    )


def live_registry_items() -> list[dict]:
    """The full registry minus DANGLING entries — exactly the set the generated
    projections are built from, so a freshness comparison against them is faithful."""
    return [
        item for item in load_json(REGISTRY).get("items", [])
        if not (item.get("paths", {}).get("artifact")
                and not resolve_repo_path(item["paths"]["artifact"]).exists())
    ]


def generated_projection_staleness(items: list[dict] | None = None) -> list[str]:
    """Why the GENERATED projections no longer describe the registry and the artifact
    bytes on disk. Empty list = fresh.

    This is the single freshness predicate: `--check` reports it and the scorer
    refuses to score on it, so a stale projection cannot be caught in one place and
    missed in the other. It needs no fingerprint logic of its own — recomputing the
    projection runs `gate_immutable_text`, which re-hashes every artifact, so a
    visual.svg that changed AFTER the projection was built shows up here as compact
    drift (that item now projects `unresolved`, the on-disk copy still says `clean`)."""
    if items is None:
        items = live_registry_items()
    stale: list[str] = []
    if not COMPACT.exists() or COMPACT.read_text(encoding="utf-8") != compact_text(items):
        stale.append(f"{_rel(COMPACT)} (compact projection out of date)")
    if not RETRIEVAL.exists() or RETRIEVAL.read_text(encoding="utf-8") != retrieval_jsonl(items):
        stale.append(f"{_rel(RETRIEVAL)} (retrieval index out of date)")
    return stale


# What an operator must run to regenerate the projections. Kept here so the scorer's
# refusal and this tool's own reports name the same command.
REFRESH_HINT = "python slide-system/scripts/build_registry.py --write"


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
        # Generated-projection drift — the scorer reads visual-library-compact.json, so
        # a full registry edit (e.g. a metadata backfill) that forgets to regenerate the
        # projection, or an artifact that changed since it was built, would otherwise
        # leave the scorer on stale metadata. Same predicate the scorer preflights on.
        for stale in generated_projection_staleness(kept):
            print(f"STALE     {stale} — run --write")
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
