#!/usr/bin/env python3
"""Shared helpers for the slide-system command-line scripts."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_ROOT = SCRIPT_DIR.parent
REPO_ROOT = SYSTEM_ROOT.parent


# T1 shape vocabulary — the SINGLE source of truth shared by
# score_visual_items.py (candidate eligibility, before ranking) and
# validate_selection_report.py (defense-in-depth shape-lock) so the scorer and
# validator can never drift. Each content_shape maps to the intent/tag tokens a
# chosen component must carry; matched case-insensitively against the item's
# intent + tags. Synonyms keep the map lenient on phrasing but strict on
# category (a `timeline` shape can never lock to a `cover` item). Every token is
# drawn from real published-item intent/tags or the scorer's canonical
# vocabulary — do not add generic filler words.
SHAPE_TYPE_MAP: dict[str, set[str]] = {
    "cover": {"cover", "hero", "title", "opening", "intro"},
    "stats": {"statistics", "data", "metrics", "kpi", "numbers", "figures", "grid"},
    "comparison": {"comparison", "versus", "do-dont", "what-how", "pros-cons", "contrast"},
    "timeline": {"timeline", "schedule", "roadmap", "process", "milestones", "phases", "instructions"},
    "checklist": {"checklist", "preparation", "steps", "action-items", "todo", "requirements"},
    "two-column": {"two-column", "split", "split-layout", "layout"},
    "profile": {"team", "profile", "profile-layout", "profile-circles", "contributors", "roles", "personas"},
    "tiers": {"levels", "tiers", "ranking", "maturity-model", "capability-ladder"},
    "icons": {"icons", "icon-reference", "icon-library", "reference-sheet", "glyph-grid"},
    "review": {"review", "check-in", "evaluation", "assessment", "questions", "quarterly-review", "progress-check"},
    "closing": {"closing", "thank-you", "farewell", "conclusion", "outro"},
}


def shape_eligible(content_shape: str | None, tokens) -> bool:
    """Whether an item carrying `tokens` (its intent + tags) may serve a slide's
    `content_shape`. Shared by the scorer (candidate eligibility) and the
    validator (shape-lock) so both apply one rule.

    - No content_shape declared -> True (filtering is a no-op; backward compatible).
    - Known shape -> True iff the item shares at least one allowed token.
    - Unknown shape (not in SHAPE_TYPE_MAP) -> False: no component can lock to a
      shape the system has no vocabulary for, so the scorer falls back to
      custom-local instead of emitting a reuse the validator would reject.
    """
    if not content_shape:
        return True
    allowed = SHAPE_TYPE_MAP.get(content_shape)
    if not allowed:
        return False
    return bool(allowed & {str(t).lower() for t in tokens})


# Content capacity — how many DISTINCT content items a component can actually
# hold, derived from its own text-slot contract (the artifact the scaffolder
# fills and the fidelity gate measures, i.e. the operational truth). Shared by
# build_component_retrieval_index.py (which bakes the number into the index) and
# the tests, so one rule defines capacity everywhere.
#
# Why not the metadata: `component_type`/`layout_role` are populated on a small
# minority of items and `set_sizes` on none; declared `content_structure` is well
# populated but over-tagged for this purpose (single-headline CTA slides declare
# `list-item`). Why not `slot_count`: it measures MARKUP, not capacity — such a
# CTA can be 8 slots, of which 5 are page furniture and 3 are one wrapped sentence.
#
# Bounds are normalized (0..1) per the text-slots contract.
CHROME_MAX_HEIGHT = 0.030   # page furniture is small type…
CHROME_TOP = 0.10           # …and lives in the header…
CHROME_BOTTOM = 0.90        # …or footer margin band.
BLOCK_MERGE_TOLERANCE = 0.012  # slots this close read as ONE block of copy.


def _slot_rect(slot: dict) -> tuple[float, float, float, float] | None:
    b = (slot or {}).get("bounds") or {}
    try:
        x, y = float(b.get("x", 0)), float(b.get("y", 0))
        w, h = float(b.get("width", 0)), float(b.get("height", 0))
    except (TypeError, ValueError):
        return None
    return (x, y, w, h) if w > 0 and h > 0 else None


def is_chrome_slot(slot: dict) -> bool:
    """Page furniture — logo, page number, footer, section label: small type in the
    header/footer margin band. It repeats on every slide of a deck, so it is not
    capacity for the slide's own content."""
    rect = _slot_rect(slot)
    if rect is None:
        return False
    _, y, _, h = rect
    return h <= CHROME_MAX_HEIGHT and (y < CHROME_TOP or y + h > CHROME_BOTTOM)


