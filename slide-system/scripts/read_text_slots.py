#!/usr/bin/env python3
"""Emit a slim projection of a library item's text-slots.json.

The full contract carries 15 fields per slot (up to ~120 KB / 97 slots) — an
HTML builder only needs id/role/html_tag/example_value/bounds. This keeps the
heavy file on disk (the export/contract stack still reads it in full) while the
orchestrating agent consumes a ~15 KB projection. See SKILL.md Prohibition #5.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import load_json

SLIM_FIELDS = ("id", "role", "html_tag", "example_value", "bounds")


def _resolve_slots_path(item: str | None, item_id: str | None, registry: str) -> Path:
    if item:
        p = Path(item)
        # Accept either the item directory or the text-slots.json itself.
        return p if p.is_file() else p / "text-slots.json"
    if not item_id:
        raise SystemExit("ERROR: pass --item <library-path> or --item-id <id>")
    reg = load_json(registry)
    for entry in reg.get("items", []):
        if entry.get("id") == item_id:
            ts = (entry.get("paths") or {}).get("text_slots")
            if not ts:
                raise SystemExit(f"ERROR: item {item_id!r} has no paths.text_slots "
                                 f"(pass the full registry, not compact)")
            return Path(ts)
    raise SystemExit(f"ERROR: item_id {item_id!r} not found in {registry}")


def project(slots: list[dict], with_typography: bool) -> list[dict]:
    out = []
    for s in slots:
        slim = {k: s.get(k) for k in SLIM_FIELDS}
        if with_typography:
            slim["typography"] = s.get("typography")
        out.append(slim)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Slim projection of a library item's text-slots.json.")
    ap.add_argument("--item", default=None, help="Library item directory (or text-slots.json path).")
    ap.add_argument("--item-id", default=None, help="Registry item id (resolved via --registry).")
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--slots-only", action="store_true",
                    help="Emit only the slim slot array (no top-level metadata).")
    ap.add_argument("--with-typography", action="store_true",
                    help="Include the typography object per slot (~2x larger).")
    ap.add_argument("--out", default=None, help="Write to file instead of stdout.")
    args = ap.parse_args()

    path = _resolve_slots_path(args.item, args.item_id, args.registry)
    if not path.exists():
        print(f"ERROR: text-slots file not found: {path}", file=sys.stderr)
        return 1

    data = load_json(path)
    slots = data.get("slots", []) if isinstance(data, dict) else data
    slim = project(slots, args.with_typography)

    if args.slots_only:
        payload: object = slim
    else:
        payload = {
            "source": str(path),
            "slot_count": len(slim),
            "coordinate_space": data.get("coordinate_space") if isinstance(data, dict) else None,
            "slots": slim,
        }

    # --slots-only is for agent consumption: emit compact JSON to minimize tokens.
    text = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if args.slots_only else json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"read_text_slots: {len(slim)} slot(s) -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
