#!/usr/bin/env python3
"""Refresh cached executable capabilities only when a probe is required."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _common import environment_fingerprint, load_json, now_iso, run_version, write_json


PROBES = {
    "node": {"names": ["node"], "args": ["--version"]},
    "python": {"names": ["python3", "python"], "args": ["--version"]},
    "xmllint": {"names": ["xmllint"], "args": ["--version"]},
    "libreoffice": {"names": ["soffice", "libreoffice"], "args": ["--version"]},
}


def find_executable(tool: dict, names: list[str]) -> str | None:
    configured = tool.get("path")
    if configured and Path(configured).exists():
        return configured
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        default=str(Path(__file__).resolve().parents[1] / "registries/capabilities.json"),
    )
    parser.add_argument("--check", default="all", help="Tool ID or all")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    registry = load_json(args.registry)
    paths = [tool.get("path") for tool in registry["tools"]]
    fingerprint = environment_fingerprint(paths)

    for tool in registry["tools"]:
        tool_id = tool["tool_id"]
        if args.check != "all" and args.check != tool_id:
            continue
        probe = PROBES.get(tool_id)
        if not probe:
            if tool.get("status") == "unknown":
                tool["environment_fingerprint"] = fingerprint
            continue
        path = find_executable(tool, probe["names"])
        must_refresh = any(
            [
                args.force,
                not tool.get("last_checked"),
                tool.get("environment_fingerprint") != fingerprint,
                not path,
                tool.get("last_failure") is not None,
            ]
        )
        if not must_refresh:
            continue
        tool["path"] = path
        tool["last_checked"] = now_iso()
        tool["environment_fingerprint"] = fingerprint
        if not path:
            tool["status"] = "unavailable"
            tool["version"] = None
            tool["last_failure"] = "Executable path was not found."
            continue
        ok, output = run_version(path, probe["args"])
        tool["status"] = "available" if ok else "unavailable"
        tool["version"] = output if ok else None
        tool["last_failure"] = None if ok else output
        if tool_id == "python" and ok:
            base = ["automation", "registry-tools"]
            pillow_ok, _ = run_version(
                path,
                ["-c", "import PIL; print(PIL.__version__)"],
            )
            tool["capabilities"] = base + (["image-analysis"] if pillow_ok else [])

    registry["environment_fingerprint"] = fingerprint
    registry["updated_at"] = now_iso()
    write_json(args.registry, registry)
    print(f"Updated {args.registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
