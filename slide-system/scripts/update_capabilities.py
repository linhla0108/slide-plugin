#!/usr/bin/env python3
"""Refresh cached executable capabilities only when a probe is required."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _common import (
    environment_fingerprint,
    load_json,
    now_iso,
    project_python_install_hint,
    run_version,
    write_json,
)


PROBES = {
    "node": {"names": ["node"], "args": ["--version"]},
    "python": {"names": ["python3", "python"], "args": ["--version"]},
    "xmllint": {"names": ["xmllint"], "args": ["--version"]},
    "libreoffice": {"names": ["soffice", "libreoffice"], "args": ["--version"]},
}

# Tools that are provided by the Claude Code runtime environment itself —
# they have no CLI path but are always available when running inside Claude Code.
# update_capabilities.py must never mark these unavailable or unknown.
CLAUDE_CODE_BUILTINS = {
    "gen-pptx": {
        "capabilities": ["editable-pptx-export"],
        "note": "Claude Code built-in PPTX generator (gen_pptx function). "
                "Available in every Claude Code agent session without installation.",
    },
    "playwright-pdf": {
        "capabilities": ["html-to-pdf", "browser-print"],
        "note": "Playwright MCP browser-print. Available via the Claude Code "
                "Playwright MCP integration without extra installation.",
    },
}


def is_claude_code_environment() -> bool:
    """Return True when the script is running inside a Claude Code agent session.

    Heuristic: Claude Code caches its bundled runtimes under
    ~/.cache/codex-runtimes/. If that directory exists the user has launched
    Claude Code at least once and the built-in tools are present.
    """
    return (Path.home() / ".cache" / "codex-runtimes").exists()


SETUP_HINT = f"Run: {project_python_install_hint()}"


def standalone_script_status(
    spec: dict, node_path: str | None, python_path: str | None
) -> tuple[str, str | None, str | None]:
    """Return (status, path|None, failure|None) for a standalone script.

    Each spec declares what it `requires`:
      - "node"        → node available + node_modules installed (playwright).
                        Used by the JS capture/PDF scripts.
      - "python-pptx" → python can `import pptx`. Used by the python build
                        script (gating it on node_modules would be wrong — it
                        needs pip's python-pptx, not npm).

    Returns ("available", abs_path, None) or ("unavailable", None, reason).
    """
    script_path = REPO_ROOT / spec["script"]
    if not script_path.exists():
        return "unavailable", None, f"script not found: {spec['script']}"

    requires = spec.get("requires", "node")
    if requires == "node":
        if not node_path:
            return "unavailable", None, "node not found. Install Node.js 18+."
        if not (REPO_ROOT / "node_modules").is_dir():
            return "unavailable", None, f"npm deps not installed. {SETUP_HINT}"
        return "available", str(script_path), None
    if requires == "python-pptx":
        if not python_path:
            return "unavailable", None, "python not found."
        ok, _ = run_version(python_path, ["-c", "import pptx"])
        if not ok:
            return "unavailable", None, f"python-pptx not installed. {SETUP_HINT}"
        return "available", str(script_path), None
    return "unavailable", None, f"unknown requirement: {requires}"


# Repo root: two levels up from this script (scripts/ → slide-system/ → repo/)
REPO_ROOT = Path(__file__).resolve().parents[2]

# Standalone scripts that replace Claude Code built-ins for non-Claude users.
# Keyed by tool_id. When npm deps are installed, these are probed and registered
# as source "standalone-script" so check_requirements.py can use them.
STANDALONE_SCRIPTS = {
    "capture-slides": {
        "script": "slide-system/scripts/capture-slides.js",
        "requires": "node",
        "capabilities": ["slide-render-capture"],
        "note": "Standalone Playwright capture — STEP 1 of the non-Claude "
                "editable-pptx pipeline. Renders text-free slide backgrounds "
                "(hides editable text, keeps boxes) and extracts the DOM text "
                "layout (export-layout.json) that build-hybrid-pptx consumes. "
                f"{SETUP_HINT} to install.",
    },
    "build-hybrid-pptx": {
        "script": "slide-system/scripts/build_hybrid_pptx.py",
        "requires": "python-pptx",
        "capabilities": ["editable-pptx-export"],
        "note": "Standalone python-pptx hybrid PPTX builder — STEP 2 of the "
                "non-Claude pipeline. Overlays native editable text from "
                "capture-slides' export-layout.json onto the text-free "
                "backgrounds. Same proven math as the Phase 1 build "
                "(see scripts/_reference/build_v3_hybrid_editable.py). "
                f"{SETUP_HINT} to install.",
    },
    "playwright-pdf": {
        "script": "slide-system/scripts/export-pdf.js",
        "requires": "node",
        "capabilities": ["html-to-pdf", "browser-print"],
        "note": "Standalone Playwright PDF exporter. "
                f"{SETUP_HINT} to install.",
    },
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

    in_cc = is_claude_code_environment()

    # Resolve node path once — needed by standalone script probes.
    node_tool = next((t for t in registry["tools"] if t["tool_id"] == "node"), None)
    node_path = node_tool.get("path") if node_tool else None
    if not node_path:
        node_path = shutil.which("node")

    # Python path — needed by python-pptx standalone probes.
    python_tool = next((t for t in registry["tools"] if t["tool_id"] == "python"), None)
    python_path = python_tool.get("path") if python_tool else None
    if not python_path:
        python_path = shutil.which("python3") or shutil.which("python")

    for tool in registry["tools"]:
        tool_id = tool["tool_id"]
        if args.check != "all" and args.check != tool_id:
            continue

        # Standalone script (non-Claude path): probe whether npm deps are installed.
        # Prefer CC built-in when in_cc — standalone is only the fallback.
        if tool_id in STANDALONE_SCRIPTS and not in_cc:
            sa = STANDALONE_SCRIPTS[tool_id]
            status, script_path, failure = standalone_script_status(
                sa, node_path, python_path
            )
            tool["status"] = status
            tool["source"] = "standalone-script"
            tool["path"] = script_path
            tool["version"] = "standalone-script" if status == "available" else None
            tool["capabilities"] = sa["capabilities"]
            tool["last_checked"] = now_iso()
            tool["environment_fingerprint"] = fingerprint
            tool["last_failure"] = failure
            continue

        # Claude Code built-in: no CLI probe needed. Mark available when in CC;
        # keep existing status (do not downgrade) when outside CC so that the
        # registry stays valid when run from a CI or non-CC shell.
        if tool_id in CLAUDE_CODE_BUILTINS:
            builtin = CLAUDE_CODE_BUILTINS[tool_id]
            if in_cc or args.force:
                tool["status"] = "available"
                tool["source"] = "claude-code-builtin"
                tool["path"] = None
                tool["version"] = "claude-code-builtin"
                tool["capabilities"] = builtin["capabilities"]
                tool["last_checked"] = now_iso()
                tool["environment_fingerprint"] = fingerprint
                tool["last_failure"] = None
            else:
                # Outside CC: only update fingerprint, preserve status as-is.
                tool["environment_fingerprint"] = fingerprint
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
