#!/usr/bin/env python3
"""Fail a deck before capture when its local visual assets cannot load."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from _common import write_json


ASSET_RE = re.compile(r'''(?:\bsrc\s*=\s*["']|\b(?:href|poster)\s*=\s*["']|url\(\s*["']?)([^"')\s]+)''', re.I)
IGNORED_PREFIXES = ("data:", "http:", "https:", "#", "javascript:", "blob:")


def _resolve(raw: str, root: Path) -> Path | None:
    value = raw.strip()
    if not value or value.lower().startswith(IGNORED_PREFIXES):
        return None
    if value.lower().startswith("file:"):
        parsed = urlparse(value)
        return Path(unquote(parsed.path.lstrip("/")))
    return root / value.split("?", 1)[0].split("#", 1)[0]


def missing_local_assets(html_path: Path) -> list[str]:
    text = html_path.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    for raw in ASSET_RE.findall(text):
        target = _resolve(raw, html_path.parent)
        if target is not None and not target.is_file() and raw not in missing:
            missing.append(raw)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local assets referenced by a deck HTML file.")
    parser.add_argument("--html", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    html = Path(args.html).resolve()
    if not html.is_file():
        print(f"ERROR: HTML not found: {html}", file=sys.stderr)
        return 1
    missing = missing_local_assets(html)
    payload = {"valid": not missing, "html": str(html), "missing": missing}
    if args.out:
        write_json(args.out, payload)
    if missing:
        for item in missing:
            print(f"ERROR: missing local deck asset: {item}", file=sys.stderr)
        return 1
    print("deck-assets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
