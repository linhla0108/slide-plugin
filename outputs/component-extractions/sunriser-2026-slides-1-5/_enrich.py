#!/usr/bin/env python3
"""Enrich staging mappings, write reports/evidence/previews for the slides 1-5 batch."""
import json, shutil
from pathlib import Path

BATCH = Path(__file__).resolve().parent
REPO = BATCH.parents[2]
PNG_DIR = REPO / "input" / "SUN.RISER 2026 - Be professional at SUN.STUDIO (PNG)"
SVG_DIR = REPO / "input" / "SUN.RISER 2026 - Be professional at SUN.STUDIO (SVG)"

CSS_BG = {"html": "supported", "pptx": "raster", "pdf": "supported", "canva": "raster"}
CSS_OK = {"html": "supported", "pptx": "supported", "pdf": "supported", "canva": "untested"}
SVG_OK = {"html": "supported", "pptx": "supported", "pdf": "supported", "canva": "untested"}
TPL = {"html": "supported", "pptx": "hybrid", "pdf": "supported", "canva": "untested"}

# id -> enrichment + preview body
META = {
  "orange-pinstripe": dict(
    name="Orange Pinstripe Background", artifact="orange-pinstripe.css", kind="css-bg",
    tags=["background","orange","gradient","pinstripe","title"], compat=CSS_BG,
    required=[], optional=[], variables=["--sun-orange","--sun-orange-deep","--sun-orange-pale"],
    limitations=["Layered gradients may not round-trip in PPTX/Canva; use PNG fallback.",
                 "Color tokens are approximate; reconcile with canonical design system."],
    css_class="sun-bg-orange-pinstripe"),
  "orange-arcs": dict(
    name="Orange Arcs Background", artifact="orange-arcs.css", kind="css-bg",
    tags=["background","orange","gradient","arcs"], compat=CSS_BG,
    required=[], optional=[], variables=["--sun-orange","--sun-orange-pale"],
    limitations=["Repeating radial gradient may not round-trip in PPTX/Canva; use PNG fallback."],
    css_class="sun-bg-orange-arcs"),
  "blue-arcs": dict(
    name="Blue Arcs Background", artifact="blue-arcs.css", kind="css-bg",
    tags=["background","blue","gradient","arcs","section"], compat=CSS_BG,
    required=[], optional=[], variables=["--sun-blue","--sun-blue-mid","--sun-blue-pale"],
    limitations=["Repeating radial gradient may not round-trip in PPTX/Canva; use PNG fallback.",
                 "Cool-tone sibling of sun.background.orange-arcs (shared geometry)."],
    css_class="sun-bg-blue-arcs"),
  "header-tag": dict(
    name="Header Tag", artifact="header-tag.css", kind="css-chrome",
    tags=["chrome","pill","label","counter","header"], compat=CSS_OK,
    required=["label","counter"], optional=[], variables=["--sun-orange","--sun-ink"],
    variants=["filled","dark","white","outline"],
    limitations=["Four variants observed across slides 1-5; verify the full deck for more."]),
  "title-cover": dict(
    name="Title Cover Template", artifact="title-cover.html", kind="template",
    tags=["template","cover","title","full-slide"], compat=TPL,
    required=["title_line_1","logo_src"], optional=["title_line_2","tag_label","tag_counter"],
    variables=[],
    limitations=["Layout contract only; no source copy reused.",
                 "Composes sun.background.orange-pinstripe, sun.asset.logo, sun.component.header-tag."]),
  "numbered-heading": dict(
    name="Numbered Heading", artifact="numbered-heading.css", kind="css-block",
    tags=["heading","step","number","intro"], compat=CSS_OK,
    required=["number","heading"], optional=["support"], variables=["--sun-ink","--sun-orange"],
    limitations=["Preview uses placeholder copy; source wording stored in evidence only."]),
  "prompt-questions": dict(
    name="Prompt Questions", artifact="prompt-questions.css", kind="css-block",
    tags=["prompt","questions","discussion","list"], compat=CSS_OK,
    required=["lead","items"], optional=[], variables=["--sun-orange","--sun-ink"],
    limitations=["Preview uses placeholder copy; source wording stored in evidence only."]),
  "arrow-up-right": dict(
    name="Arrow Up-Right Icon", artifact="arrow-up-right.svg", kind="svg",
    tags=["icon","arrow","mark"], compat=SVG_OK,
    required=[], optional=[], variables=["currentColor"],
    limitations=["Recurs on slides 3 and 5; color via currentColor."]),
  "quote-mark": dict(
    name="Quote Mark Icon", artifact="quote-mark.svg", kind="svg",
    tags=["icon","quote","mark","decoration"], compat=SVG_OK,
    required=[], optional=[], variables=["currentColor"],
    limitations=["Decorative glyph; path is a clean reconstruction, not a font glyph."]),
  # duplicates
  "logo": dict(name="SUN.STUDIO Logo", dup="sun.asset.logo", dup_status="published v1.0.0"),
  "qr-stack": dict(name="QR Stack", dup="sun.component.qr-stack", dup_status="qa v0.9.0"),
  "agenda": dict(name="Agenda", dup="sun.section.agenda", dup_status="published v1.0.0"),
  "divider": dict(name="Section Divider", dup="sun.section.divider", dup_status="published v1.0.0"),
  "folio": dict(name="Folio Footer", dup="sun.component.folio", dup_status="published v1.0.0"),
}

