#!/usr/bin/env python3
"""Auto-stage Docling candidates as catalog Draft items.

This is the automation bridge from the Docling analysis pre-step to the existing
Draft review/publish surface:

  analysis/candidate-extraction-request.json
      -> deterministic semantic metadata
      -> approved single-item extraction requests
      -> scaffold_extraction.py
      -> optional core PDF artifact build
      -> catalog Drafts

It never publishes and never writes the shared registry. Publish remains a
human click from the Draft card.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from _common import REPO_ROOT, load_json, resolve_repo_path, write_json

import candidate_review as cr
import check_base_requirements as base_req
import scaffold_extraction as scaffold


SCRIPT_DIR = Path(__file__).resolve().parent
STOPWORDS = {
    "add", "approval", "approve", "auto",
    "a", "adipiscing", "amet", "an", "and", "are", "about", "by", "candidate", "consectetur",
    "detected", "docling", "dolor", "draft", "elit", "ipsum", "lorem",
    "detect", "descriptor", "for", "from", "in", "item", "of", "on", "or",
    "our", "publish", "region", "rename", "required", "sed", "semantic", "slide",
    "goes", "is", "so", "sub", "talk", "that", "the", "then", "this", "to", "was", "we", "were", "will", "with",
    "your", "here", "have", "has", "first", "next", "far",
    "anh", "buoc", "cac", "cho", "cua", "cung", "cuoi", "dai", "dau", "duoc",
    "gia", "han", "loi", "mot", "muc", "nhung", "noi", "phuc", "quyen",
    "trong", "tu", "va",
    "van",
}
ENGLISH_HINTS = {
    "achieved", "action", "agenda", "agent", "ai", "answer", "assistant", "assistants",
    "autocomplete", "benefits", "card", "check", "checklist", "coach",
    "circle", "circles", "coding", "collaborative", "company", "connect", "content", "contributors", "cover", "development",
    "do", "dont", "driver", "engagement", "factory", "faq", "framework", "goal",
    "highlight", "how", "improvement", "interview", "leadership", "level",
    "investment", "long", "management", "manager", "maturity", "member", "members", "metric", "networks", "next", "numbered", "overview", "performance",
    "people", "preparation", "process", "profile", "profiles", "quote", "recognition", "recruitment", "results", "revenue",
    "review", "rewards", "role", "salary", "section", "setting", "share",
    "size", "software", "statistics", "strategist", "structure", "subtitle", "summary",
    "stars", "team", "term", "thanks", "timeline", "title", "translator", "takeaway", "takeaways", "trip", "workshop", "grow",
}
LOCALIZED_HINTS = [
    ("sub tittle", ["subtitle"]),
    ("sub title", ["subtitle"]),
    ("luong phuc loi", ["salary", "benefits"]),
    ("phuc loi", ["benefits"]),
    ("mot buoc au tu", ["investment"]),
    ("mot buoc dau tu", ["investment"]),
    ("au tu", ["investment"]),
    ("dau tu", ["investment"]),
    ("quyen loi dai han", ["long", "term", "benefits"]),
    ("company trip", ["company", "trip"]),
    ("anh gia", ["review"]),
    ("tuyen dung", ["recruitment"]),
    ("phong van", ["interview"]),
    ("muc tieu", ["goal"]),
    ("chuan bi", ["preparation"]),
    ("cau truc", ["structure"]),
    ("dao sau", ["deep-dive"]),
    ("doi ngu", ["team"]),
    ("do va don", ["do", "dont"]),
    ("do va dont", ["do", "dont"]),
    ("quan ly", ["management"]),
]
TOKEN_ALIASES = {
    "tittle": "title",
}
LABEL_COMPONENT_TYPE = {
    "picture": "visual",
    "figure": "visual",
    "table": "table",
    "chart": "chart",
    "form": "form",
}
DATA_CHART_RE = re.compile(
    r"\b(?:pie|donut|bar|line|area|scatter|radar|mix|rating\s+scale)\s+chart\b"
    r"|\bchart\s+(?:candidate|layout|visualization|visualisation|region)\b",
    re.I,
)
SVG_ASSET_HREF_RE = re.compile(
    r"(?P<attr>(?:xlink:)?href=)(?P<quote>[\"'])"
    r"(?P<ref>(?:\.\./artifact/)?assets/(?P<name>[^\"']+))(?P=quote)"
)


class AutoStageError(Exception):
    """Auto-stage request cannot be completed safely."""


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _tokens(*values: object, limit: int = 7) -> list[str]:
    out: list[str] = []
    for value in values:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        for raw in re.findall(r"[A-Za-z0-9]+", ascii_value.lower()):
            raw = TOKEN_ALIASES.get(raw, raw)
            if raw in STOPWORDS or len(raw) < 2:
                continue
            if raw not in out:
                out.append(raw)
            if len(out) >= limit:
                return out
    return out


def _clean_lines(value: str) -> list[str]:
    lines: list[str] = []
    for raw in re.split(r"[\n|]+", value or ""):
        line = re.sub(r"\s+", " ", raw).strip()
        if line and line not in lines:
            lines.append(line)
    return lines


def _is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _ascii_words(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _localized_hint_tokens(value: str) -> list[str]:
    text = _ascii_words(value)
    out: list[str] = []
    for phrase, tokens in LOCALIZED_HINTS:
        if phrase in text:
            for token in tokens:
                if token not in out:
                    out.append(token)
    return out


def _english_lines(value: str) -> list[str]:
    lines: list[str] = []
    for line in _clean_lines(value):
        tokens = _tokens(line, limit=12)
        if not tokens:
            continue
        has_hint = any(token in ENGLISH_HINTS for token in tokens)
        is_short_label = (
            _is_ascii(line)
            and line.upper() == line
            and len(line) <= 32
            and re.search(r"[A-Za-z]", line)
        )
        if (has_hint or is_short_label) and line not in lines:
            lines.append(line)
    return lines


def _id_tokens_from_line(line: str, limit: int = 4) -> list[str]:
    tokens = _tokens(line, limit=limit)
    if _is_ascii(line):
        return tokens
    # Mixed Vietnamese/English source lines often contain one useful English
    # domain word ("goal", "team") surrounded by Vietnamese prose. Keep only
    # known English vocabulary for ids so accent-stripped Vietnamese fragments
    # never become stable component names.
    return [token for token in tokens if token in ENGLISH_HINTS]


def _level_series_tokens(lines: list[str]) -> list[str]:
    level_count = sum(1 for line in lines if re.search(r"\blevel\s+\d+\b", line, re.I))
    if level_count < 2:
        return []
    tokens: list[str] = []
    for line in lines:
        if re.search(r"\blevel\s+\d+\b", line, re.I):
            continue
        for token in _id_tokens_from_line(line, limit=5):
            if token in {"level", "levels"}:
                continue
            if token not in tokens:
                tokens.append(token)
        if len(tokens) >= 3:
            break
    if tokens:
        tokens.append("levels")
    return tokens


def _has_metric_signal(text: str) -> bool:
    return bool(re.search(r"[%$€£¥]|[+-]?\d+(?:[.,]\d+)?\s*(?:%|x)?", text, re.I))


def _metric_series_tokens(lines: list[str]) -> list[str]:
    text = " ".join(lines)
    if not _has_metric_signal(text):
        return []
    tokens: list[str] = []
    for line in lines:
        for token in _id_tokens_from_line(line, limit=5):
            if token.isdigit():
                continue
            if token not in tokens:
                tokens.append(token)
        if len(tokens) >= 3:
            break
    if not tokens:
        return []
    if "metric" not in tokens:
        tokens.append("metric")
    return tokens[:4]


def _icon_reference_signal(item: dict) -> bool:
    text = "\n".join([
        str(item.get("region_text") or ""),
        " ".join(str(v) for v in item.get("semantic_intent", [])),
        str(item.get("page_text") or ""),
    ])
    if not re.search(r"\bicons?\b", text, re.I):
        return False
    region = item.get("region", {})
    try:
        area = float(region.get("width", 0)) * float(region.get("height", 0))
    except (TypeError, ValueError):
        area = 0.0
    return area >= 0.02


def _source_topic_tokens(source_path: str, limit: int = 4) -> list[str]:
    tokens = _tokens(Path(source_path).stem, limit=8)
    generic = {
        "guidline", "guideline", "presentation", "sun", "suner", "sunriser",
        "studio", "slide", "kick", "off", "pdf",
    }
    topic = [token for token in tokens if token not in generic]
    topic = [token for token in topic if not token.isdigit()]
    return (topic or ["source"])[:limit]


def _role_suffix(item: dict, label: str) -> str:
    if label in {"table", "chart", "form"}:
        return label
    region = item.get("region", {})
    try:
        ratio = float(region.get("width", 0)) / max(float(region.get("height", 0)), 0.0001)
        area = float(region.get("width", 0)) * float(region.get("height", 0))
    except (TypeError, ValueError):
        ratio = 1.0
        area = 0.0
    if area < 0.008:
        return "icon"
    if ratio >= 1.8 and area >= 0.04 and _has_metric_signal(
        str(item.get("region_text") or "")):
        return "strip"
    if ratio >= 2.4:
        return "strip"
    if ratio <= 1.35:
        return "card"
    return "visual"


def _auto_stage_skip_reason(item: dict) -> str | None:
    """Return a reason when a detected candidate should not become a Draft."""
    original_id = str(item.get("item_id") or "")
    label = original_id.split("-", 1)[0].lower()
    if label == "chart":
        return "chart candidates are skipped by auto-detect"

    text = " ".join(
        str(value or "")
        for value in (
            original_id,
            item.get("notes"),
            item.get("region_text"),
            item.get("context_text"),
            " ".join(map(str, item.get("semantic_intent") or [])),
        )
    )
    if DATA_CHART_RE.search(text):
        return "data-chart regions are skipped by auto-detect"
    return None


def _region_band(value: float) -> int:
    return max(0, min(9, int(value / 0.1)))


def _size_band(value: float) -> str:
    if value < 0.18:
        return "tiny"
    if value < 0.75:
        return "small"
    return "large"


def _ratio_band(width: float, height: float) -> str:
    ratio = width / max(height, 0.0001)
    if ratio >= 2.2:
        return "wide"
    if ratio <= 0.7:
        return "tall"
    return "balanced"


def _pattern_region_profile(item: dict) -> tuple[int, int, str, str, str] | None:
    region = item.get("region") if isinstance(item.get("region"), dict) else {}
    try:
        x = float(region.get("x", 0))
        y = float(region.get("y", 0))
        width = float(region.get("width", 0))
        height = float(region.get("height", 0))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return (
        _region_band(x),
        _region_band(y),
        _size_band(width),
        _size_band(height),
        _ratio_band(width, height),
    )


def _pattern_text_profile(item: dict) -> tuple[int, tuple[int, ...]]:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("region_text"),
            item.get("context_text"),
            " ".join(map(str, item.get("semantic_intent") or [])),
        )
    )
    lines = _clean_lines(text)
    if not lines:
        return (0, ())
    if len(lines) <= 2:
        line_band = 1
    elif len(lines) <= 5:
        line_band = 2
    else:
        line_band = 3
    buckets: list[int] = []
    for line in lines[:2]:
        token_count = len(_tokens(line, limit=20))
        if token_count:
            if token_count <= 3:
                buckets.append(1)
            elif token_count <= 7:
                buckets.append(2)
            elif token_count <= 11:
                buckets.append(3)
            else:
                buckets.append(4)
    return (line_band, tuple(buckets[:2]))


def _duplicate_pattern_signature(source_path: str, item: dict) -> tuple | None:
    original_id = str(item.get("item_id") or "")
    label = original_id.split("-", 1)[0].lower() or "visual"
    role = _role_suffix(item, label)
    if role == "icon":
        return None
    if role in {"card", "strip", "visual"}:
        role = "component"
    region_profile = _pattern_region_profile(item)
    if region_profile is None:
        return None
    try:
        area = float((item.get("region") or {}).get("width", 0)) * float((item.get("region") or {}).get("height", 0))
    except (TypeError, ValueError):
        area = 0.0
    if area < 0.025:
        return None
    return (
        slug(Path(source_path).stem),
        role,
        region_profile,
        _pattern_text_profile(item),
    )


def _semantic_core(item: dict, suffix: str) -> list[str]:
    text = str(item.get("region_text") or "")
    raw_lines = _clean_lines(text)
    lines = _english_lines(text)
    localized = _localized_hint_tokens(text)
    ascii_text = _ascii_words(text)
    if "sub tittle" in ascii_text or "sub title" in ascii_text:
        return ["subtitle"]
    has_english_signal = any(
        _is_ascii(line)
        and any(token in ENGLISH_HINTS and token != "level"
                for token in _tokens(line, limit=8))
        for line in lines
    )
    if localized and not has_english_signal:
        return localized[:4]
    level_series = _level_series_tokens(raw_lines)
    if level_series:
        return level_series[:4]
    metric_series = _metric_series_tokens(raw_lines)
    if metric_series:
        return metric_series[:4]
    uppercase_labels = [
        line for line in lines
        if _is_ascii(line)
        and line.upper() == line
        and len(line) <= 36
        and re.search(r"[A-Za-z]", line)
    ]
    for line in reversed(uppercase_labels):
        label_tokens = _id_tokens_from_line(line, limit=4)
        if label_tokens and not all(token == "level" for token in label_tokens):
            return label_tokens
    for line in reversed(lines):
        label_tokens = _id_tokens_from_line(line, limit=4)
        if label_tokens and all(token == "level" for token in label_tokens):
            continue
        if (
            label_tokens
            and len(line) <= 36
            and re.search(r"[A-Za-z]", line)
            and _is_ascii(line)
            and (line.upper() == line or any(token in ENGLISH_HINTS for token in label_tokens))
            and line.lower() not in STOPWORDS
        ):
            return label_tokens
    english_tokens: list[str] = []
    for line in lines[:4]:
        for token in _id_tokens_from_line(line, limit=5):
            if token not in english_tokens:
                english_tokens.append(token)
        if len(english_tokens) >= 5:
            break
    return english_tokens[:5] or [suffix]


def _semantic_intent_core(item: dict, suffix: str) -> list[str]:
    intent = " ".join(str(value) for value in item.get("semantic_intent", []))
    tokens: list[str] = []
    for token in _tokens(intent, limit=20):
        if token not in ENGLISH_HINTS:
            continue
        if token in {suffix, "visual", "card", "strip", "table", "chart", "icon"}:
            continue
        if token not in tokens:
            tokens.append(token)
        if len(tokens) >= 4:
            break
    return tokens


def _context_core(item: dict, suffix: str) -> list[str]:
    """Best-effort semantic fallback before using the source filename.

    Prefer page-level headings and region text cues that are useful for
    retrieval, but keep lorem/filler and detector boilerplate out of stable ids.
    """
    parts = [
        str(item.get("page_text") or ""),
        str(item.get("region_text") or ""),
        " ".join(str(value) for value in item.get("semantic_intent", [])),
    ]
    text = "\n".join(parts)
    localized = _localized_hint_tokens(text)
    if localized:
        return localized[:4]
    role_tokens = {suffix, "visual", "card", "strip", "table", "chart", "icon", "form", "component", "source"}
    hinted: list[str] = []
    for token in _tokens(text, limit=40):
        if token in role_tokens or token.isdigit():
            continue
        if token in ENGLISH_HINTS and token not in hinted:
            hinted.append(token)
        if len(hinted) >= 4:
            return hinted
    if hinted:
        return hinted
    for line in _clean_lines(text):
        if re.search(r"\b(?:lorem|ipsum|candidate detected|docling|pymupdf)\b", line, re.I):
            continue
        tokens = [
            token for token in _tokens(line, limit=8)
            if token not in role_tokens and not token.isdigit()
        ]
        if tokens and (len(line) <= 64 or _is_ascii(line)):
            return tokens[:4]
    if _has_metric_signal(text):
        return ["metric"]
    return []


def _fallback_source_tokens(source_path: str, suffix: str, ordinal: str | None) -> list[str]:
    tokens = _source_topic_tokens(source_path)
    if tokens == ["source"]:
        tokens = ["detected", suffix]
    else:
        tokens = [*tokens, suffix]
    if ordinal:
        tokens.append(str(ordinal))
    return tokens


def semantic_item_id(source_path: str, item: dict, used: set[str]) -> str:
    original_id = str(item.get("item_id", ""))
    label = original_id.split("-", 1)[0] or "visual"
    source_stem = Path(source_path).stem
    source_slug = slug(source_stem) or "source"
    docling_match = re.match(
        r"^(?P<label>picture|figure|table|chart|form)-p(?P<page>[a-z0-9]+)-(?P<n>\d+)$",
        original_id,
    )
    if docling_match:
        if _icon_reference_signal(item):
            base = "icon-reference-sheet"
            candidate = base
            n = 2
            while candidate in used:
                candidate = f"{base}-{n}"
                n += 1
            used.add(candidate)
            return candidate
        if str(item.get("region_text") or "").strip():
            suffix = _role_suffix(item, label)
            core = _semantic_core(item, suffix)
            if core and core != [suffix]:
                base = slug("-".join([*core, suffix]))
            else:
                intent_core = _semantic_intent_core(item, suffix)
                if intent_core:
                    base = slug("-".join([*intent_core, suffix]))
                else:
                    context_core = _context_core(item, suffix)
                    ordinal = docling_match.group("n")
                    if context_core:
                        base = slug("-".join([*context_core, suffix]))
                    else:
                        base = slug("-".join(_fallback_source_tokens(source_path, suffix, ordinal)))
        else:
            suffix = _role_suffix(item, label)
            core = _semantic_intent_core(item, suffix)
            if core:
                base = slug("-".join([*core, suffix]))
            else:
                context_core = _context_core(item, suffix)
                ordinal = docling_match.group("n")
                if context_core:
                    base = slug("-".join([*context_core, suffix]))
                else:
                    base = slug("-".join(_fallback_source_tokens(source_path, suffix, ordinal)))
    else:
        intent = " ".join(str(v) for v in item.get("semantic_intent", []))
        notes = item.get("notes", "")
        parts = _tokens(source_stem, intent, notes, label)
        if label not in parts:
            parts.append(label)
        page = slug(str(item.get("slide_or_page") or ""))
        if page and f"p{page}" not in parts:
            parts.append(f"p{page}")
        base = slug("-".join(parts)) or "detected-visual"
    # Make sure the generated id passes the same scaffold gate as human names.
    if scaffold._BANNED_ID.match(base) or scaffold._DOCLING_DRAFT_ID.match(base):
        base = f"{slug(source_stem) or 'source'}-{label}-visual"
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def metadata_for(source_path: str, item: dict, item_id: str) -> dict:
    label = str(item.get("item_id", "")).split("-", 1)[0] or "visual"
    role_suffix = _role_suffix(item, label)
    component_type = role_suffix if role_suffix != "visual" else LABEL_COMPONENT_TYPE.get(label, label)
    if _icon_reference_signal(item):
        component_type = "icon"
        role_suffix = "icon"
    region_text = str(item.get("region_text") or "").strip()
    english_region_text = "\n".join(_english_lines(region_text))
    intent_values = [
        str(v).strip()
        for v in item.get("semantic_intent", [])
        if str(v).strip()
    ]
    if region_text:
        intent_values = [item_id.replace("-", " "), *intent_values]
    elif not intent_values:
        intent_values = [f"{component_type} from {Path(source_path).stem}"]
    intent_values = list(dict.fromkeys(intent_values))[:4]
    id_keywords = _tokens(item_id, label, limit=8)
    keywords = list(id_keywords)
    for token in _tokens(region_text, " ".join(intent_values), label, limit=16):
        if token in keywords:
            continue
        if token in ENGLISH_HINTS or token in id_keywords:
            keywords.append(token)
        if len(keywords) >= 8:
            break
    tags = [component_type, label, "docling", "auto-staged"]
    if component_type == "icon":
        tags.append("icon-set")
    display = item_id.replace("-", " ").title()
    text_note = f" Region cue: {_clean_lines(region_text)[:3]}." if region_text else ""
    return {
        "item_id": item_id,
        "display_name": display,
        "requested_type": item.get("requested_type", "component"),
        "component_type": component_type,
        "layout_role": (
            "icon reference sheet" if component_type == "icon"
            else f"{component_type} extracted from source region"
        ),
        "visual_summary": (
            f"Auto-staged {component_type} from page {item.get('slide_or_page')} "
            f"of {Path(source_path).name}.{text_note}"
        ),
        "semantic_intent": intent_values,
        "content_structure": [component_type, "text-bearing region" if region_text else "detected region"],
        "tags": tags,
        "keywords": keywords or [component_type],
        "use_cases": [f"Review and publish this {component_type} as a reusable component."],
        "anti_use_cases": ["Do not use before the Draft preview and metadata are reviewed."],
        "quality_notes": "Auto-generated from PDF text and Docling region; final approval happens in Draft.",
        "retrieval_notes": "Generated from region text, Docling label, source name, and page.",
    }


def _component_tokens(item_id: str) -> list[str]:
    role_suffixes = {"card", "strip", "icon", "table", "chart", "form", "visual", "component"}
    return [token for token in item_id.split("-") if token and token not in role_suffixes and not token.isdigit()]


def group_item_id(source_path: str, staged_records: list[dict], used: set[str]) -> str:
    child_ids = [str(record["review"]["item_id"]) for record in staged_records]
    child_tokens = [token for item_id in child_ids for token in _component_tokens(item_id)]
    has_cards = sum(item_id.endswith("-card") for item_id in child_ids) >= 2
    if has_cards:
        role_tokens = []
        for token in child_tokens:
            if token in ENGLISH_HINTS and token not in role_tokens:
                role_tokens.append(token)
            if len(role_tokens) >= 4:
                break
        base = "-".join([*(role_tokens or ["role"]), "card", "set"])
    else:
        base_tokens = []
        for token in child_tokens:
            if token in ENGLISH_HINTS and token not in base_tokens:
                base_tokens.append(token)
            if len(base_tokens) >= 4:
                break
        if not base_tokens:
            for token in child_tokens:
                if token in {"source", "detected"}:
                    continue
                if token not in base_tokens:
                    base_tokens.append(token)
                if len(base_tokens) >= 3:
                    break
        if not base_tokens:
            base_tokens = _fallback_source_tokens(source_path, "component", None)[:3]
        base = "-".join([*base_tokens, "component", "set"])
    candidate = slug(base)
    n = 2
    while candidate in used:
        candidate = f"{slug(base)}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def _tool_python() -> str:
    fitz_python, _fitz_path, _fitz_version = base_req.probe_fitz()
    return fitz_python or sys.executable


def _run_script(args: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        [_tool_python(), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    return proc.returncode == 0, (output + ("\n" + error if error else "")).strip()


def _chunks(values: list[Path], size: int) -> list[list[Path]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def _run_render_quality_gate(item_dirs: list[Path]) -> tuple[bool, dict]:
    unique: list[Path] = []
    seen: set[str] = set()
    for item_dir in item_dirs:
        key = str(Path(item_dir).resolve()).lower()
        if key in seen or not Path(item_dir).exists():
            continue
        seen.add(key)
        unique.append(Path(item_dir).resolve())
    summary = {
        "items": len(unique),
        "render_blank_refs_pruned": 0,
        "blank_item_visual": 0,
        "render_errors": 0,
        "parse_errors": 0,
    }
    if not unique:
        return True, summary
    ok_all = True
    for chunk in _chunks(unique, 40):
        args = ["slide-system/scripts/quality_gate.py", "--render-check"]
        for item_dir in chunk:
            args.extend(["--item-dir", str(item_dir)])
        ok, log = _run_script(args)
        ok_all = ok_all and ok
        if not log:
            continue
        try:
            payload = json.loads(log)
        except json.JSONDecodeError:
            summary["parse_errors"] += 1
            continue
        for item in payload.get("items") or []:
            summary["render_blank_refs_pruned"] += int(item.get("render_blank_refs_pruned") or 0)
            summary["render_errors"] += int(item.get("render_errors") or 0)
            if item.get("blank_item_visual"):
                summary["blank_item_visual"] += 1
    return ok_all, summary


def _extract_region_texts(source_path: str, items: list[dict]) -> dict[str, str]:
    source = resolve_repo_path(source_path)
    if source.suffix.lower() != ".pdf":
        return {}
    payload = {"source": str(source), "items": items}
    code = r"""
