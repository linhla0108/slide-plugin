#!/usr/bin/env python3
"""Validate a per-user slide style profile against the whitelisted schema.

A style profile records APPROVED, enum-bounded design preferences only (see
`slide-system/schemas/style-profile.schema.json` and `rules/style-profiles.md`).
This gate refuses anything outside that contract so a profile can never smuggle
arbitrary CSS/HTML/JS, raw deck text, secrets, or free-form values into the
generation pipeline. No new dependency, no network — a hand-rolled check mirroring
`validate_component_metadata.py`.

Usage:
  <project-python> slide-system/scripts/validate_style_profile.py --profile <path>
Exit 0 = valid; exit 1 = one error per line, plain language.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import load_json

TOP_KEYS = {"profile_id", "version", "owner", "description", "preferences"}
REQUIRED_TOP = {"profile_id", "version", "preferences"}

# preference key -> allowed enum values (None means "array of intent slugs").
ENUMS: dict[str, set[str] | None] = {
    "information_density": {"minimal", "balanced", "rich"},
    "heading_hierarchy": {"understated", "balanced", "bold"},
    "spacing": {"tight", "balanced", "airy"},
    "visual_rhythm": {"calm", "dynamic"},
    "visual_tone": {"restrained", "expressive"},
    "media_bias": {"image-led", "diagram-led", "balanced"},
    "language": {"vi", "en", "bilingual"},
    "tone": {"coaching", "formal", "energetic", "neutral"},
}
LAYOUT_FAMILIES = {"grid", "columns", "timeline", "cards", "centered", "split",
                   "editorial", "list"}
ARRAY_KEYS = {"layout_families", "preferred_component_intents", "avoided_component_intents"}
PREF_KEYS = set(ENUMS) | ARRAY_KEYS

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# Genuine markup / CSS / URL / script injection vectors are forbidden in every
# string value. Ordinary prose punctuation (commas, colons, single slashes) is
# allowed in free-text owner/description; enum + slug values are separately
# pattern-checked so they can never carry any of this anyway.
_UNSAFE_RE = re.compile(
    r"[<>{}]|url\(|https?://|/\*|\*/|javascript:|expression\(|@import|\\|[\r\n]",
    re.IGNORECASE)


def _unsafe(value: str) -> bool:
    return bool(_UNSAFE_RE.search(value))


def validate_profile(profile: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(profile, dict):
        return ["profile must be a JSON object"]

    unknown = set(profile) - TOP_KEYS
    if unknown:
        errors.append(f"unknown top-level key(s): {sorted(unknown)}")
    for k in REQUIRED_TOP:
        if k not in profile:
            errors.append(f"missing required key: {k}")

    pid = profile.get("profile_id")
    if isinstance(pid, str) and not _ID_RE.match(pid):
        errors.append(f"profile_id {pid!r} must match ^[a-z0-9][a-z0-9._-]*$")
    ver = profile.get("version")
    if isinstance(ver, str) and not _VERSION_RE.match(ver):
        errors.append(f"version {ver!r} must be semantic (x.y.z)")
    for k in ("owner", "description"):
        v = profile.get(k)
        if v is not None and (not isinstance(v, str) or _unsafe(v)):
            errors.append(f"{k} must be a plain string with no markup/CSS/URL/script")

    prefs = profile.get("preferences")
    if prefs is None:
        return errors
    if not isinstance(prefs, dict):
        errors.append("preferences must be an object")
        return errors

    for key, val in prefs.items():
        if key not in PREF_KEYS:
            errors.append(f"unknown preference key: {key}")
            continue
        if key in ENUMS:
            if not isinstance(val, str) or _unsafe(val) or val not in ENUMS[key]:
                errors.append(f"{key} must be one of {sorted(ENUMS[key])}, got {val!r}")
        elif key == "layout_families":
            if not isinstance(val, list) or any(
                    not isinstance(x, str) or x not in LAYOUT_FAMILIES for x in val):
                errors.append(f"layout_families must be a list of {sorted(LAYOUT_FAMILIES)}")
        else:  # preferred/avoided_component_intents: slug tokens only
            if not isinstance(val, list) or any(
                    not isinstance(x, str) or _unsafe(x) or not _SLUG_RE.match(x) for x in val):
                errors.append(f"{key} must be a list of lowercase intent slugs")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a per-user slide style profile.")
    ap.add_argument("--profile", required=True, help="Path to a style-profile JSON.")
    args = ap.parse_args(argv)

    path = Path(args.profile)
    if not path.exists():
        print(f"ERROR: style profile not found: {path}", file=sys.stderr)
        return 1
    try:
        profile = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot parse {path}: {exc}", file=sys.stderr)
        return 1

    errors = validate_profile(profile)
    if errors:
        print(f"INVALID style profile: {path}")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"valid style profile: {profile.get('profile_id')} v{profile.get('version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