def preview_body(item_id, m, art_rel):
    k = m.get("kind")
    if k == "css-bg":
        return (f'<link rel="stylesheet" href="{art_rel}">'
                f'<div class="stage {m["css_class"]}"></div>')
    if k == "svg":
        svg = (BATCH/"items"/item_id/"artifact"/m["artifact"]).read_text()
        return f'<div class="stage stage--light icon-host">{svg}</div>'
    if k == "css-chrome":
        return (f'<link rel="stylesheet" href="{art_rel}">'
          '<div class="rows">'
          '<div class="row" style="background:#ff5533">'
          '<div class="sun-header-tag" data-variant="filled"><span class="sun-header-tag__label">Intern L&amp;D</span><span class="sun-header-tag__counter">#01</span></div></div>'
          '<div class="row" style="background:#fff">'
          '<div class="sun-header-tag" data-variant="dark"><span class="sun-header-tag__label">Intern L&amp;D</span><span class="sun-header-tag__counter">#01</span></div></div>'
          '<div class="row" style="background:#2f3bff">'
          '<div class="sun-header-tag" data-variant="white"><span class="sun-header-tag__label">Intern L&amp;D</span><span class="sun-header-tag__counter">#01</span></div></div>'
          '<div class="row" style="background:#f3f3f3;color:#111">'
          '<div class="sun-header-tag" data-variant="outline"><span class="sun-header-tag__label">Intern L&amp;D</span><span class="sun-header-tag__counter">#01</span></div></div>'
          '</div>')
    if item_id == "numbered-heading":
        return (f'<link rel="stylesheet" href="{art_rel}">'
          '<div class="stage stage--light"><div class="sun-numbered-heading">'
          '<p class="sun-numbered-heading__number">01</p>'
          '<p class="sun-numbered-heading__heading">Heading goes here</p>'
          '<p class="sun-numbered-heading__support">Supporting line of context.</p>'
          '</div></div>')
    if item_id == "prompt-questions":
        return (f'<link rel="stylesheet" href="{art_rel}">'
          '<div class="stage stage--light"><div class="sun-prompt-questions">'
          '<p class="sun-prompt-questions__lead">Lead-in prompt line.</p>'
          '<ul class="sun-prompt-questions__list"><li>First question placeholder?</li>'
          '<li>Second question placeholder?</li></ul></div></div>')
    if k == "template":
        html = (BATCH/"items"/item_id/"artifact"/m["artifact"]).read_text()
        html = (html.replace("{{logo_src}}","")
                    .replace("{{tag_label}}","Intern L&amp;D").replace("{{tag_counter}}","#01")
                    .replace("{{title_line_1}}","TITLE LINE ONE").replace("{{title_line_2}}","@PLACEHOLDER"))
        return (f'<link rel="stylesheet" href="../../header-tag/artifact/header-tag.css">'
                f'<link rel="stylesheet" href="../../orange-pinstripe/artifact/orange-pinstripe.css">'
                f'<div class="stage stage--bare">{html}</div>')
    return "<p>preview</p>"

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{title} — preview</title>
<style>
 body{{font-family:Inter,system-ui,sans-serif;margin:0;background:#fafafa;color:#111}}
 header{{padding:14px 18px;border-bottom:1px solid #eee;font-size:13px}}
 header b{{font-size:15px}} header code{{color:#666}}
 main{{padding:18px}}
 .stage{{aspect-ratio:16/9;width:100%;max-width:760px;border-radius:8px;border:1px solid #eee;overflow:hidden}}
 .stage--light{{background:#fff;display:flex;align-items:center;justify-content:center;padding:32px;box-sizing:border-box}}
 .stage--bare{{border:none;padding:0}}
 .icon-host svg{{width:120px;height:120px}}
 .rows{{display:grid;gap:10px;max-width:520px}}
 .row{{padding:14px;border-radius:8px;display:flex;justify-content:flex-end}}
</style></head><body>
<header><b>{title}</b> &nbsp; <code>{cid}</code> &nbsp; status: <b>{status}</b> &nbsp; slide {slide}{dupline}</header>
<main>{body}</main></body></html>"""

for mp in sorted((BATCH/"items").glob("*/mapping.json")):
    m_full = json.load(open(mp))
    iid = m_full["item_id"]
    meta = META[iid]
    item_dir = mp.parent
    slide = m_full["source"]["slide_or_page"]
    # enrich mapping
    m_full["name"] = meta["name"]
    if "dup" in meta:
        m_full["tags"] = ["duplicate"]
        m_full["limitations"] = [f"Already in library as {meta['dup']} ({meta['dup_status']}); do not re-publish."]
        m_full["notes_resolution"] = f"Maps to existing {meta['dup']}."
    else:
        m_full["tags"] = meta["tags"]
        m_full["content_fields"] = {"required": meta["required"], "optional": meta["optional"]}
        m_full["variables"] = meta["variables"]
        m_full["variants"] = meta.get("variants", [])
        m_full["compatibility"] = meta["compat"]
        m_full["limitations"] = meta["limitations"]
        m_full["paths"] = {"artifact": f"artifact/{meta['artifact']}", "preview": "preview/index.html"}
    json.dump(m_full, open(mp, "w"), indent=2)
    open(mp, "a").write("\n")

    # evidence: copy source slide png + notes
    src_png = PNG_DIR / f"{slide}.png"
    if src_png.exists():
        shutil.copy(src_png, item_dir/"evidence"/f"source-slide-{slide}.png")
    region = m_full["source"]["region"]
    rel_png = f"../../../../../input/SUN.RISER 2026 - Be professional at SUN.STUDIO (PNG)/{slide}.png"
    rel_svg = f"../../../../../input/SUN.RISER 2026 - Be professional at SUN.STUDIO (SVG)/{slide}.svg"
    (item_dir/"evidence"/"notes.md").write_text(
        f"# Evidence — {meta['name']}\n\n"
        f"- Candidate ID: `{m_full['candidate_stable_id']}`\n"
        f"- Status: `{m_full['status']}`\n"
        f"- Source deck: `{m_full['source']['path']}` (sha256 `{m_full['source']['sha256'][:16]}...`)\n"
        f"- Slide: {slide}\n"
        f"- Region (normalized 0-1 of 960x540): x={region['x']} y={region['y']} "
        f"w={region['width']} h={region['height']}\n"
        f"- Object handles: {m_full['source']['object_ids'] or 'none'}\n\n"
        f"## Source reference\n"
        f"- Full slide raster copied here: `source-slide-{slide}.png`\n"
        f"- Original PNG: `{rel_png}`\n"
        f"- Original SVG (vector): `{rel_svg}`\n\n"
        f"## Method\n"
        + ("Background reconstructed as layered CSS gradients; raster PNG fallback recommended for PPTX/Canva.\n"
           if meta.get('kind')=='css-bg' else
           "Standalone SVG reconstruction (currentColor).\n" if meta.get('kind')=='svg' else
           "Full-slide layout contract; foreground text kept as editable slots, no source copy reused.\n" if meta.get('kind')=='template' else
           "Semantic HTML + scoped CSS; foreground text kept editable.\n" if 'dup' not in meta else
           f"Region matched to existing library item {meta.get('dup')}; no new artifact produced.\n")
        + "\nRegion bounds are visual estimates from the 960x540 export and should be tightened against the PPTX shape geometry before publish.\n",
        encoding="utf-8")

    # report.md
    if "dup" in meta:
        (item_dir/"report.md").write_text(
          f"# Extraction Report — {meta['name']}\n\n"
          f"- Candidate ID: `{m_full['candidate_stable_id']}`\n- Status: `duplicate`\n- Approval: `n/a`\n\n"
          f"This region matches an existing library item **{meta['dup']}** ({meta['dup_status']}). "
          f"No new artifact was created. Action: reuse the published item; do not re-publish.\n", encoding="utf-8")
    else:
        (item_dir/"report.md").write_text(
          f"# Extraction Report — {meta['name']}\n\n"
          f"- Candidate ID: `{m_full['candidate_stable_id']}`\n- Status: `staging`\n- Approval: `pending`\n\n"
          f"## Method\nSee `evidence/notes.md`. Artifact: `artifact/{meta['artifact']}`.\n\n"
          f"## Content contract\n- Required: {meta['required'] or 'none'}\n- Optional: {meta['optional'] or 'none'}\n"
          f"- Variants: {meta.get('variants', []) or 'none'}\n\n"
          f"## Compatibility\n" + "".join(f"- {k}: {v}\n" for k,v in meta['compat'].items()) +
          f"\n## Limitations\n" + "".join(f"- {l}\n" for l in meta['limitations']) +
          f"\n## Preview\nOpen `preview/index.html`.\n", encoding="utf-8")

    # preview
    if "dup" in meta:
        dupline = f' &nbsp; → duplicate of <code>{meta["dup"]}</code> ({meta["dup_status"]})'
        body = (f'<div class="stage stage--light"><div style="text-align:center;max-width:60ch">'
                f'<p style="font-size:15px">Region matches existing library item</p>'
                f'<p style="font-size:22px"><b>{meta["dup"]}</b></p>'
                f'<p style="color:#666">{meta["dup_status"]} — reuse, do not re-publish.</p>'
                f'<p style="color:#999;font-size:13px">Source: slide {slide}. See evidence/source-slide-{slide}.png</p>'
                f'</div></div>')
    else:
        dupline = ""
        art_rel = f"../artifact/{meta['artifact']}"
        body = preview_body(iid, meta, art_rel)
    (item_dir/"preview"/"index.html").write_text(
        PAGE.format(title=meta["name"], cid=m_full["candidate_stable_id"],
                    status=m_full["status"], slide=slide, dupline=dupline, body=body),
        encoding="utf-8")

print("enriched", len(list((BATCH/'items').glob('*/mapping.json'))), "items")