def _rects_touch(a: tuple, b: tuple, tol: float) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw + tol < bx or bx + bw < ax - tol
                or ay + ah + tol < by or by + bh < ay - tol)


def content_blocks(slots) -> int:
    """The number of distinct content blocks in a text-slot contract == how many
    separate content items the component can hold.

    Chrome is excluded, then the remaining slots are merged when their boxes sit
    within `BLOCK_MERGE_TOLERANCE`: a headline wrapped across several slots
    collapses to ONE block, while list/card rows separated by real gaps stay
    distinct. So a CTA slide scores 1 no matter how many fragments its headline is
    split into, and a checklist scores its true number of items.
    """
    rects = [r for r in (_slot_rect(s) for s in (slots or [])
                         if not is_chrome_slot(s)) if r is not None]
    parent = list(range(len(rects)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if _rects_touch(rects[i], rects[j], BLOCK_MERGE_TOLERANCE):
                parent[find(i)] = find(j)
    return len({find(i) for i in range(len(rects))})


def derive_content_shape(tokens) -> list[str]:
    """Deterministically infer which content_shape(s) an item fits from its own
    intent/tags, by reverse-lookup on SHAPE_TYPE_MAP. Returns every shape whose
    allowed vocabulary the item shares (sorted; may be empty). This is the generic,
    zero-churn derivation the scorer reports for auditability — the system reasons
    about an item's shape from its existing metadata, so no shape label is invented
    and stored on the 91 registry items."""
    toks = {str(t).lower() for t in tokens}
    return sorted(shape for shape, allowed in SHAPE_TYPE_MAP.items() if allowed & toks)


class ProjectPythonError(RuntimeError):
    """Raised when the repository virtualenv is missing or unusable."""


def project_python_path(repo_root: str | Path = REPO_ROOT,
                        os_name: str | None = None) -> Path:
    """Return the platform-specific Python path inside the project virtualenv."""
    platform_name = os.name if os_name is None else os_name
    relative = Path("Scripts/python.exe") if platform_name == "nt" else Path("bin/python3")
    return Path(repo_root) / ".venv" / relative


def project_python_install_hint(os_name: str | None = None) -> str:
    platform_name = os.name if os_name is None else os_name
    if platform_name == "nt":
        return r"powershell -ExecutionPolicy Bypass -File .\slide-system\scripts\setup.ps1"
    return "./slide-system/scripts/setup.sh"


def require_project_python(repo_root: str | Path = REPO_ROOT,
                           os_name: str | None = None,
                           required_modules: tuple[str, ...] = ()) -> Path:
    """Return a usable project Python or raise with the platform setup command."""
    python = project_python_path(repo_root, os_name)
    platform_name = os.name if os_name is None else os_name
    display = (r".venv\Scripts\python.exe" if platform_name == "nt"
               else ".venv/bin/python3")
    hint = project_python_install_hint(platform_name)
    if not python.is_file():
        raise ProjectPythonError(
            f"Project Python is missing at {display}. Run: {hint}"
        )

    imports = "; ".join(f"import {module}" for module in required_modules)
    code = f"{imports}; print('ok')" if imports else "print('ok')"
    try:
        probe = subprocess.run(
            [str(python), "-c", code],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProjectPythonError(
            f"Project Python at {display} is not usable ({exc}). Run: {hint}"
        ) from exc
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or f"exit {probe.returncode}").strip().splitlines()
        suffix = detail[-1] if detail else f"exit {probe.returncode}"
        modules = f" with required modules {', '.join(required_modules)}" if required_modules else ""
        raise ProjectPythonError(
            f"Project Python at {display} is not usable{modules}: {suffix}. Run: {hint}"
        )
    return python


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_json_atomic(path: str | Path, data: Any) -> None:
    """Write JSON to *path* using an atomic temporary-file + os.replace.

    The temp file is created beside the final path so the rename stays on
    the same filesystem (required for os.replace to work atomically).  On
    failure the temp file is cleaned up; the destination is never touched.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".tmp.{target.name}.{os.getpid()}"
    try:
        content = json.dumps(data, ensure_ascii=True, indent=2) + "\n"
        with tmp.open("w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(target))
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_jsonl_atomic(path: str | Path, records: list[dict]) -> None:
    """Write JSONL records atomically using temp-file + os.replace.

    Preserves deterministic JSONL formatting (sorted keys, one record
    per line, trailing newline, \\n line endings).  On failure the temp
    file is cleaned up and the destination is never touched.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".tmp.{target.name}.{os.getpid()}"
    try:
        content = "".join(
            json.dumps(r, ensure_ascii=True, sort_keys=True) + "\n"
            for r in records
        )
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(target))
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def snapshot_path(path: Path) -> tuple[bool, bytes] | None:
    """Snapshot whether *path* existed and its original bytes.

    Returns ``(existed, original_bytes)`` or ``None`` if the path did
    not exist (caller uses this to decide whether to remove or restore).
    """
    try:
        if path.exists():
            return (True, path.read_bytes())
    except OSError:
        pass
    return None


def restore_path(path: Path, snapshot: tuple[bool, bytes] | None) -> None:
    """Restore *path* to the exact state from *snapshot*.

    When the snapshot says the path originally did not exist, the path
    is removed (if it exists now).  When it did exist, the original
    bytes are written back exactly.
    """
    if snapshot is None:
        path.unlink(missing_ok=True)
        return
    existed, original_bytes = snapshot
    path.parent.mkdir(parents=True, exist_ok=True)
    if existed:
        path.write_bytes(original_bytes)
    else:
        path.unlink(missing_ok=True)


def replace_dir_atomically(src: Path, dst: Path) -> Path | None:
    """Swap *src* (a fully-written temp directory) into *dst*.

    Returns the backup path (or ``None`` when *dst* did not exist before
    the swap).  The caller is responsible for deleting the backup after
    all subsequent operations succeed, or restoring it on failure.

    If *dst* exists it is first moved to a backup sibling so the
    destination is never empty or partially written — even if the
    rename of *src* fails, the backup is restored.  Works on Windows and
    POSIX (uses ``os.rename`` which is the same-filesystem atomic
    directory rename available on both).
    """
    backup = dst.parent / f"{dst.name}.backup.{os.getpid()}"
    if backup.exists():
        shutil.rmtree(backup)
    if dst.exists():
        os.rename(str(dst), str(backup))
    else:
        backup = None
    try:
        os.rename(str(src), str(dst))
    except BaseException:
        if backup and backup.exists():
            os.rename(str(backup), str(dst))
        raise
    return backup


def restore_dir_from_backup(dst: Path, backup: Path) -> None:
    """Restore *dst* from *backup*, removing the current *dst* if any."""
    if dst.exists():
        shutil.rmtree(dst)
    os.rename(str(backup), str(dst))


def quarantine_path(path: Path) -> Path:
    """Return a sibling quarantine path for *path* (``.quarantine.<pid>``)."""
    return path.parent / f"{path.name}.quarantine.{os.getpid()}"


def _ownership_token() -> str:
    """Return a unique, verifiable ownership token for this process."""
    return f"{socket.gethostname()}:{os.getpid()}:{time.time_ns()}"


def library_mutation_lock(lock_dir: Path) -> str | None:
    """Acquire an exclusive, cross-platform file-system mutex.

    Returns an ownership token (opaque ``str``) on success, or ``None``
    when another live process holds the lock.

    The lock is a single file created with ``O_CREAT | O_EXCL`` — the
    only truly exclusive file creation primitive on both Windows and
    POSIX (``os.rename`` replaces existing files on POSIX).

    The lock file contains an ownership token (``hostname:pid:ns``).
    Stale locks are detected by parsing the owner PID from the token
    and checking whether it is still alive.  Stale locks are reaped
    transparently.
    """
    lock_dir.mkdir(parents=True, exist_ok=True)
    anchor = lock_dir / ".lock"
    token = _ownership_token()
    try:
        fd = os.open(str(anchor), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        # Lock held — check for staleness.
        stale = False
        try:
            raw = anchor.read_bytes().decode("utf-8")
            parts = raw.split(":")
            owner_pid = int(parts[1]) if len(parts) >= 2 else 0
            if not owner_pid or not _pid_alive(owner_pid):
                stale = True
        except (OSError, ValueError, IndexError):
            stale = True
        if stale:
            anchor.unlink(missing_ok=True)
            return library_mutation_lock(lock_dir)  # retry
        return None
    try:
        os.write(fd, token.encode("utf-8"))
    finally:
        os.close(fd)
    return token


def library_mutation_unlock(lock_dir: Path, token: str) -> None:
    """Release the mutation lock owned by *token*.

    If the lock file no longer contains *token* (another process reaped
    it, or this is not the owner), the unlock is a no-op.  This prevents
    accidentally removing another process's lock.
    """
    anchor = lock_dir / ".lock"
    try:
        current = anchor.read_bytes().decode("utf-8")
    except (OSError, ValueError):
        return
    if current.strip() == token.strip():
        anchor.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    """Check whether *pid* is still running (cross-platform)."""
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    # POSIX
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


_MUTEX_DIR: Path | None = None


def mutex_dir() -> Path:
    """Return the single repo-local mutex directory (lazy)."""
    global _MUTEX_DIR
    if _MUTEX_DIR is None:
        _MUTEX_DIR = SYSTEM_ROOT / ".library-mutation.lock.d"
    return _MUTEX_DIR


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def environment_fingerprint(paths: list[str | None] | None = None) -> str:
    payload = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "path": os.environ.get("PATH", ""),
        "tools": [],
    }
    for raw_path in paths or []:
        if not raw_path:
            continue
        path = Path(raw_path)
        payload["tools"].append(
            {
                "path": str(path),
                "exists": path.exists(),
                "mtime_ns": path.stat().st_mtime_ns if path.exists() else None,
                "size": path.stat().st_size if path.exists() else None,
            }
        )
    return sha256_text(json.dumps(payload, sort_keys=True))


def run_version(path: str, args: list[str], timeout: int = 10) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [path, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (result.stdout or result.stderr).strip()
    first_line = output.splitlines()[0] if output else f"exit {result.returncode}"
    return result.returncode == 0, first_line


def resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def normalized_bounds(region: dict[str, Any]) -> dict[str, Any]:
    return {
        "x": round(float(region["x"]), 6),
        "y": round(float(region["y"]), 6),
        "width": round(float(region["width"]), 6),
        "height": round(float(region["height"]), 6),
        "unit": region["unit"],
    }


def prune_empty_dirs(root: str | Path) -> list[Path]:
    """Remove empty directories under root (deepest first). Returns removed paths.

    LLM sessions tend to scaffold folder trees ahead of content; anything still
    empty at packaging/cleanup time is scaffolding noise, not output.
    """
    root = Path(root)
    removed: list[Path] = []
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()
            removed.append(path)
        except OSError:
            continue
    return removed


def region_identity_hash(
    source_sha256: str,
    slide_or_page: str | int,
    region: dict[str, Any],
    object_ids: list[str] | None = None,
) -> str:
    identity = {
        "source_sha256": source_sha256,
        "slide_or_page": str(slide_or_page),
        "region": normalized_bounds(region),
        "object_ids": sorted(object_ids or []),
    }
    return sha256_text(json.dumps(identity, sort_keys=True))


def semantic_signature_hash(intents: list[str]) -> str:
    return sha256_text("|".join(sorted(v.lower() for v in intents)))


def average_image_hash(path: str | Path) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(path) as image:
        gray = image.convert("L").resize((8, 8))
        pixels = list(gray.getdata())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"

