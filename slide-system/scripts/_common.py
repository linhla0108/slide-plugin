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

