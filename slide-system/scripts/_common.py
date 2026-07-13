#!/usr/bin/env python3
"""Shared helpers for the slide-system command-line scripts."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_ROOT = SCRIPT_DIR.parent
REPO_ROOT = SYSTEM_ROOT.parent


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

