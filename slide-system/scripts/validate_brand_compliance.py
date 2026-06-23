#!/usr/bin/env python3
"""Post-build gate: validate HTML deck follows SUN.STUDIO brand rules before PPTX export."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import load_json, now_iso, write_json

BRAND_HEX = {
    "#ff5533", "#3333ff", "#171717",
    "#ffd4cc", "#ffaa99", "#ff7766", "#fff3ef", "#eb462d",
    "#ccccff", "#9999ff", "#6666ff", "#f4f5ff",
    "#2a2a2a", "#666666", "#8a8a8a", "#e7e7e7", "#cfcfcf",
    "#fafafa", "#ffffff", "#fffdf8",
    "#22c55e", "#dcfce7", "#ef4444", "#fee2e2",
    "#000000",
}

ALWAYS_ALLOWED_PATTERNS = {"transparent", "inherit", "currentcolor", "none"}

EMOJI_RANGES = [
    (0x1F300, 0x1FAFF),
    (0x2600, 0x26FF),
    (0x2700, 0x27BF),
    (0xFE00, 0xFE0F),
    (0x200D, 0x200D),
    (0xE0020, 0xE007F),
]

BRAND_PRIMARY_FONT = "proxima nova"
ALLOWED_GENERIC = {"monospace", "system-ui", "sans-serif", "serif", "-apple-system"}


def _is_emoji(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in EMOJI_RANGES)


def check_emoji(text: str) -> dict:
    found: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for ch in line:
            cp = ord(ch)
            if _is_emoji(cp):
                entry = f"U+{cp:04X} '{ch}' line {lineno}: {line.strip()[:60]}"
                if entry not in found:
                    found.append(entry)
    passed = not found
    return {"name": "emoji_icons", "pass": passed,
            "detail": "No emoji found." if passed else f"{len(found)} emoji occurrence(s) found.",
            "found": found}


def _primary_font(declaration: str) -> str:
    return declaration.split(",")[0].strip().strip("'\"").lower()


def _extract_css(html: str) -> str:
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL | re.IGNORECASE)
    inline = re.findall(r'style\s*=\s*"([^"]*)"', html, re.IGNORECASE)
    inline += re.findall(r"style\s*=\s*'([^']*)'", html, re.IGNORECASE)
    return "\n".join(blocks + inline)


def check_brand_fonts(html: str) -> dict:
    all_css = _extract_css(html)
    raw_families = re.findall(r"font-family\s*:\s*([^;}\n\"']+)", all_css, re.IGNORECASE)
    violations = list(dict.fromkeys(
        f"'{r.strip()}'" for r in raw_families
        if (p := _primary_font(r.strip())) and p not in
        (ALWAYS_ALLOWED_PATTERNS | ALLOWED_GENERIC | {BRAND_PRIMARY_FONT})
    ))
    passed = not violations
    return {"name": "brand_fonts", "pass": passed,
            "detail": "All fonts compliant." if passed else f"{len(violations)} non-brand font declaration(s).",
            "violations": violations}


def _expand_hex3(h: str) -> str:
    if len(h) == 3:
        return h[0] * 2 + h[1] * 2 + h[2] * 2
    return h


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _collect_colors(css_text: str) -> set[str]:
    colors: set[str] = set()
    for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", css_text, re.IGNORECASE):
        colors.add(_rgb_to_hex(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in re.finditer(r"#([0-9a-fA-F]{3,8})\b", css_text):
        raw = m.group(1).lower()
        if len(raw) in (3, 6):
            colors.add("#" + _expand_hex3(raw) if len(raw) == 3 else "#" + raw)
        elif len(raw) == 8:
            colors.add("#" + raw[:6])
    return colors


def check_brand_colors(html: str) -> dict:
    non_brand = sorted(_collect_colors(_extract_css(html)) - BRAND_HEX)
    passed = len(non_brand) <= 5
    detail = f"{len(non_brand)} unique non-brand color(s) found (threshold 5)." if non_brand else "All colors within brand palette."
    return {"name": "brand_colors", "pass": passed, "detail": detail,
            "non_brand_count": len(non_brand), "non_brand": non_brand}


def check_template_assets(html: str, selection_report: dict) -> dict:
    missing = []
    entries = selection_report.get("slides", [])
    if not entries and "decision" in selection_report:
        entries = [selection_report]
    for slide in entries:
        action = slide.get("decision", {}).get("action", "")
        item_id = slide.get("decision", {}).get("item_id") or ""
        if action not in ("reuse", "adapt-local") or not item_id:
            continue
        patterns = [item_id, item_id.replace(".", "-").replace("_", "-").lower(), item_id.split(".")[-1]]
        if not any(p in html for p in patterns if p):
            missing.append(item_id)
    passed = not missing
    return {"name": "template_assets", "pass": passed,
            "detail": "All reuse/adapt-local assets referenced." if passed else f"{len(missing)} asset(s) not referenced in HTML.",
            "missing": missing}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate HTML deck brand compliance.")
    parser.add_argument("--html", required=True, help="Path to the built HTML deck.")
    parser.add_argument("--selection-report", required=True, help="Path to selection-report JSON (required: the template_assets check must not be skippable).")
    parser.add_argument(
        "--brand-pack",
        default=None,
        help="Path to brand-pack manifest (default: brand-packs/sun-studio/manifest.json).",
    )
    args = parser.parse_args()

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        print(f"ERROR: HTML file not found: {html_path}", file=sys.stderr)
        return 1

    html = html_path.read_text(encoding="utf-8", errors="replace")
    checks: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []

    checks.append(check_emoji(html))
    checks.append(check_brand_fonts(html))

    color_check = check_brand_colors(html)
    if color_check["non_brand_count"] > 0:
        warnings.append(f"Non-brand colors detected: {', '.join(color_check['non_brand'])}")
    checks.append(color_check)

    try:
        checks.append(check_template_assets(html, load_json(args.selection_report)))
    except Exception as exc:
        # A selection-report that cannot be loaded is a hard failure, never a
        # silent pass — otherwise the fidelity check becomes opt-out.
        errors.append(f"Could not load selection-report: {exc}")
        checks.append({"name": "template_assets", "pass": False, "missing": [],
                       "detail": f"FAILED to load selection-report: {exc}"})

    failed = [c for c in checks if not c["pass"]]
    valid = len(failed) == 0 and len(errors) == 0

    report = {
        "valid": valid,
        "checked_at": now_iso(),
        "html_path": str(html_path),
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }

    out_path = html_path.parent / "qa" / "brand-compliance-report.json"
    write_json(out_path, report)

    status = "PASS" if valid else "FAIL"
    print(f"Brand compliance: {status}")
    for check in checks:
        mark = "OK" if check["pass"] else "FAIL"
        print(f"  [{mark}] {check['name']}: {check['detail']}")
    for warning in warnings:
        print(f"  [WARN] {warning}")
    for error in errors:
        print(f"  [ERROR] {error}")
    print(f"Report: {out_path}")

    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
