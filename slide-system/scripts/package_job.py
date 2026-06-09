#!/usr/bin/env python3
"""Create a checksum manifest for one completed slide run."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import now_iso, sha256_file, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory does not exist: {run_dir}")
    output = Path(args.output).resolve() if args.output else run_dir / "reports/delivery-manifest.json"
    files = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.resolve() == output:
            continue
        files.append(
            {
                "path": str(path.relative_to(run_dir)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "packaged_at": now_iso(),
        "run_dir": str(run_dir),
        "file_count": len(files),
        "files": files,
    }
    write_json(output, manifest)
    print(f"Packaged {len(files)} files into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

