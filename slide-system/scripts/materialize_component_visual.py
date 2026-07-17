#!/usr/bin/env python3
"""Materialize a component's visual.svg into a SELF-CONTAINED, job-local SVG.

A published component visual can reference external raster tiles
(e.g. xlink:href="assets/image-01.png"). A browser refuses to load those when
the SVG is embedded via `<img src>` (SVG "secure static" mode), so the artwork
renders blank. This script inlines every *local* image reference as a base64
data URI and writes the result into the JOB directory — the canonical library
asset is never modified. It is generic (works from any component's artifacts,
no hardcoded ids) and fails with a nonblank guard so a blank base cannot slip
into a generated deck.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path

from _common import load_json

HREF_RE = re.compile(
    r'(xlink:href|href)="([^"]+\.(?:png|jpe?g|gif|svg|webp))"', re.IGNORECASE)
DATA_URI_RE = re.compile(r'data:image/[^;]+;base64,[A-Za-z0-9+/]{100,}')
SHAPE_RE = re.compile(
    r'<(?:path|rect|circle|ellipse|polygon|polyline|line|image|use)\b', re.IGNORECASE)
_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
         "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp"}


def _visual_path(item_id: str, registry: str) -> Path:
    reg = load_json(registry)
    for entry in reg.get("items", []):
        if entry.get("id") == item_id:
            visual = (entry.get("paths") or {}).get("visual")
            if not visual:
                raise SystemExit(f"ERROR: item {item_id!r} has no paths.visual "
                                 f"(pass the full registry, not compact).")
            return Path(visual)
    raise SystemExit(f"ERROR: item_id {item_id!r} not found in {registry}")


def _classify_ref(ref: str, base_dir: Path, base_res: Path) -> tuple[str, Path | None]:
    """Classify ONE <image> href, the single source of truth materialization and the
    immutable-audit fingerprint share so they can never disagree on which files decide
    the render:
      - ('external', None) — a data: URI, http(s) URL, or #fragment: self-contained or
        not a local file, so it is neither inlined nor fingerprinted;
      - ('unsafe',   None) — an absolute path, a path escaping ``base_dir`` (path
        traversal), or a missing local file: refused (fail closed);
      - ('local',    Path) — a safe, existing local file under ``base_dir``.
    """
    if ref.startswith(("data:", "http:", "https:", "#")):
        return ("external", None)
    if os.path.isabs(ref) or ref.startswith(("/", "\\")):
        return ("unsafe", None)
    try:
        p_res = (base_dir / ref).resolve()
    except (OSError, RuntimeError, ValueError):
        return ("unsafe", None)
    if base_res != p_res and base_res not in p_res.parents:
        return ("unsafe", None)             # escapes base_dir
    if not p_res.exists():
        return ("unsafe", None)             # missing
    return ("local", p_res)


def image_dependencies(svg_text: str, base_dir: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    """Discover every local image the visual references, WITHOUT inlining. Returns
    (safe, unresolved): `safe` is the list of (ref, resolved-Path) files that
    materialization base64-inlines and that therefore decide the rendered background;
    `unresolved` is the list of refs that are missing/absolute/escaping (fail closed).
    Deterministic; shared by `inline_external_images` and `build_registry` so the audit
    fingerprint covers exactly the files the render consumes. External (data:/http/#)
    refs are neither — they are self-contained or not local files."""
    base_res = base_dir.resolve()
    safe: list[tuple[str, Path]] = []
    unresolved: list[str] = []
    for m in HREF_RE.finditer(svg_text):
        ref = m.group(2)
        kind, p = _classify_ref(ref, base_dir, base_res)
        if kind == "local":
            safe.append((ref, p))
        elif kind == "unsafe":
            unresolved.append(ref)
    return safe, unresolved


def inline_external_images(svg_text: str, base_dir: Path) -> tuple[str, list[str]]:
    """Return (self-contained svg, list of refs that could NOT be safely inlined).
    Local image refs are base64-inlined; data:/http/#fragment refs are left as-is.
    A ref is reported (and left unresolved) when it is missing, absolute, or
    escapes ``base_dir`` (path traversal) — the caller must treat a non-empty
    list as a hard failure rather than ship an incomplete visual. Uses the shared
    `_classify_ref` so the inlined set is exactly `image_dependencies(...)[0]`."""
    unresolved: list[str] = []
    base_res = base_dir.resolve()

    def repl(m: re.Match) -> str:
        attr, ref = m.group(1), m.group(2)
        kind, p_res = _classify_ref(ref, base_dir, base_res)
        if kind == "local":
            mime = _MIME.get(p_res.suffix.lstrip(".").lower(), "application/octet-stream")
            data = base64.b64encode(p_res.read_bytes()).decode()
            return f'{attr}="data:{mime};base64,{data}"'
        if kind == "unsafe":
            unresolved.append(ref)
        return m.group(0)                   # external or unsafe: left unchanged

    return HREF_RE.sub(repl, svg_text), unresolved


def is_nonblank(svg_text: str) -> bool:
    """A visual is non-blank if it carries embedded image data or real shapes."""
    return bool(DATA_URI_RE.search(svg_text)) or len(SHAPE_RE.findall(svg_text)) >= 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Materialize a self-contained job-local component visual.")
    src_group = ap.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--item-id", help="Registry id; resolves paths.visual.")
    src_group.add_argument("--svg", help="Path to the component visual.svg directly.")
    ap.add_argument("--registry",
                    default=str(Path(__file__).resolve().parents[1] / "registries/visual-library.json"))
    ap.add_argument("--out", required=True, help="Job-local output .svg path.")
    args = ap.parse_args(argv)

    src = Path(args.svg) if args.svg else _visual_path(args.item_id, args.registry)
    if not src.exists():
        print(f"ERROR: visual not found: {src}", file=sys.stderr)
        return 1

    svg_text = src.read_text(encoding="utf-8", errors="replace")
    out_svg, unresolved = inline_external_images(svg_text, src.parent)
    # Fail by default: a missing/unsafe/unresolved local ref means the visual
    # cannot be made self-contained. Refuse to write an incomplete "successful"
    # SVG that would render blank or leak an external dependency into the deck.
    if unresolved:
        print(f"ERROR: {len(unresolved)} unresolved/unsafe local image ref(s) next to "
              f"{src.name}; refusing to write an incomplete visual: {unresolved[:5]}",
              file=sys.stderr)
        return 1
    if not is_nonblank(out_svg):
        print(f"ERROR: materialized visual is blank (no embedded images or shapes): {src}",
              file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_svg, encoding="utf-8")
    print(f"materialize: {len(DATA_URI_RE.findall(out_svg))} embedded image(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
