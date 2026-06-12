#!/usr/bin/env python3
"""Remove empty directories left behind by abandoned scaffolding.

LLM sessions tend to `mkdir -p` whole folder trees ahead of content; whatever
stays empty is noise, never output. `package_job.py` prunes each slide run
automatically — use this CLI for ad-hoc sweeps over any output tree:

    python3 slide-system/scripts/prune_empty_dirs.py outputs/
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import prune_empty_dirs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory tree to sweep")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"not a directory: {args.root}")
    removed = prune_empty_dirs(args.root)
    for path in removed:
        print(f"removed {path}")
    print(f"Pruned {len(removed)} empty director{'y' if len(removed) == 1 else 'ies'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
