#!/usr/bin/env python3
"""Local control server for the visual-library catalog.

Serves the catalog (and all repo-relative assets) exactly like
`python3 -m http.server`, plus two POST endpoints that mutate the real repo
on this machine:

    POST /api/publish  {id}          -> build preview/, approve, promote into library,
                                        then remove the redundant staging copy
    POST /api/delete   {id, status}  -> remove a published (library) or draft item

After every mutation the catalog data is regenerated so the page can reload.

Binds to 127.0.0.1 only. This is a local authoring tool, not a public service.

Run from the repo root:
    python3 slide-system/catalog/catalog_server.py
then open http://127.0.0.1:8799/slide-system/catalog/
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "slide-system" / "scripts"
REGISTRY = REPO_ROOT / "slide-system" / "registries" / "visual-library.json"
LIBRARY = REPO_ROOT / "slide-system" / "library"
EXTRACTIONS = REPO_ROOT / "outputs" / "component-extractions"
ID_PATTERN = re.compile(r"^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+$")
HOST = "127.0.0.1"
PORT = 8799


# ---------- helpers ----------

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode == 0, (out + ("\n" + err if err else "")).strip()


def regen_catalog() -> tuple[bool, str]:
    return run([sys.executable, str(SCRIPTS / "build_component_catalog.py")])


def regen_compact() -> tuple[bool, str]:
    # Keep visual-library-compact.json (the scorer's registry) in lockstep after
    # a registry mutation. publish goes through publish_extraction.py which already
    # does this; the published-delete path edits the registry inline, so it must
    # reproject the compact here or the scorer drifts.
    return run([sys.executable, str(SCRIPTS / "build_registry.py"), "--write"])


def within_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def find_staging(item_id: str):
    """Locate a draft item dir by stable id. Returns (item_dir, batch_dir, folder) or None."""
    if not EXTRACTIONS.exists():
        return None
    for mapping_path in EXTRACTIONS.glob("*/items/*/mapping.json"):
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ids = {mapping.get("candidate_stable_id"), mapping.get("id"), mapping_path.parent.name}
        if item_id in ids:
            item_dir = mapping_path.parent
            return item_dir, item_dir.parent.parent, item_dir.name
    return None


def find_published(item_id: str):
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for entry in registry.get("items", []):
        if entry.get("id") == item_id:
            return registry, entry
    return registry, None


def prune_staging(item_dir: Path) -> None:
    """Remove a published item's staging copy and any dirs it leaves empty."""
    if not (within_repo(item_dir) and EXTRACTIONS in item_dir.parents):
        return
    if item_dir.is_dir():
        shutil.rmtree(item_dir)
    items_dir = item_dir.parent          # <batch>/items
    batch_dir = items_dir.parent         # <batch>
    for d in (items_dir, batch_dir):
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


# ---------- actions ----------

def action_publish(item_id: str) -> tuple[int, dict]:
    found = find_staging(item_id)
    if not found:
        return 404, {"ok": False, "error": f"Draft item not found: {item_id}"}
    item_dir, batch_dir, folder = found

    # Author the publish-grade preview/ on demand if the extraction didn't.
    # This keeps the user flow to a single click: review -> Publish -> done.
    preview_dir = item_dir / "preview"
    if not preview_dir.is_dir() or not any(preview_dir.iterdir()):
        ok, log = run([sys.executable, str(SCRIPTS / "generate_item_preview.py"),
                       "--item-dir", str(item_dir)])
        if not ok:
            return 500, {"ok": False, "error": "Could not build a preview for this item.", "log": log}

    # The deliberate Publish click is the explicit human approval.
    mapping_path = item_dir / "mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping["approval"] = {
        "status": "approved",
        "approved_by": "catalog-ui",
        "approved_at": now_iso(),
    }
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    ok, log = run([sys.executable, str(SCRIPTS / "publish_extraction.py"),
                   "--extraction-dir", str(batch_dir), "--item-id", folder])
    if not ok:
        return 500, {"ok": False, "error": "Publish failed", "log": log}

    # Staging copy is now redundant — the artifacts live in library/. Remove it
    # and prune the emptied items/ and batch dirs (outputs/ is gitignored).
    prune_staging(item_dir)
    regen_catalog()
    return 200, {"ok": True, "message": "Published to library", "log": log}


def action_delete(item_id: str, status: str) -> tuple[int, dict]:
    if status == "published":
        registry, entry = find_published(item_id)
        if not entry:
            return 404, {"ok": False, "error": f"Published item not found: {item_id}"}
        artifact = entry.get("paths", {}).get("artifact")
        # Hard guard: only items owned by the library may be deleted. Canonical
        # assets (logo, Dio) live under .agents/ and are protected by AGENTS.md.
        if not artifact or not artifact.startswith("slide-system/library/"):
            return 403, {"ok": False, "error": "This item is a protected/canonical asset and cannot be deleted here."}
        target = (REPO_ROOT / artifact).resolve()
        if not (within_repo(target) and LIBRARY in target.parents):
            return 403, {"ok": False, "error": "Refusing to delete outside the library."}
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
        registry["items"] = [i for i in registry["items"] if i.get("id") != item_id]
        registry["updated_at"] = now_iso()
        REGISTRY.write_text(json.dumps(registry, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        regen_compact()
        regen_catalog()
        return 200, {"ok": True, "message": "Published item deleted", "removed": artifact}

    # draft / staging: remove the whole staging item dir (gitignored = permanent)
    found = find_staging(item_id)
    if not found:
        return 404, {"ok": False, "error": f"Draft item not found: {item_id}"}
    item_dir, _, _ = found
    target = item_dir.resolve()
    if not (within_repo(target) and EXTRACTIONS in target.parents):
        return 400, {"ok": False, "error": "Refusing to delete outside extractions."}
    shutil.rmtree(target)
    regen_catalog()
    return 200, {"ok": True, "message": "Draft item deleted (permanent)", "removed": str(item_dir.relative_to(REPO_ROOT))}


ROUTES = {
    "/api/publish": lambda body: action_publish(body.get("id", "")),
    "/api/delete": lambda body: action_delete(body.get("id", ""), body.get("status", "")),
}


# ---------- handler ----------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def log_message(self, fmt, *args):  # quieter
        sys.stderr.write("[catalog] " + (fmt % args) + "\n")

    def _json(self, code: int, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        route = ROUTES.get(self.path)
        if not route:
            return self._json(404, {"ok": False, "error": "Unknown endpoint"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"ok": False, "error": "Invalid JSON body"})
        item_id = str(body.get("id", ""))
        if not ID_PATTERN.match(item_id):
            return self._json(400, {"ok": False, "error": "Invalid item id"})
        try:
            code, payload = route(body)
        except Exception as exc:  # surface, never crash the server
            code, payload = 500, {"ok": False, "error": str(exc)}
        self._json(code, payload)


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Catalog control server on http://{HOST}:{PORT}/slide-system/catalog/")
    print("Mutating endpoints: /api/publish, /api/delete")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
