#!/usr/bin/env python3
"""build_log_index.py — Derive a machine-readable index from the human session
logs so agents can find relevant entries cheaply (one rtk grep/json pass) before
reading any prose.

Single source of truth = the prose `docs/logs/SESSION-LOG-<date>.md` files.
This script *derives* `docs/logs/INDEX.jsonl` from them; never edit INDEX.jsonl
by hand.

One JSON object per line:
  {"id","date","title","status","commit","files":[],"symbols":[],
   "supersedes":<id|null>,"log":"<relative path>"}

Usage:
  build_log_index.py --check   # exit 1 if INDEX.jsonl is stale vs the logs
  build_log_index.py --write   # regenerate INDEX.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# repo_root/slide-system/scripts/build_log_index.py -> repo_root
REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "docs" / "logs"
INDEX_PATH = LOGS_DIR / "INDEX.jsonl"

LOG_GLOB = "SESSION-LOG-*.md"
HEADING_RE = re.compile(r"^## +(?P<id>\S+) +— +(?P<title>.+?)\s*$")
DATE_IN_ID_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\.")
DATE_IN_NAME_RE = re.compile(r"SESSION-LOG-(?P<date>\d{4}-\d{2}-\d{2})\.md$")
FIELD_RE = re.compile(r"^\*\*(?P<key>When|Request|Result|Files|Symbols|State):\*\*\s*(?P<val>.*)$")
COMMIT_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
SUPERSEDED_RE = re.compile(r"SUPERSEDED by entry +(?P<id>\S+?)[\s:.]", re.IGNORECASE)


def _split_list(val: str) -> list[str]:
    """Split a comma/`/backtick-delimited field into clean tokens."""
    val = val.strip()
    if not val or val.lower() in {"none", "n/a", "-"}:
        return []
    parts = re.split(r"[,\s]+", val.replace("`", " "))
    return [p for p in (p.strip(" .;`") for p in parts) if p]


def _status_from_state(state: str) -> str:
    s = state.lower()
    if "not committed" in s or "uncommitted" in s:
        return "uncommitted"
    if "committed" in s:
        return "committed"
    return "unknown"


def _commit_from_state(state: str) -> str | None:
    # Only treat a bare hex token as a hash; phrases like "in entry 8's batch"
    # have no standalone hash and stay null.
    for m in COMMIT_RE.finditer(state):
        tok = m.group(1)
        # avoid matching short decimal-ish tokens that are pure digits
        if not tok.isdigit():
            return tok
    return None


def parse_log(path: Path) -> list[dict]:
    name_date = DATE_IN_NAME_RE.search(path.name)
    fallback_date = name_date.group("date") if name_date else None
    rel = path.relative_to(REPO_ROOT).as_posix()

    entries: list[dict] = []
    cur: dict | None = None
    section: str | None = None  # which **field** we are inside (for Actions multi-line)

    def flush() -> None:
        if cur is not None:
            entries.append(cur)

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")

        h = HEADING_RE.match(line)
        if h:
            flush()
            eid = h.group("id")
            d = DATE_IN_ID_RE.match(eid)
            cur = {
                "id": eid,
                "date": d.group("date") if d else fallback_date,
                "title": h.group("title").strip(),
                "status": "unknown",
                "commit": None,
                "files": [],
                "symbols": [],
                "supersedes": None,
                "log": rel,
            }
            section = None
            continue

        if cur is None:
            continue

        sup = SUPERSEDED_RE.search(line)
        if sup:
            cur["supersedes"] = cur["supersedes"]  # keep; this marks the OLD entry
            cur.setdefault("superseded_by", sup.group("id"))

        f = FIELD_RE.match(line)
        if f:
            key, val = f.group("key"), f.group("val")
            section = key
            if key == "Files":
                cur["files"] = _split_list(val)
            elif key == "Symbols":
                cur["symbols"] = _split_list(val)
            elif key == "State":
                cur["status"] = _status_from_state(val)
                cur["commit"] = _commit_from_state(val)
            continue

    flush()
    return entries


def build_index() -> list[dict]:
    out: list[dict] = []
    for log in sorted(LOGS_DIR.glob(LOG_GLOB)):
        out.extend(parse_log(log))
    return out


def serialize(entries: list[dict]) -> str:
    return "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in entries)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="exit 1 if INDEX.jsonl is stale")
    g.add_argument("--write", action="store_true", help="regenerate INDEX.jsonl")
    args = ap.parse_args()

    if not LOGS_DIR.is_dir():
        print(f"[build_log_index] no logs dir: {LOGS_DIR}", file=sys.stderr)
        return 1

    new = serialize(build_index())

    if args.write:
        INDEX_PATH.write_text(new, encoding="utf-8")
        n = new.count("\n")
        print(f"[build_log_index] wrote {n} entries -> {INDEX_PATH.relative_to(REPO_ROOT)}")
        return 0

    # --check
    old = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
    if old != new:
        print("[build_log_index] INDEX.jsonl is STALE — run: build_log_index.py --write", file=sys.stderr)
        return 1
    print("[build_log_index] INDEX.jsonl is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
