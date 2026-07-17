#!/usr/bin/env python3
"""Audit which published items carry IMMUTABLE text — copy that survives when every
editable slot is emptied.

Why this exists (and why the obvious audit does not work): the extraction pipeline
strips `<text>` out of `visual.svg`, so NO published item has live text in its
background — parsing the artifacts for "text with no slot" finds nothing on every
item, including the ones that genuinely do carry fixed copy. The real baked text is
OUTLINED VECTOR PATHS (a programme lockup exported from the source deck). No XML
parse can see it, and OCR would mean a new dependency.

So the audit renders the truth instead: scaffold each item, leave EVERY slot empty,
and screenshot it. Whatever words remain cannot be edited through any slot — that is
exactly "visible in the artifact but not represented by an editable slot". The render
is deterministic and reproducible; deciding whether the remaining ink is a WORD (vs
artwork) is left to a human, whose verdict is recorded as `immutable_text.audit` on
the item. That is the honest split: the machine produces evidence, the human
classifies, the registry records it, and the scorer enforces it.

Also checks, deterministically, the one thing that IS decidable from the artifacts:
that every `<text>` node in the source evidence is covered by a declared slot. An
uncovered source string would be copy the deck can never edit OR silently loses.

Two report kinds, never the same file — a static pass must not be mistakable for, or
overwrite, real visual evidence:

  audit-report.json          mode=rendered. Written ONLY by a rendering run. Carries a
                             durable repo-relative render path for every renderable item
                             and an explicit reason for every one that has none. Its
                             `status` is `complete` only when every renderable item
                             actually rendered; otherwise `incomplete`, and it must not
                             be cited as proof of a clean/immutable verdict.
  audit-report.static.json   mode=static-only (--no-render). Markup checks only. It can
                             never prove a verdict, so it is written under its own name
                             and leaves any rendered report untouched.

Usage:
  <project-python> slide-system/scripts/audit_immutable_text.py \
      --out-dir <run>/qa/immutable-text-audit [--ids id1,id2] [--no-render]

Outputs (under --out-dir):
  audit-report.json / audit-report.static.json   machine-readable, one record per item
  renders/<id>.png    the empty-slot render (the evidence a human classifies)
  sheets/<n>.png      contact sheets, grouped by source set, for review
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from _common import load_json, write_json
import build_registry

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
DEFAULT_REGISTRY = SCRIPTS.parent / "registries/visual-library.json"


def _rel(path: Path, base: Path = REPO) -> str:
    """Posix path relative to `base`. Evidence must be citable from any checkout,
    so reports never carry absolute machine paths. Render evidence is written
    relative to the REPORT (base=the audit dir) so the audit folder stays a
    self-contained bundle that still resolves after it is moved or archived;
    repo files (the registry) stay repo-relative."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()

