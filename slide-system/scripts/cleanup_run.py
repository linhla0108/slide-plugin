#!/usr/bin/env python3
"""Clean up intermediate files from a finished slide run."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


KEEP_PATTERNS = {
    "deck.html",
    "*.pptx",
}

KEEP_DIRS = {"analysis"}

DELETE_DIRS = [
    "parity",
    "qa/export-renders",
]

DELETE_PATTERNS = [
    "slide-*-bg.png",
    "slide-*-ov-*.png",
    "slide-*-capture.png",
    "delivery-manifest.json",
    "export-result.json",
    "validation.json",
]


def cleanup(run_dir: Path, dry_run: bool = False) -> list[str]:
    removed: list[str] = []

    for d in DELETE_DIRS:
        target = run_dir / d
        if target.is_dir():
            if dry_run:
                count = sum(1 for _ in target.rglob("*") if _.is_file())
                removed.append(f"[dir] {target.relative_to(run_dir)} ({count} files)")
            else:
                count = sum(1 for _ in target.rglob("*") if _.is_file())
                shutil.rmtree(target)
                removed.append(f"[dir] {target.relative_to(run_dir)} ({count} files)")

    for pattern in DELETE_PATTERNS:
        for f in run_dir.glob(pattern):
            if f.is_file():
                removed.append(f"[file] {f.relative_to(run_dir)}")
                if not dry_run:
                    f.unlink()

    for f in run_dir.rglob("*.png"):
        rel = f.relative_to(run_dir)
        parts = rel.parts
        if parts[0] in KEEP_DIRS:
            continue
        if any(f.match(p) for p in KEEP_PATTERNS):
            continue
        removed.append(f"[file] {rel}")
        if not dry_run:
            f.unlink()

    for d in sorted(run_dir.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            removed.append(f"[empty] {d.relative_to(run_dir)}")
            if not dry_run:
                d.rmdir()

    manifest = run_dir / "export-manifest.json"
    if manifest.exists() and manifest.stat().st_size > 20_000:
        import json
        data = json.loads(manifest.read_text())
        for slide in data.get("slides", []):
            slide.pop("parity", None)
            slide.pop("checksums", None)
            for obj in slide.get("objects", []):
                obj.pop("pixel_stats", None)
        compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if not dry_run:
            manifest.write_text(compact)
        saved = manifest.stat().st_size - len(compact)
        if saved > 0:
            removed.append(f"[compact] export-manifest.json (saved {saved//1024}KB)")

    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up intermediate files from a slide run.")
    parser.add_argument("run_dir", help="Path to the run directory.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"ERROR: {run_dir} is not a directory", file=sys.stderr)
        return 1

    removed = cleanup(run_dir, dry_run=args.dry_run)
    mode = "DRY RUN" if args.dry_run else "CLEANED"
    print(f"{mode}: {len(removed)} item(s) from {run_dir.name}")
    for r in removed:
        print(f"  {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
