#!/usr/bin/env python3
"""Validate visual registry IDs, paths, statuses, and contracts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import load_json, resolve_repo_path
from build_registry import immutable_text_drift, renders_as_slide


# Base ID is three dotted segments (family.type.slug). Materialized group items
# carry an optional `.gNN` suffix (g01, g02, …) minted by classify/publish, e.g.
# `sun.component.team-contributor-circles.g01`. Both must validate; malformed IDs
# (wrong segment count, uppercase, bad suffix like `.g` or `.gab`) must not.
ID_PATTERN = re.compile(r"^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+(\.g[0-9]+)?$")
VALID_STATUS = {"staging", "qa", "published", "deprecated", "rejected"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"),
    )
    parser.add_argument("--allow-missing-paths", action="store_true")
    args = parser.parse_args()

    registry = load_json(args.registry)
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
        # auto_reuse is optional (absent == eligible); when present it must carry a
        # boolean flag AND a human-readable reason, so an item can never be barred
        # from automatic reuse without an explanation the reviewer can read.
        auto = item.get("auto_reuse")
        if auto is not None:
            if not isinstance(auto, dict) or set(auto) - {"eligible", "reason"}:
                errors.append(f"auto_reuse for {item_id} must be an object with only "
                              f"'eligible' and 'reason'")
            elif not isinstance(auto.get("eligible"), bool) or not str(auto.get("reason") or "").strip():
                errors.append(f"auto_reuse for {item_id} needs eligible (boolean) and a "
                              f"non-empty reason")
        # build_scope is optional (absent == unreviewed == not auto-buildable; the item
        # stays published + manually selectable). When present it records the reviewed
        # buildability verdict and must carry a mode and a human-readable reason, so an
        # item can never be marked auto-buildable — or bench-marked source-specific —
        # without evidence a reviewer can read.
        bscope = item.get("build_scope")
        if bscope is not None:
            if not isinstance(bscope, dict) or set(bscope) - {"mode", "reason"}:
                errors.append(f"build_scope for {item_id} must be an object with only "
                              f"'mode' and 'reason'")
            elif bscope.get("mode") not in ("generic", "source-specific"):
                errors.append(f"build_scope.mode for {item_id} must be 'generic' or "
                              f"'source-specific'")
            elif not str(bscope.get("reason") or "").strip():
                errors.append(f"build_scope for {item_id} needs a non-empty reason "
                              f"grounded in the item's slot contract")
        # immutable_text is optional (absent == not audited; the item keeps its existing
        # behaviour). When present it records the audit verdict and must always carry a
        # human-readable reason, so a verdict can never be set without evidence a
        # reviewer can read. `terms` are required by — and only meaningful for — an
        # `immutable` verdict: they are what a request has to match.
        imm = item.get("immutable_text")
        if imm is not None:
            groups = imm.get("contexts")
            if not isinstance(imm, dict) or set(imm) - {"audit", "contexts", "evidence", "reason"}:
                errors.append(f"immutable_text for {item_id} must be an object with only "
                              f"'audit', 'contexts', 'evidence' and 'reason'")
            elif imm.get("audit") not in ("clean", "immutable", "unresolved"):
                errors.append(f"immutable_text.audit for {item_id} must be one of "
                              f"clean/immutable/unresolved")
            elif not str(imm.get("reason") or "").strip():
                errors.append(f"immutable_text for {item_id} needs a non-empty reason "
                              f"(the audit finding)")
            elif imm["audit"] == "immutable" and (
                    not isinstance(groups, list) or not groups
                    or any(not isinstance(g, list) or not g
                           or any(not isinstance(t, str) or not t.strip() for t in g)
                           for g in groups)):
                errors.append(f"immutable_text for {item_id} is audit=immutable, so it needs "
                              f"a non-empty 'contexts' list of non-empty term groups; every "
                              f"term in a group must match for automatic reuse")
            elif imm["audit"] != "immutable" and groups:
                errors.append(f"immutable_text for {item_id} is audit={imm['audit']}, which "
                              f"must not declare 'contexts' (nothing to match against)")
            else:
                # The verdict is only as good as the artifact it was taken from: an
                # audit with no fingerprint cannot be re-checked, and one whose hashes
                # no longer match the files describes an artifact that no longer exists.
                # Both are projected as `unresolved` by build_registry (fail closed);
                # surface them here so the drift is visible before a build.
                ev = imm.get("evidence")
                if ev is None and renders_as_slide(item):
                    errors.append(f"immutable_text for {item_id} records no 'evidence' "
                                  f"fingerprint, so the verdict cannot be bound to the "
                                  f"artifact it was taken from; re-run audit_immutable_text.py")
                elif ev is None:
                    pass  # no artifact file at all (a directory): nothing to fingerprint
                elif not isinstance(ev, dict) or set(ev) - {"visual_sha256", "slots_sha256",
                                                            "preview_sha256", "deps_sha256"}:
                    errors.append(f"immutable_text.evidence for {item_id} must be an object "
                                  f"with only 'visual_sha256', 'slots_sha256', "
                                  f"'preview_sha256' and 'deps_sha256'")
                else:
                    drift = immutable_text_drift(item)
                    if drift:
                        errors.append(f"immutable_text for {item_id} is stale: {drift}. "
                                      f"Automatic reuse fails closed until it is re-audited.")
        for key in ("artifact", "preview"):
            value = item.get("paths", {}).get(key)
            if not value or args.allow_missing_paths:
                continue
            if not resolve_repo_path(value).exists():
                errors.append(f"Missing {key} path for {item_id}: {value}")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"Valid registry: {len(ids)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