import json
import sys
import fitz

payload = json.loads(sys.stdin.read())
doc = fitz.open(payload["source"])
out = {}
for item in payload.get("items", []):
    try:
        page_no = int(item.get("slide_or_page", 1)) - 1
        page = doc[page_no]
        region = item["region"]
        if region.get("unit") == "normalized":
            rect = fitz.Rect(
                float(region["x"]) * page.rect.width,
                float(region["y"]) * page.rect.height,
                (float(region["x"]) + float(region["width"])) * page.rect.width,
                (float(region["y"]) + float(region["height"])) * page.rect.height,
            )
        else:
            rect = fitz.Rect(
                float(region["x"]),
                float(region["y"]),
                float(region["x"]) + float(region["width"]),
                float(region["y"]) + float(region["height"]),
            )
        text = page.get_text("text", clip=rect)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        out[str(item.get("item_id"))] = "\n".join(lines)
    except Exception:
        out[str(item.get("item_id"))] = ""
print(json.dumps(out, ensure_ascii=True))
"""
    try:
        proc = subprocess.run(
            [_tool_python(), "-c", code],
            cwd=str(REPO_ROOT),
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def _extract_page_texts(source_path: str, items: list[dict]) -> dict[str, str]:
    source = resolve_repo_path(source_path)
    if source.suffix.lower() != ".pdf":
        return {}
    pages = sorted({str(item.get("slide_or_page", 1)) for item in items})
    payload = {"source": str(source), "pages": pages}
    code = r"""
