#!/usr/bin/env python3
"""Flatten the fragmented background raster stack of visual.svg into one PNG.

PDF sources often paint the slide background as dozens of thin raster strips
(plus duplicate passes and soft-mask overlays). PyMuPDF reproduces that
faithfully, so `artifact/visual.svg` ends up referencing 30+ asset files that
are all one visual background. Per `slide-system/rules/background-rendering.md`
that stack should be a single `base-background` PNG.

This step finds the LEADING run of paint-order elements that draw only
`<image>` content (groups, clips, and masks allowed), renders exactly that run
to `artifact/assets/background-<hash>.png` with Chromium (mask/clip aware),
and replaces the run with one full-canvas `<image>`. Vector foreground decor
that follows the stack is left untouched, and the evidence SVG keeps the
original fragmented record.

Safety gate: the rewritten visual.svg is rendered and pixel-diffed against the
original render. Items that exceed the diff budget are restored unchanged.

    python3 slide-system/scripts/flatten_svg_background.py --batch <batch-dir>

Requires Playwright Chromium (slide-system/scripts/setup.sh) and Pillow.
After a flatten, rerun externalize_svg_images.py to refresh the per-item
external-image manifests, then optimize/validate as usual.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


TAG = re.compile(r"<(?P<close>/?)(?P<name>[a-zA-Z][\w:.-]*)(?:\"[^\"]*\"|'[^']*'|[^>\"'])*>")
ROOT_SIZE = re.compile(r"<svg\b[^>]*?\bwidth=\"(?P<w>[\d.]+)\"[^>]*?\bheight=\"(?P<h>[\d.]+)\"")
DEF_ID = re.compile(r"\bid=\"(?P<id>[^\"]+)\"")
DRAWING_TAGS = {
    "image", "path", "rect", "circle", "ellipse", "line",
    "polyline", "polygon", "text", "tspan", "use", "foreignObject",
}
RENDER_JS = Path(__file__).with_name("render_svg.js")


@dataclass
class Chunk:
    text: str
    drawing_tags: set[str] = field(default_factory=set)
    image_refs: int = 0

    @property
    def raster_only(self) -> bool:
        return bool(self.drawing_tags) and self.drawing_tags <= {"image"}


def top_level_chunks(body: str) -> list[Chunk] | None:
    """Split markup into balanced top-level element chunks."""
    chunks: list[Chunk] = []
    depth = 0
    start = None
    current_tags: set[str] = set()
    current_images = 0
    for match in TAG.finditer(body):
        name = match.group("name")
        is_close = bool(match.group("close"))
        is_selfclose = match.group(0).endswith("/>")
        if depth == 0 and not is_close:
            start = match.start()
            current_tags = set()
            current_images = 0
        if name in DRAWING_TAGS and not is_close:
            current_tags.add(name)
            if name == "image":
                current_images += 1
        if is_close:
            depth -= 1
        elif not is_selfclose:
            depth += 1
        if depth < 0:
            return None
        if depth == 0 and start is not None:
            chunks.append(Chunk(body[start:match.end()], current_tags, current_images))
            start = None
    if depth != 0:
        return None
    return chunks


def peel_wrappers(body: str) -> tuple[list[str], list[Chunk], list[str]] | None:
    """Descend through lone <g> wrappers until siblings appear.

    PyMuPDF nests page content inside a few full-page clip groups; the strip
    stack and the vector foreground only become siblings a few levels down.
    Wrappers carrying a transform are rejected (a full-canvas replacement
    image would be remapped by them).
    """
    wrappers_open: list[str] = []
    wrappers_close: list[str] = []
    while True:
        chunks = top_level_chunks(body)
        if chunks is None:
            return None
        if len(chunks) == 1 and not chunks[0].raster_only:
            text = chunks[0].text.strip()
            first = TAG.search(text)
            if (
                first
                and first.group("name") == "g"
                and not first.group(0).endswith("/>")
                and "transform=" not in first.group(0)
                and text.endswith("</g>")
            ):
                wrappers_open.append(first.group(0))
                wrappers_close.insert(0, "</g>")
                body = text[first.end(): -len("</g>")]
                continue
        return wrappers_open, chunks, wrappers_close


def prune_unused_defs(head: str, rest: str) -> str:
    """Drop defs children whose ids are never referenced by the document."""
    defs_match = re.search(r"<defs>(?P<inner>.*)</defs>", head, re.DOTALL)
    if not defs_match:
        return head
    inner_chunks = top_level_chunks(defs_match.group("inner"))
    if inner_chunks is None:
        return head
    while True:
        doc = head + rest
        referenced = set(re.findall(r"url\(#([^)]+)\)", doc))
        referenced |= set(re.findall(r"href=\"#([^\"]+)\"", doc))
        kept: list[Chunk] = []
        dropped = False
        for chunk in inner_chunks:
            id_match = DEF_ID.search(chunk.text)
            if id_match and id_match.group("id") not in referenced:
                # The id must be the element's own id (first tag), not a nested one.
                first_tag = TAG.search(chunk.text)
                if first_tag and id_match.start() < first_tag.end():
                    dropped = True
                    continue
            kept.append(chunk)
        inner_chunks = kept
        new_inner = "\n" + "\n".join(chunk.text for chunk in inner_chunks) + "\n"
        head = head[: defs_match.start()] + "<defs>" + new_inner + "</defs>" + head[defs_match.end():]
        defs_match = re.search(r"<defs>(?P<inner>.*)</defs>", head, re.DOTALL)
        if not dropped:
            return head


def render_jobs(jobs: list[dict[str, object]]) -> None:
    if not jobs:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(jobs, handle)
        jobs_path = handle.name
    try:
        subprocess.run(
            ["node", str(RENDER_JS), "--jobs", jobs_path],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"render_svg.js failed:\n{error.stderr}")
    finally:
        Path(jobs_path).unlink(missing_ok=True)


def diff_metrics(reference: Path, candidate: Path, threshold: int = 24) -> tuple[float, float]:
    from PIL import Image, ImageChops, ImageStat

    ref = Image.open(reference).convert("RGB")
    cand = Image.open(candidate).convert("RGB")
    if ref.size != cand.size:
        return 255.0, 1.0
    diff = ImageChops.difference(ref, cand)
    mean_error = sum(ImageStat.Stat(diff).mean) / 3
    changed = sum(max(pixel) > threshold for pixel in diff.get_flattened_data())
    return mean_error, changed / (ref.width * ref.height)


@dataclass
class Plan:
    item_dir: Path
    visual: Path
    head: str
    wrappers_open: list[str]
    wrappers_close: list[str]
    background_chunks: list[Chunk]
    rest_chunks: list[Chunk]
    width: int
    height: int
    work_dir: Path
    bg_render: Path = Path()
    orig_render: Path = Path()
    new_render: Path = Path()
    new_svg: Path = Path()


def prepare(item_dir: Path, work_root: Path, min_images: int) -> Plan | str:
    visual = item_dir / "artifact" / "visual.svg"
    if not visual.exists():
        return "no visual.svg"
    source = visual.read_text(encoding="utf-8")
    if source.count("<image") <= 1:
        return "already flat"

    size = ROOT_SIZE.search(source)
    if not size:
        return "no explicit width/height on <svg>"
    width, height = round(float(size.group("w"))), round(float(size.group("h")))

    defs_end = source.find("</defs>")
    head_end = defs_end + len("</defs>") if defs_end != -1 else TAG.search(source[5:]).end() + 5
    tail_start = source.rfind("</svg>")
    head, body = source[:head_end], source[head_end:tail_start]

    peeled = peel_wrappers(body)
    if peeled is None:
        return "unbalanced markup"
    wrappers_open, chunks, wrappers_close = peeled
    background: list[Chunk] = []
    for chunk in chunks:
        if chunk.raster_only:
            background.append(chunk)
        else:
            break
    image_count = sum(chunk.image_refs for chunk in background)
    if image_count < min_images:
        return f"leading raster stack too small ({image_count} image refs)"

    work_dir = work_root / item_dir.name
    work_dir.mkdir(parents=True)
    plan = Plan(item_dir, visual, head, wrappers_open, wrappers_close,
                background, chunks[len(background):], width, height, work_dir)

    # The stack-only SVG must live next to visual.svg so assets/ refs resolve.
    bg_svg = item_dir / "artifact" / ".flatten-bg.svg"
    bg_svg.write_text(
        head
        + "\n" + "\n".join(wrappers_open)
        + "\n" + "\n".join(chunk.text for chunk in background)
        + "\n" + "\n".join(wrappers_close)
        + "\n</svg>\n",
        encoding="utf-8",
    )
    plan.bg_render = work_dir / "background.png"
    plan.orig_render = work_dir / "original.png"
    return plan


def rewrite(plan: Plan) -> None:
    digest = hashlib.sha256(plan.bg_render.read_bytes()).hexdigest()
    asset_name = f"background-{digest[:12]}.png"
    assets_dir = plan.item_dir / "artifact" / "assets"
    assets_dir.mkdir(exist_ok=True)
    asset_path = assets_dir / asset_name
    if not asset_path.exists():
        asset_path.write_bytes(plan.bg_render.read_bytes())

    background_ref = (
        f'<image x="0" y="0" width="{plan.width}" height="{plan.height}" '
        f'xlink:href="assets/{asset_name}" />'
    )
    rest = (
        "\n" + "\n".join(plan.wrappers_open)
        + "\n" + background_ref
        + "\n" + "\n".join(c.text for c in plan.rest_chunks)
        + "\n" + "\n".join(plan.wrappers_close)
        + "\n</svg>\n"
    )
    head = prune_unused_defs(plan.head, rest)

    plan.new_svg = plan.item_dir / "artifact" / ".flatten-new.svg"
    plan.new_svg.write_text(head + rest, encoding="utf-8")
    plan.new_render = plan.work_dir / "flattened.png"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=Path, help="Extraction batch directory")
    parser.add_argument("--min-images", type=int, default=3,
                        help="Minimum image refs in the leading stack to bother flattening")
    parser.add_argument("--max-mean-error", type=float, default=0.5,
                        help="QA gate: max mean absolute pixel error vs original render")
    parser.add_argument("--max-changed-ratio", type=float, default=0.001,
                        help="QA gate: max ratio of pixels differing by more than 24")
    args = parser.parse_args()
    batch = args.batch.resolve()
    if not (batch / "items").is_dir():
        parser.error(f"{batch} has no items/ — not an extraction batch")
    if not RENDER_JS.exists():
        parser.error(f"missing renderer helper: {RENDER_JS}")

    flattened = skipped = 0
    with tempfile.TemporaryDirectory(prefix="flatten-bg-") as tmp:
        work_root = Path(tmp)
        plans: list[Plan] = []
        for item_dir in sorted((batch / "items").iterdir()):
            if not item_dir.is_dir():
                continue
            result = prepare(item_dir, work_root, args.min_images)
            if isinstance(result, str):
                print(f"  skip {item_dir.name}: {result}")
                skipped += 1
            else:
                plans.append(result)

        # Pass 1: render each item's background stack and original visual.
        render_jobs(
            [
                job
                for plan in plans
                for job in (
                    {"svg": str(plan.item_dir / "artifact" / ".flatten-bg.svg"),
                     "output": str(plan.bg_render),
                     "width": plan.width, "height": plan.height},
                    {"svg": str(plan.visual), "output": str(plan.orig_render),
                     "width": plan.width, "height": plan.height},
                )
            ]
        )

        # Pass 2: build and render the rewritten visual.
        for plan in plans:
            rewrite(plan)
        render_jobs(
            [
                {"svg": str(plan.new_svg), "output": str(plan.new_render),
                 "width": plan.width, "height": plan.height}
                for plan in plans
            ]
        )

        for plan in plans:
            mean_error, changed_ratio = diff_metrics(plan.orig_render, plan.new_render)
            stack_images = sum(chunk.image_refs for chunk in plan.background_chunks)
            ok = mean_error <= args.max_mean_error and changed_ratio <= args.max_changed_ratio
            if ok:
                plan.visual.write_text(plan.new_svg.read_text(encoding="utf-8"), encoding="utf-8")
                flattened += 1
                print(f"  flatten {plan.item_dir.name}: {stack_images} image refs -> 1 "
                      f"(mean_err={mean_error:.3f}, changed={changed_ratio:.5%})")
            else:
                skipped += 1
                print(f"  REJECT {plan.item_dir.name}: diff too large "
                      f"(mean_err={mean_error:.3f}, changed={changed_ratio:.5%}) — left unchanged")
                background = plan.item_dir / "artifact" / "assets"
                # Drop the background asset we staged for a rejected item.
                for path in background.glob("background-*.png"):
                    referenced = path.name in plan.visual.read_text(encoding="utf-8")
                    if not referenced:
                        path.unlink()
            (plan.item_dir / "artifact" / ".flatten-bg.svg").unlink(missing_ok=True)
            (plan.item_dir / "artifact" / ".flatten-new.svg").unlink(missing_ok=True)

    print(f"Flattened {flattened} item(s), skipped {skipped}.")
    if flattened:
        print("Rerun externalize_svg_images.py + optimize_svg.py + validate_text_slots.py "
              "on this batch to refresh manifests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