# <text>…</text> including any nested <tspan>; whitespace-normalized.
_TEXT_BLOCK_RE = re.compile(r"<text[^>]*>(.*?)</text>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def source_text_nodes(path: str | None) -> list[str] | None:
    """The literal strings the SOURCE artwork carried as live text. None when the
    item ships no source evidence (nothing to compare against)."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    xml = p.read_text(encoding="utf-8", errors="replace")
    out = []
    for block in _TEXT_BLOCK_RE.findall(xml):
        s = re.sub(r"\s+", " ", _TAG_RE.sub(" ", block)).strip()
        if s:
            out.append(s)
    return out


def declared_slots(item: dict) -> list[dict]:
    ts = (item.get("paths") or {}).get("text_slots")
    if not ts or not Path(ts).exists():
        return []
    data = load_json(ts)
    slots = data.get("slots", data) if isinstance(data, dict) else data
    return [s for s in slots if isinstance(s, dict) and s.get("id")]


def _norm(s: str) -> str:
    """Fold a string to the shape the slot-id slugger produces, so a source string and
    its slot id compare equal without depending on that slugger's exact rules. Entities
    are unescaped first: raw `&amp;` would otherwise inject a literal 'amp' that the
    slugger never saw, and every '&' in the deck would look uncovered."""
    return re.sub(r"[^a-z0-9]+", "", html.unescape(s).lower())


def source_text_uncovered(item: dict) -> list[str] | None:
    """Source strings that no declared slot appears to represent. Deterministic, but it
    only sees LIVE text — outlined text is invisible here (that is what the empty-slot
    render is for). None when there is no source evidence to check.

    One `<text>` block can hold several `<tspan>` lines that each became their own slot,
    and a slot id is a truncated slug, so a block is covered when any slot id is a
    substring of it (or the block of the id) — not by equality."""
    # Only meaningful for full-slide templates. A component's source evidence is the
    # whole SOURCE PAGE it was cropped from, so its neighbours' copy is "uncovered" by
    # construction — comparing that against the crop's slots is noise, not a finding.
    if item.get("type") != "template":
        return None
    src = source_text_nodes((item.get("text_contract") or {}).get("source_evidence"))
    if src is None:
        return None
    slot_keys = {_norm(s["id"]) for s in declared_slots(item)}
    slot_keys.discard("")
    uncovered = []
    for s in src:
        n = _norm(s)
        if not n or any(k in n or n in k for k in slot_keys):
            continue
        uncovered.append(s)
    return uncovered


def empty_scaffold(item_id: str, registry: str, out_html: Path) -> bool:
    """Scaffold the item and leave every slot EMPTY — the scaffold already emits
    blank slots, so this is the real build path with no copy authored into it."""
    frag = out_html.parent / "frag.html"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "scaffold_slide_from_component.py"),
         "--item-id", item_id, "--registry", registry,
         "--out", str(frag), "--instance-id", "audit"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return False
    out_html.write_text(
        '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        "html,body{margin:0;padding:0}"
        ".slide{position:relative;width:1920px;height:1080px;overflow:hidden;background:#fff}"
        '</style></head><body><section class="slide">'
        + frag.read_text(encoding="utf-8") + "</section></body></html>",
        encoding="utf-8")
    return True


_SHOT_JS = """
const { chromium } = require('playwright');
const jobs = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  for (const j of jobs) {
    try {
      await p.goto('file:///' + j.html.split('\\\\').join('/'), { waitUntil: 'networkidle' });
      await p.evaluate(() => (document.fonts && document.fonts.ready) || Promise.resolve());
      const el = await p.$('.slide');
      await el.screenshot({ path: j.png });
      console.log('ok ' + j.id);
    } catch (e) { console.log('ERR ' + j.id + ' ' + e.message.slice(0, 80)); }
  }
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
"""


def render_all(jobs: list[dict]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        js = Path(tmp) / "shot.js"
        js.write_text(_SHOT_JS, encoding="utf-8")
        spec = Path(tmp) / "jobs.json"
        spec.write_text(json.dumps(jobs), encoding="utf-8")
        env = {"NODE_PATH": str(REPO / "node_modules")}
        import os
        proc = subprocess.run(["node", str(js), str(spec)], capture_output=True, text=True,
                              env={**os.environ, **env})
        sys.stdout.write(proc.stdout[-2000:])
        if proc.returncode != 0:
            print(proc.stderr[-1000:], file=sys.stderr)


def contact_sheets(records: list[dict], audit_dir: Path, per_sheet: int = 12) -> list[str]:
    """Grid the empty renders so a human can scan them for surviving words. Grouped
    by source set (a baked lockup is usually a per-DECK design element)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("WARN: PIL unavailable; skipping contact sheets", file=sys.stderr)
        return []
    have = [r for r in records if r.get("render", {}).get("status") == "rendered"]
    have.sort(key=lambda r: (r["id"].split(".")[1] if r["id"].count(".") >= 2 else "", r["id"]))
    cols, tw, th, pad = 3, 620, 349, 26
    sheets: list[str] = []
    out_dir = audit_dir / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    for n in range(0, len(have), per_sheet):
        chunk = have[n:n + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad) + pad), "#3a3a3a")
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(chunk):
            x = pad + (i % cols) * (tw + pad)
            y = pad + (i // cols) * (th + pad)
            im = Image.open(audit_dir / r["render"]["path"]).convert("RGB").resize((tw, th - 18))
            sheet.paste(im, (x, y + 18))
            d.rectangle([x, y + 18, x + tw, y + th], outline="#888")
            d.text((x + 2, y + 4), r["id"][:78], fill="#fff")
        p = out_dir / f"sheet-{n // per_sheet + 1:02d}.png"
        sheet.save(p)
        sheets.append(_rel(p, audit_dir))
    return sheets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ids", help="Comma-separated subset (default: every published item).")
    ap.add_argument("--no-render", action="store_true",
                    help="Static checks only; skip the empty-slot renders.")
    args = ap.parse_args(argv)

    registry = load_json(args.registry)
    wanted = {i.strip() for i in args.ids.split(",")} if args.ids else None
    items = [i for i in registry.get("items", [])
             if i.get("status") == "published" and (not wanted or i.get("id") in wanted)]

    out = Path(args.out_dir)
    renders = out / "renders"
    renders.mkdir(parents=True, exist_ok=True)

    rendered_report = out / "audit-report.json"
    report_path = out / ("audit-report.static.json" if args.no_render else "audit-report.json")

    records, jobs = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for item in items:
            iid = item["id"]
            slots = declared_slots(item)
            uncovered = source_text_uncovered(item)
            rec = {
                "id": iid,
                "type": item.get("type"),
                "declared_slots": len(slots),
                "source_text_nodes": None if uncovered is None
                                     else len(source_text_nodes(
                                         (item.get("text_contract") or {}).get("source_evidence")) or []),
                # Deterministic: live source strings no slot represents. Outlined text
                # is invisible here — the empty render is what exposes that.
                "uncovered_source_text": uncovered,
                "recorded": item.get("immutable_text"),
                # The fingerprint of the artwork this record is evidence ABOUT. Copy it
                # into immutable_text.evidence when recording a verdict; build_registry
                # re-checks it and fails closed once the artifact changes.
                "artifact_fingerprint": build_registry.immutable_text_fingerprint(item),
                "render": {"status": "skipped", "path": None,
                           "reason": "static-only run (--no-render): no render attempted"},
            }
            if not args.no_render:
                stage = Path(tmp) / iid
                stage.mkdir(parents=True, exist_ok=True)
                html = stage / "page.html"
                if empty_scaffold(iid, args.registry, html):
                    png = renders / f"{iid}.png"
                    jobs.append({"id": iid, "html": str(html), "png": str(png)})
                    rec["render"] = {"status": "pending", "path": _rel(png, out), "reason": None}
                else:
                    rec["render"] = {"status": "not-applicable", "path": None, "reason": (
                        "cannot be scaffolded (no preview/slot contract to empty), so an "
                        "empty-slot render cannot exist for this item")}
            records.append(rec)

        if jobs:
            print(f"rendering {len(jobs)} item(s) with every slot empty…")
            render_all(jobs)

    for r in records:
        if r["render"]["status"] != "pending":
            continue
        # Only a file on disk counts as evidence.
        if (out / "renders" / f"{r['id']}.png").is_file():
            r["render"] = {"status": "rendered", "path": r["render"]["path"], "reason": None}
        else:
            r["render"] = {"status": "failed", "path": None,
                           "reason": "the browser produced no screenshot for this item"}

    by_status = collections.Counter(r["render"]["status"] for r in records)
    renderable = [r for r in records if r["render"]["status"] in ("rendered", "failed")]
    # A rendered audit is only COMPLETE when every renderable item actually produced
    # evidence. Anything less must not be cited as proof of a verdict.
    complete = (not args.no_render and renderable
                and all(r["render"]["status"] == "rendered" for r in renderable))
    sheets = contact_sheets(records, out) if not args.no_render else []
    report = {
        "generated_by": "audit_immutable_text.py",
        "mode": "static-only" if args.no_render else "rendered",
        "status": "complete" if complete else "incomplete",
        "usable_as_verdict_evidence": bool(complete),
        "registry": _rel(Path(args.registry)),
        "method": ("Scaffold each published item and render it with EVERY editable slot "
                   "empty. Any word still visible cannot be edited through a slot and is "
                   "therefore immutable. Outlined (path) text is invisible to XML parsing, "
                   "so the render — not the markup — is the evidence; a human classifies it "
                   "and the verdict is recorded as immutable_text.audit on the item. A "
                   "static-only (--no-render) run performs the markup checks ONLY and can "
                   "never establish a verdict."),
        "counts": {
            "audited": len(records),
            "with_uncovered_source_text": sum(1 for r in records if r["uncovered_source_text"]),
            **{f"render_{k}": v for k, v in sorted(by_status.items())},
        },
        "contact_sheets": sheets,
        "items": records,
    }

    if args.no_render and rendered_report.is_file():
        # Never let a markup-only pass overwrite or downgrade real visual evidence:
        # that is exactly how a report came to claim 91 audited with 0 rendered while
        # 90 renders sat on disk beside it.
        print(f"NOTE: keeping the existing rendered report at {_rel(rendered_report)}; "
              f"this static-only pass is written separately.", file=sys.stderr)

    write_json(report_path, report)
    print(f"audit [{report['mode']}/{report['status']}]: {len(records)} published item(s); "
          + ", ".join(f"{v} {k}" for k, v in sorted(by_status.items()))
          + f"; {len(sheets)} contact sheet(s) -> {_rel(report_path)}")
    if not complete and not args.no_render:
        print("WARNING: this rendered audit is INCOMPLETE — it must not be used as "
              "evidence for a clean/immutable verdict.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