import json
import sys
import fitz

payload = json.loads(sys.stdin.read())
doc = fitz.open(payload["source"])
out = {}
for page_value in payload.get("pages", []):
    try:
        page_no = int(page_value) - 1
        text = doc[page_no].get_text("text")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        out[str(page_value)] = "\n".join(lines[:12])
    except Exception:
        out[str(page_value)] = ""
print(json.dumps(out, ensure_ascii=True))
"""
    try:
        proc = subprocess.run(
            [_tool_python(), "-c", code],
            cwd=str(REPO_ROOT),
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def _scaffold_request(request_path: Path, output_root: Path, history: Path,
                      registry: Path) -> None:
    old_argv = sys.argv[:]
    sys.argv = [
        "scaffold_extraction.py",
        "--request", str(request_path),
        "--output-root", str(output_root),
        "--history", str(history),
        "--registry", str(registry),
    ]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            scaffold.main()
    finally:
        sys.argv = old_argv


def _existing_stable_ids(output_root: Path) -> set[str]:
    stable_ids: set[str] = set()
    for mapping_path in output_root.glob("*/items/*/mapping.json"):
        try:
            mapping = load_json(mapping_path)
        except Exception:
            continue
        if mapping.get("status") == "skipped":
            continue
        stable_id = mapping.get("candidate_stable_id")
        if stable_id:
            stable_ids.add(str(stable_id))
    return stable_ids


def _used_item_ids(output_root: Path, registry: Path) -> set[str]:
    used: set[str] = set()
    for stable_id in _existing_stable_ids(output_root):
        if stable_id.startswith("sun.component."):
            used.add(stable_id.removeprefix("sun.component."))
    try:
        registry_data = load_json(registry)
    except Exception:
        registry_data = {"items": []}
    for item in registry_data.get("items", []):
        stable_id = str(item.get("id", ""))
        if stable_id.startswith("sun.component."):
            used.add(stable_id.removeprefix("sun.component."))
    return used


def _history_stable_id_for_item(history_data: dict, source_hash: str | None,
                                item: dict) -> str | None:
    if not source_hash:
        return None
    try:
        region = scaffold.normalized_bounds(item["region"])
        region_hash = scaffold.region_identity_hash(
            source_hash,
            item["slide_or_page"],
            region,
            item.get("object_ids", []),
        )
    except Exception:
        return None
    for attempt in history_data.get("attempts", []):
        if (
            attempt.get("region_identity_sha256") == region_hash
            and attempt.get("stable_id")
        ):
            return str(attempt["stable_id"])
    return None


def _augment_mapping(item_dir: Path, review: dict, run_id: str,
                     original_item: dict) -> None:
    mapping_path = item_dir / "mapping.json"
    mapping = load_json(mapping_path)
    if mapping.get("status") != "duplicate":
        mapping["candidate_stable_id"] = f"sun.component.{review['item_id']}"
    mapping["name"] = review["display_name"]
    mapping["component_type"] = review["component_type"]
    mapping["layout_role"] = review["layout_role"]
    mapping["visual_summary"] = review["visual_summary"]
    mapping["content_structure"] = review["content_structure"]
    mapping["tags"] = review["tags"]
    mapping["keywords"] = review["keywords"]
    mapping["use_cases"] = review["use_cases"]
    mapping["anti_use_cases"] = review["anti_use_cases"]
    mapping["quality_notes"] = review["quality_notes"]
    mapping["retrieval_notes"] = review["retrieval_notes"]
    mapping.setdefault("source", {})
    mapping["source"]["candidate_id"] = review["candidate_id"]
    mapping["source"]["docling_run_id"] = run_id
    mapping["source"]["docling_label"] = str(original_item.get("item_id", "")).split("-", 1)[0]
    mapping["review"] = {
        "mode": "auto-staged",
        "status": "draft_final_review_required",
        "review_surface": "catalog Draft",
    }
    write_json(mapping_path, mapping)


def _sync_history_stable_id(history: Path, extraction_id: str, item_id: str,
                            stable_id: str) -> None:
    if not history.exists():
        return
    history_data = load_json(history)
    updated = False
    for attempt in reversed(history_data.get("attempts", [])):
        if attempt.get("extraction_id") == extraction_id and attempt.get("item_id") == item_id:
            if attempt.get("stable_id") != stable_id:
                attempt["stable_id"] = stable_id
                history_data["updated_at"] = scaffold.now_iso()
                updated = True
            break
    if updated:
        write_json(history, history_data)


def _union_region(records: list[dict]) -> dict:
    regions = [record["item"].get("region", {}) for record in records]
    unit = regions[0].get("unit", "normalized") if regions else "normalized"
    xs = [float(region.get("x", 0)) for region in regions]
    ys = [float(region.get("y", 0)) for region in regions]
    x2s = [float(region.get("x", 0)) + float(region.get("width", 0)) for region in regions]
    y2s = [float(region.get("y", 0)) + float(region.get("height", 0)) for region in regions]
    x = min(xs) if xs else 0.0
    y = min(ys) if ys else 0.0
    x2 = max(x2s) if x2s else 1.0
    y2 = max(y2s) if y2s else 1.0
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "width": round(x2 - x, 6),
        "height": round(y2 - y, 6),
        "unit": unit,
    }


def _record_role(record: dict) -> str:
    item_id = str((record.get("review") or {}).get("item_id") or "")
    for suffix in ("card", "strip", "icon", "table", "chart", "form", "visual"):
        if item_id == suffix or item_id.endswith(f"-{suffix}"):
            return suffix
    original = str((record.get("item") or {}).get("item_id") or "")
    label = original.split("-", 1)[0] or "visual"
    return _role_suffix(record.get("item") or {}, label)


def _region_metric(record: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(((record.get("item") or {}).get("region") or {}).get(key, default))
    except (TypeError, ValueError):
        return default


def _record_center_y(record: dict) -> float:
    return _region_metric(record, "y") + (_region_metric(record, "height") / 2)


def _candidate_ordinal(record: dict) -> int:
    candidate_id = str(record.get("candidate_id") or (record.get("item") or {}).get("item_id") or "")
    match = re.match(r"^(?:picture|figure|table|chart|form)-p[a-z0-9]+-(\d+)$", candidate_id)
    if match:
        return int(match.group(1))
    return 1_000_000


def _sort_group_records(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda r: (
        _candidate_ordinal(r),
        _record_center_y(r),
        _region_metric(r, "x"),
    ))


def _split_layout_rows(records: list[dict]) -> list[list[dict]]:
    if len(records) < 2:
        return [records]
    rows: list[list[dict]] = []
    for record in sorted(records, key=lambda r: (_record_center_y(r), _region_metric(r, "x"))):
        center_y = _record_center_y(record)
        height = max(_region_metric(record, "height"), 0.001)
        if not rows:
            rows.append([record])
            continue
        current = rows[-1]
        current_centers = [_record_center_y(r) for r in current]
        current_heights = [max(_region_metric(r, "height"), 0.001) for r in current]
        row_center = sum(current_centers) / len(current_centers)
        threshold = max(0.12, min(0.22, max([height, *current_heights]) * 0.75))
        if abs(center_y - row_center) > threshold:
            rows.append([record])
        else:
            current.append(record)
    return rows


def _cluster_staged_records(staged_records: list[dict]) -> list[list[dict]]:
    """Return only related clusters that should become carousel Draft parents."""
    buckets: dict[tuple[str, str], list[dict]] = {}
    for record in staged_records:
        page = str((record.get("item") or {}).get("slide_or_page") or "")
        role = _record_role(record)
        buckets.setdefault((page, role), []).append(record)

    clusters: list[list[dict]] = []
    for (_page, _role), records in buckets.items():
        for row in _split_layout_rows(records):
            if len(row) >= 2:
                clusters.append(row)
    return clusters


def _same_file_bytes(left: Path, right: Path) -> bool:
    try:
        return left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def _copy_svg_with_assets(source_svg: Path, dest_svg: Path,
                          dest_assets_dir: Path, href_prefix: str) -> None:
    """Copy an item-local SVG into a new folder without breaking asset hrefs.

    Child item visuals reference `artifact/assets` as `assets/...`. Carousel
    manifests place those visuals under `artifact/components`, where the same
    relative href would point at a non-existent `components/assets` directory.
    Copy the referenced files into the parent artifact asset store and rewrite
    the SVG for its destination folder.
    """
    text = source_svg.read_text(encoding="utf-8")
    source_artifact_dir = source_svg.parent
    dest_svg.parent.mkdir(parents=True, exist_ok=True)
    dest_assets_dir.mkdir(parents=True, exist_ok=True)

    def replace(match: re.Match) -> str:
        name = match.group("name")
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            return match.group(0)
        source_assets_dir = (
            source_artifact_dir.parent / "artifact" / "assets"
            if match.group("ref").startswith("../artifact/")
            else source_artifact_dir / "assets"
        )
        source_asset = source_assets_dir / rel
        dest_rel = rel
        dest_asset = dest_assets_dir / dest_rel
        if source_asset.exists():
            if dest_asset.exists() and not _same_file_bytes(source_asset, dest_asset):
                stem = dest_rel.stem
                suffix = dest_rel.suffix
                parent = dest_rel.parent
                idx = 2
                while True:
                    candidate = parent / f"{stem}-{idx}{suffix}"
                    candidate_path = dest_assets_dir / candidate
                    if not candidate_path.exists() or _same_file_bytes(source_asset, candidate_path):
                        dest_rel = candidate
                        dest_asset = candidate_path
                        break
                    idx += 1
            dest_asset.parent.mkdir(parents=True, exist_ok=True)
            if not dest_asset.exists():
                shutil.copy2(source_asset, dest_asset)
        href = href_prefix + dest_rel.as_posix()
        return f"{match.group('attr')}{match.group('quote')}{href}{match.group('quote')}"

    dest_svg.write_text(SVG_ASSET_HREF_RE.sub(replace, text), encoding="utf-8")


def _materialize_group_item(
    extraction_id: str,
    source_path: str,
    staged_records: list[dict],
    output_root: Path,
    history: Path,
    registry: Path,
    used_ids: set[str],
    build_artifacts: bool,
) -> dict | None:
    if len(staged_records) < 2:
        return None
    staged_records = _sort_group_records(staged_records)
    group_id = group_item_id(source_path, staged_records, used_ids)
    group_extraction_id = f"{extraction_id}-{group_id}"
    group_dir = output_root / group_extraction_id
    item_dir = group_dir / "items" / group_id
    if (item_dir / "mapping.json").is_file():
        return {
            "item_id": group_id,
            "stable_id": f"sun.component.{group_id}",
            "extraction_id": group_extraction_id,
            "item_dir": str(item_dir),
            "status": "already_grouped",
        }

    slide_or_page = staged_records[0]["item"].get("slide_or_page", 1)
    union_region = _union_region(staged_records)
    group_request = {
        "extraction_id": group_extraction_id,
        "source_path": source_path,
        "items": [{
            "item_id": group_id,
            "slide_or_page": slide_or_page,
            "region": union_region,
            "object_ids": [],
            "requested_type": "component",
            "semantic_intent": [group_id.replace("-", " ")],
            "notes": "Auto-grouped overview for related Docling candidates.",
            "replacement_for": None,
        }],
    }
    analysis_dir = group_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    group_request_path = analysis_dir / "group-extraction-request.json"
    write_json(group_request_path, group_request)
    _scaffold_request(group_request_path, output_root, history, registry)
    artifact_status = "skipped"
    artifact_log = ""
    if build_artifacts:
        artifact_status, artifact_log = _build_pdf_artifacts(
            item_dir, source_path, slide_or_page)

    artifact_dir = item_dir / "artifact"
    components_dir = artifact_dir / "components"
    evidence_dir = item_dir / "evidence"
    preview_dir = item_dir / "preview"
    components_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    manifest_groups: list[dict] = []
    variants: list[str] = []
    children: list[dict] = []
    first_preview: Path | None = None
    for record in staged_records:
        child_item_dir = Path(record["item_dir"])
        child_id = record["review"]["item_id"]
        child_name = record["review"]["display_name"]
        preview = child_item_dir / "preview" / "thumbnail.png"
        if not preview.exists():
            preview = child_item_dir / "evidence" / "source-with-text.svg"
        if not preview.exists():
            continue
        suffix = preview.suffix.lower()
        variant_file = f"{child_id}{suffix}"
        shutil.copy2(preview, components_dir / variant_file)
        shutil.copy2(preview, artifact_dir / variant_file)
        if first_preview is None and suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            first_preview = preview
        cards: list[dict] = []
        text_free = child_item_dir / "artifact" / "visual.svg"
        if text_free.exists():
            text_free_file = f"{child_id}-text-free.svg"
            _copy_svg_with_assets(
                text_free, components_dir / text_free_file,
                artifact_dir / "assets", "../assets/")
            _copy_svg_with_assets(
                text_free, artifact_dir / text_free_file,
                artifact_dir / "assets", "assets/")
            cards.append({
                "title": f"{child_name} (Text-free)",
                "file": f"components/{text_free_file}",
                "member_count": 1,
            })
        manifest_groups.append({
            "group_id": child_id,
            "title": child_name,
            "file": f"components/{variant_file}",
            "member_count": 1,
            "cards": cards,
        })
        variants.append(child_name)
        children.append({
            "item_id": child_id,
            "stable_id": record["stable_id"],
            "item_dir": str(child_item_dir),
            "candidate_id": record["candidate_id"],
        })

    if len(manifest_groups) < 2:
        return None
    write_json(components_dir / "components-manifest.json", {"groups": manifest_groups})
    # _build_pdf_artifacts already rendered the grouped overview thumbnail.
    # Use a child preview only as a fallback for no-artifact runs.
    if first_preview and not (preview_dir / "thumbnail.png").exists():
        shutil.copy2(first_preview, preview_dir / "thumbnail.png")

    source = resolve_repo_path(source_path)
    source_hash = scaffold.sha256_file(source)
    region_hash = scaffold.region_identity_hash(source_hash, slide_or_page, union_region, [])
    stable_id = f"sun.component.{group_id}"
    display_name = group_id.replace("-", " ").title()
    keywords = _tokens(group_id, " ".join(variants), limit=10)
    existing_mapping = load_json(item_dir / "mapping.json")
    mapping = {
        "extraction_id": group_extraction_id,
        "item_id": group_id,
        "candidate_stable_id": stable_id,
        "name": display_name,
        "status": "staging",
        "type": "component",
        "category": "component-set",
        "brand": "sun-studio",
        "source": {
            "path": str(source),
            "sha256": source_hash,
            "slide_or_page": slide_or_page,
            "region": union_region,
            "object_ids": [],
            "docling_run_id": extraction_id,
            "candidate_ids": [record["candidate_id"] for record in staged_records],
        },
        "fingerprints": {
            "region_identity_sha256": region_hash,
            "semantic_signature_sha256": scaffold.semantic_signature_hash([group_id]),
            "perceptual_hash": None,
        },
        "semantic_intent": [display_name],
        "content_fields": {"required": [], "optional": []},
        "text_contract": existing_mapping.get("text_contract"),
        "variables": [],
        "variants": variants,
        "limitations": ["Review carousel variants before publishing this grouped component set."],
        "approval": {"status": "pending", "approved_by": None, "approved_at": None},
        "duplicate_of": None,
        "component_type": "component-set",
        "layout_role": "grouped carousel component set",
        "visual_summary": f"Grouped {len(manifest_groups)} related detected components from one source page.",
        "content_structure": ["component-set", "carousel variants"],
        "tags": ["component-set", "carousel", "docling", "auto-staged"],
        "keywords": keywords or ["component", "set"],
        "use_cases": ["Review and publish related visual variants as one reusable component set."],
        "anti_use_cases": ["Do not use before every carousel variant is reviewed."],
        "quality_notes": "Auto-grouped from related candidates on one source page.",
        "retrieval_notes": "Group metadata is generated from child component names and source page context.",
        "review": {
            "mode": "auto-staged-group",
            "status": "draft_final_review_required",
            "review_surface": "catalog Draft",
        },
        "collection_children": children,
        "artifact_status": artifact_status,
        "artifact_log": artifact_log,
    }
    write_json(item_dir / "mapping.json", mapping)
    evidence = [
        f"# Evidence - {group_id}",
        "",
        f"- Source: `{source}`",
        f"- Slide or page: `{slide_or_page}`",
        f"- Variants: {len(children)}",
        "",
    ]
    evidence.extend(f"- `{child['item_id']}` from `{child['item_dir']}`" for child in children)
    (evidence_dir / "notes.md").write_text("\n".join(evidence) + "\n", encoding="utf-8")

    for child in children:
        child_mapping_path = Path(child["item_dir"]) / "mapping.json"
        if child_mapping_path.exists():
            child_mapping = load_json(child_mapping_path)
            child_mapping["collection_parent_id"] = group_id
            child_mapping["collection_parent_stable_id"] = stable_id
            child_mapping["collection_parent_extraction_id"] = group_extraction_id
            write_json(child_mapping_path, child_mapping)

    history_data = load_json(history) if history.exists() else {"attempts": []}
    history_data.setdefault("attempts", []).append({
        "attempted_at": scaffold.now_iso(),
        "extraction_id": group_extraction_id,
        "item_id": group_id,
        "stable_id": stable_id,
        "status": "staging",
        "source_sha256": source_hash,
        "region_identity_sha256": region_hash,
        "semantic_signature_sha256": mapping["fingerprints"]["semantic_signature_sha256"],
    })
    history_data["updated_at"] = scaffold.now_iso()
    write_json(history, history_data)
    return {
        "item_id": group_id,
        "stable_id": stable_id,
        "extraction_id": group_extraction_id,
        "item_dir": str(item_dir),
        "status": "grouped",
        "variant_count": len(children),
        "artifact_status": artifact_status,
    }


def _build_pdf_artifacts(item_dir: Path, source_path: str, page: int | str) -> tuple[str, str]:
    source = resolve_repo_path(source_path)
    if source.suffix.lower() != ".pdf":
        return "skipped", "Core artifact build currently supports PDF sources."
    decompose_mode = _decompose_mode(item_dir)
    commands = [
        ["slide-system/scripts/convert_pdf_source.py", "--pdf", str(source), "--page", str(page), "--item-dir", str(item_dir)],
        ["slide-system/scripts/extract_editable_text_slots.py", "--item-dir", str(item_dir)],
        ["slide-system/scripts/crop_svg_region.py", "--item-dir", str(item_dir)],
        ["slide-system/scripts/externalize_svg_images.py", "--batch", str(item_dir.parents[1])],
        ["slide-system/scripts/optimize_svg.py", "--batch", str(item_dir.parents[1])],
        ["slide-system/scripts/apply_text_contract.py", "--batch", str(item_dir.parents[1])],
        ["slide-system/scripts/validate_text_slots.py", "--item-dir", str(item_dir)],
    ]
    if decompose_mode:
        classify_cmd = [
            "slide-system/scripts/classify_page_components.py",
            "--item-dir", str(item_dir),
            "--manifest-only",
        ]
        if decompose_mode == "layout-row-groups":
            classify_cmd.append("--layout-row-groups")
        commands.append(classify_cmd)
    if _is_icon_sheet_item(item_dir):
        commands.append(["slide-system/scripts/split_icon_sheet.py", "--item-dir", str(item_dir)])
    commands.append(["slide-system/scripts/quality_gate.py", "--item-dir", str(item_dir)])
    commands.append(["slide-system/scripts/generate_item_preview.py", "--item-dir", str(item_dir)])
    logs: list[str] = []
    for cmd in commands:
        ok, log = _run_script(cmd)
        logs.append(f"{Path(cmd[0]).name}: {'ok' if ok else 'failed'}")
        if log:
            logs.append(log)
        if not ok:
            return "failed", "\n".join(logs)
    return "ready", "\n".join(logs)


def _is_icon_sheet_item(item_dir: Path) -> bool:
    mapping_path = item_dir / "mapping.json"
    if not mapping_path.exists():
        return False
    try:
        mapping = load_json(mapping_path)
    except Exception:
        return False
    return mapping.get("component_type") == "icon"


def _decompose_mode(item_dir: Path) -> str | None:
    mapping_path = item_dir / "mapping.json"
    if not mapping_path.exists():
        return None
    try:
        mapping = load_json(mapping_path)
    except Exception:
        return None
    if mapping.get("component_type") == "strip":
        return "cards"
    region = (mapping.get("source") or {}).get("region") or {}
    try:
        area = float(region.get("width") or 0) * float(region.get("height") or 0)
    except (TypeError, ValueError):
        area = 0.0
    component_type = mapping.get("component_type")
    try:
        width = float(region.get("width") or 0)
        height = float(region.get("height") or 0)
    except (TypeError, ValueError):
        width = height = 0.0
    if component_type == "table" and area >= 0.10:
        return "layout-row-groups"
    if component_type in {"card", "component", "visual"} and (
        area >= 0.35 or (width >= 0.45 and height >= 0.18)
    ):
        return "layout-row-groups"
    return None


def stage_run(
    extraction_id: str,
    *,
    root: Path | None = None,
    output_root: Path | None = None,
    history: Path | None = None,
    registry: Path | None = None,
    rebuild_catalog: bool = True,
    build_artifacts: bool = True,
) -> dict:
    """Auto-stage every non-rejected Docling candidate in one analysis run."""
    root = (root or cr.extractions_root()).resolve()
    output_root = (output_root or cr.extractions_root()).resolve()
    history = (history or (REPO_ROOT / "slide-system/registries/extraction-history.json")).resolve()
    registry = (registry or (REPO_ROOT / "slide-system/registries/visual-library.json")).resolve()
    if not history.exists():
        write_json(history, {"attempts": []})
    adir = cr._analysis_dir(extraction_id, root)
    request = cr._load_request(adir)
    source_path = request.get("source_path", "")
    request_items = request.get("items", [])
    region_texts = _extract_region_texts(source_path, request_items)
    page_texts = _extract_page_texts(source_path, request_items)
    used_ids = _used_item_ids(output_root, registry)
    summary = {
        "extraction_id": extraction_id,
        "source_path": source_path,
        "staged": 0,
        "skipped": 0,
        "grouped": 0,
        "items": [],
    }
    existing_stable_ids = _existing_stable_ids(output_root)
    history_data = load_json(history) if history.exists() else {"attempts": []}
    try:
        source_hash = scaffold.sha256_file(resolve_repo_path(source_path))
    except Exception:
        source_hash = None
    items_by_id = {item.get("item_id"): item for item in request_items}
    staged_records: list[dict] = []
    pattern_representatives: dict[tuple, dict] = {}
    render_gate_item_dirs: list[Path] = []
    for original_id, item in items_by_id.items():
        if not original_id:
            continue
        item = dict(item)
        item["region_text"] = region_texts.get(str(original_id), "")
        item["page_text"] = page_texts.get(str(item.get("slide_or_page", "")), "")
        existing = (cr._load_reviews(adir).get(original_id) or {})
        if existing.get("review_status") == "rejected":
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "status": "skipped",
                "reason": "candidate rejected",
            })
            continue
        skip_reason = _auto_stage_skip_reason(item)
        if skip_reason:
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "status": "skipped",
                "reason": skip_reason,
            })
            continue
        pattern_signature = _duplicate_pattern_signature(source_path, item)
        item_page = str(item.get("slide_or_page") or "")
        representative = pattern_representatives.get(pattern_signature)
        if representative and representative.get("slide_or_page") != item_page:
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "status": "skipped_duplicate_pattern",
                "reason": "same component pattern already staged in this run",
                "duplicate_of_candidate_id": representative["candidate_id"],
                "duplicate_of_item_id": representative.get("item_id"),
                "duplicate_of_stable_id": representative.get("stable_id"),
            })
            continue
        history_stable_id = _history_stable_id_for_item(
            history_data, source_hash, item)
        if history_stable_id and history_stable_id in existing_stable_ids:
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "stable_id": history_stable_id,
                "status": "already_staged_region",
                "reason": "matching source/page/region already has a Draft",
            })
            if pattern_signature is not None:
                pattern_representatives[pattern_signature] = {
                    "candidate_id": original_id,
                    "slide_or_page": item_page,
                    "item_id": None,
                    "stable_id": history_stable_id,
                }
            continue
        item_id = semantic_item_id(source_path, item, used_ids)
        metadata = metadata_for(source_path, item, item_id)
        review = cr.save_review(extraction_id, original_id, metadata,
                                reviewer="auto-stage", root=root)
        result = cr.approve(extraction_id, original_id, reviewer="auto-stage", root=root)
        request_path = root / result["approved_request_path"]
        if not request_path.exists():
            request_path = Path(result["approved_request_path"])
        approved_request = load_json(request_path)
        staged_extraction_id = approved_request["extraction_id"]
        item_dir = output_root / staged_extraction_id / "items" / review["item_id"]
        if (item_dir / "mapping.json").is_file():
            existing_mapping = load_json(item_dir / "mapping.json")
            if existing_mapping.get("status") == "skipped":
                summary["skipped"] += 1
                summary["items"].append({
                    "candidate_id": original_id,
                    "item_id": review["item_id"],
                    "extraction_id": staged_extraction_id,
                    "item_dir": str(item_dir),
                    "status": "skipped_blank_text_free",
                    "reason": "text-free visual rendered blank; likely text-only region",
                })
                continue
            summary["skipped"] += 1
            summary["items"].append({
                "candidate_id": original_id,
                "item_id": review["item_id"],
                "extraction_id": staged_extraction_id,
                "item_dir": str(item_dir),
                "status": "already_staged",
            })
            if pattern_signature is not None:
                pattern_representatives[pattern_signature] = {
                    "candidate_id": original_id,
                    "slide_or_page": item_page,
                    "item_id": review["item_id"],
                    "stable_id": existing_mapping["candidate_stable_id"],
                }
            if not existing_mapping.get("collection_parent_id"):
                staged_records.append({
                    "candidate_id": original_id,
                    "item": item,
                    "review": review,
                    "item_dir": str(item_dir),
                    "stable_id": existing_mapping["candidate_stable_id"],
                })
            continue
        _scaffold_request(request_path, output_root, history, registry)
        _augment_mapping(item_dir, review, extraction_id, item)
        history_data = load_json(history) if history.exists() else {"attempts": []}
        stable_id = load_json(item_dir / "mapping.json")["candidate_stable_id"]
        existing_stable_ids.add(stable_id)
        artifact_status = "skipped"
        artifact_log = ""
        if build_artifacts:
            artifact_status, artifact_log = _build_pdf_artifacts(
                item_dir, source_path, item.get("slide_or_page", 1))
            if artifact_status != "failed":
                render_gate_item_dirs.append(item_dir)
        _sync_history_stable_id(history, staged_extraction_id, review["item_id"], stable_id)
        summary["staged"] += 1
        summary["items"].append({
            "candidate_id": original_id,
            "item_id": review["item_id"],
            "stable_id": stable_id,
            "extraction_id": staged_extraction_id,
            "item_dir": str(item_dir),
            "artifact_status": artifact_status,
            "artifact_log": artifact_log,
        })
        if pattern_signature is not None:
            pattern_representatives[pattern_signature] = {
                "candidate_id": original_id,
                "slide_or_page": item_page,
                "item_id": review["item_id"],
                "stable_id": stable_id,
            }
        staged_records.append({
            "candidate_id": original_id,
            "item": item,
            "review": review,
            "item_dir": str(item_dir),
            "stable_id": stable_id,
        })
    group_items: list[dict] = []
    for cluster in _cluster_staged_records(staged_records):
        grouped = _materialize_group_item(
            extraction_id,
            source_path,
            cluster,
            output_root,
            history,
            registry,
            used_ids,
            build_artifacts,
        )
        if grouped:
            group_items.append(grouped)
            if build_artifacts and grouped.get("status") == "grouped":
                render_gate_item_dirs.append(Path(grouped["item_dir"]))
    if group_items:
        summary["grouped"] = len(group_items)
        summary["group_items"] = group_items
        summary["group_item"] = group_items[0]
    if build_artifacts and render_gate_item_dirs:
        ok, render_summary = _run_render_quality_gate(render_gate_item_dirs)
        summary["quality_gate_render_checked"] = ok
        summary["quality_gate_render"] = render_summary
    if rebuild_catalog:
        ok, log = _run_script(["slide-system/scripts/build_component_catalog.py"])
        summary["catalog_rebuilt"] = ok
        if log:
            summary["catalog_log"] = log
    return summary


def list_runs() -> list[dict]:
    return cr.list_runs()


def compact_summary(summary: dict) -> dict:
    """Return a CLI-friendly summary without multi-line per-script logs."""
    out = dict(summary)
    compact_items: list[dict] = []
    for item in summary.get("items", []):
        compact = {k: v for k, v in item.items() if k != "artifact_log"}
        log = str(item.get("artifact_log") or "")
        if log:
            compact["artifact_log_lines"] = len(log.splitlines())
            compact["artifact_log_status"] = "see mapping.json artifact_log"
        compact_items.append(compact)
    out["items"] = compact_items
    if "catalog_log" in out:
        log = str(out["catalog_log"] or "")
        out["catalog_log_lines"] = len(log.splitlines())
        out.pop("catalog_log", None)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extraction_id", help="Docling analysis run to auto-stage.")
    parser.add_argument("--output-root", default=str(cr.extractions_root()))
    parser.add_argument("--history", default=str(REPO_ROOT / "slide-system/registries/extraction-history.json"))
    parser.add_argument("--registry", default=str(REPO_ROOT / "slide-system/registries/visual-library.json"))
    parser.add_argument("--no-artifacts", action="store_true",
                        help="Only scaffold Draft folders; do not run the PDF artifact chain.")
    parser.add_argument("--no-catalog", action="store_true",
                        help="Do not rebuild catalog-data.json after staging.")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full artifact logs in the JSON summary.")
    args = parser.parse_args(argv)
    try:
        summary = stage_run(
            args.extraction_id,
            root=Path(args.output_root),
            output_root=Path(args.output_root),
            history=Path(args.history),
            registry=Path(args.registry),
            rebuild_catalog=not args.no_catalog,
            build_artifacts=not args.no_artifacts,
        )
    except (cr.CandidateError, cr.CandidateValidationError, AutoStageError, SystemExit) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary if args.verbose else compact_summary(summary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
