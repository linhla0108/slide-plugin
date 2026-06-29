#!/usr/bin/env python3
"""Validate a slide job requirement file against cached capabilities."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import SYSTEM_ROOT, load_json, now_iso, resolve_repo_path, sha256_file, write_json


REQUIRED_KEYS = {
    "job_id",
    "brand_pack",
    "inputs",
    "authority",
    "exports",
    "editability",
    "required_tools",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", required=True)
    parser.add_argument(
        "--capabilities",
        default=str(Path(__file__).resolve().parents[1] / "registries/capabilities.json"),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    requirements = load_json(args.requirements)
    capabilities = load_json(args.capabilities)
    blockers: list[str] = []
    warnings: list[str] = []
    inputs: list[dict] = []

    # Host-aware staleness check. capabilities.json is checked in and may have
    # been probed on a different machine (its tool `path`s are absolute and
    # host-specific). If an "available" tool's recorded path does not exist on
    # THIS host, the cache cannot be trusted — surface a warning that points to
    # the refresh command rather than silently trusting a foreign fingerprint.
    stale_tools = {
        tool["tool_id"]
        for tool in capabilities.get("tools", [])
        if tool.get("status") == "available"
        and tool.get("path")
        and not Path(tool["path"]).exists()
    }
    if stale_tools:
        warnings.append(
            "Stale capabilities cache: recorded path missing on this host for "
            + ", ".join(sorted(stale_tools))
            + ". Refresh with `python3 slide-system/scripts/update_capabilities.py "
            "--force` before trusting tool availability."
        )

    missing_keys = sorted(REQUIRED_KEYS - set(requirements))
    if missing_keys:
        blockers.append(f"Missing required keys: {', '.join(missing_keys)}")

    for source in requirements.get("inputs", []):
        path = resolve_repo_path(source["path"])
        record = dict(source)
        record["resolved_path"] = str(path)
        record["format"] = path.suffix.lower().lstrip(".") or "directory"
        record["exists"] = path.exists()
        if path.exists() and path.is_file():
            actual_checksum = sha256_file(path)
            record["actual_checksum"] = actual_checksum
            if source.get("checksum") and source["checksum"] != actual_checksum:
                blockers.append(f"Checksum mismatch: {source['path']}")
        elif not path.exists():
            blockers.append(f"Missing input: {source['path']}")
        inputs.append(record)

    tool_map = {tool["tool_id"]: tool for tool in capabilities.get("tools", [])}
    tools: list[dict] = []
    for tool_id in requirements.get("required_tools", []):
        tool = tool_map.get(tool_id)
        if not tool:
            blockers.append(f"Required tool is not registered: {tool_id}")
            tools.append({"tool_id": tool_id, "status": "missing"})
            continue
        tools.append(tool)
        if tool["status"] != "available":
            blockers.append(f"Required tool is {tool['status']}: {tool_id}")
        elif tool_id in stale_tools:
            # An "available" tool whose cached path is missing on this host is
            # not actually usable here — block readiness, do not just warn.
            blockers.append(
                f"Required tool path is stale on this host: {tool_id} "
                f"({tool.get('path')}). Refresh capabilities "
                "(update_capabilities.py --force) before this job is ready."
            )

    if not requirements.get("exports"):
        blockers.append("At least one export format is required.")
    brand_manifest = SYSTEM_ROOT / "brand-packs" / requirements.get("brand_pack", "") / "manifest.json"
    brand_check = {"manifest": str(brand_manifest), "exists": brand_manifest.exists(), "references": []}
    if not brand_manifest.exists():
        blockers.append(f"Brand-pack manifest is missing: {requirements.get('brand_pack')}")
    else:
        brand = load_json(brand_manifest)
        for name, value in brand.get("canonical", {}).items():
            target = (brand_manifest.parent / value).resolve()
            exists = target.exists()
            brand_check["references"].append({"name": name, "path": str(target), "exists": exists})
            if not exists:
                blockers.append(f"Brand-pack reference is missing: {name}")

    unsupported_effects = requirements.get("unsupported_effects", [])
    if unsupported_effects:
        warnings.append(
            "Unsupported effects require a raster or approved fallback strategy: "
            + ", ".join(unsupported_effects)
        )

    required_workflows = [
        "check-requirements",
        "plan-slide-deck",
        "select-visual-items",
        "build-html-deck",
        "package-delivery",
    ]
    if "pptx-editable" in requirements.get("exports", []):
        required_workflows.extend(["export-editable-pptx", "verify-render-parity"])
    if "pdf" in requirements.get("exports", []):
        required_workflows.extend(["export-pdf", "verify-render-parity"])
    required_scripts = [
        "check_requirements.py",
        "score_visual_items.py",
        "package_job.py",
    ]
    for workflow in sorted(set(required_workflows)):
        if not (SYSTEM_ROOT / "workflows" / f"{workflow}.md").exists():
            blockers.append(f"Required workflow is missing: {workflow}")
    for script in required_scripts:
        if not (SYSTEM_ROOT / "scripts" / script).exists():
            blockers.append(f"Required script is missing: {script}")

    overrides = requirements.get("overrides", [])
    unresolved = [item for item in blockers if item not in overrides]
    if overrides:
        warnings.append("Overrides require explicit approval in the approval package.")

    report = {
        "job_id": requirements.get("job_id"),
        "checked_at": now_iso(),
        "status": "blocked" if unresolved else "ready",
        "inputs": inputs,
        "tools": tools,
        "blockers": blockers,
        "unresolved_blockers": unresolved,
        "warnings": warnings,
        "requested_overrides": overrides,
        "brand_pack": brand_check,
        "visual_needs": requirements.get("visual_needs", []),
        "unsupported_effects": unsupported_effects,
        "required_workflows": sorted(set(required_workflows)),
        "required_scripts": required_scripts,
    }
    write_json(args.output, report)
    print(report["status"])
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
