#!/usr/bin/env python3
"""Local control server for the visual-library catalog.

Serves the catalog (and all repo-relative assets) exactly like
`python3 -m http.server`, plus two POST endpoints that mutate the real repo
on this machine:

    POST /api/publish  {id}          -> build preview/, approve, promote into library,
                                        then remove the redundant staging copy
    POST /api/delete   {id, status}  -> remove a published (library) or draft item
    POST /api/stage-candidates {extraction_id}
                                      -> auto-stage Docling candidates as Drafts

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
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "slide-system" / "scripts"

# Candidate review is now a backend compatibility layer; user-facing review is
# the normal Draft tab. auto_stage_candidates bridges Docling analysis -> Draft.
sys.path.insert(0, str(SCRIPTS))
import candidate_review as cr  # noqa: E402
import auto_stage_candidates as asc  # noqa: E402
REGISTRY = REPO_ROOT / "slide-system" / "registries" / "visual-library.json"
HISTORY = REPO_ROOT / "slide-system" / "registries" / "extraction-history.json"
LIBRARY = REPO_ROOT / "slide-system" / "library"
EXTRACTIONS = REPO_ROOT / "outputs" / "component-extractions"
# sun.<type>.<slug> plus an optional .gNN group suffix. Decomposed page
# components are surfaced as <base>.g01/.g02/... by build_component_catalog;
# without the optional group segment the publish/delete endpoints rejected
# every group item with "Invalid item id".
ID_PATTERN = re.compile(r"^[a-z0-9]+\.[a-z0-9-]+\.[a-z0-9-]+(\.g\d+)?$")
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


def body_bool(body: dict, key: str, default: bool) -> bool:
    value = body.get(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{key} must be a boolean")


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


def find_all_staging(item_id: str) -> list[Path]:
    """Every staging item dir that resolves to item_id. A draft can be
    re-scaffolded into several extraction batches (e.g. a re-run marked
    `duplicate`); the catalog dedupes them to one card, so a delete must sweep
    ALL of them or an orphan folder is left on disk."""
    dirs: list[Path] = []
    if not EXTRACTIONS.exists():
        return dirs
    for mapping_path in EXTRACTIONS.glob("*/items/*/mapping.json"):
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ids = {mapping.get("candidate_stable_id"), mapping.get("id"), mapping_path.parent.name}
        if item_id in ids:
            dirs.append(mapping_path.parent)
    return dirs


def purge_draft_history(item_id: str) -> int:
    """Remove every NON-published extraction-history record for item_id (the
    draft's staging/duplicate trail). A `published` record, if any, belongs to a
    promoted version and is left intact. Without this, deleting a draft leaves
    staging/duplicate records that no gate catches -> silent history drift.
    Returns the count of records removed."""
    if not HISTORY.exists():
        return 0
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    attempts = history.get("attempts", [])
    kept = [a for a in attempts
            if not (a.get("stable_id") == item_id and a.get("status") != "published")]
    removed = len(attempts) - len(kept)
    if removed:
        history["attempts"] = kept
        history["updated_at"] = now_iso()
        HISTORY.write_text(json.dumps(history, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return removed


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

    # draft / staging: remove EVERY staging folder for this id (gitignored =
    # permanent) and purge its history trail so disk, catalog, and history agree.
    found = find_all_staging(item_id)
    if not found:
        return 404, {"ok": False, "error": f"Draft item not found: {item_id}"}
    removed: list[str] = []
    for item_dir in found:
        target = item_dir.resolve()
        if not (within_repo(target) and EXTRACTIONS in target.parents):
            continue  # never delete outside outputs/component-extractions
        rel = str(item_dir.relative_to(REPO_ROOT))
        prune_staging(item_dir)  # rmtree + prune emptied items/ and batch dirs
        removed.append(rel)
    if not removed:
        return 400, {"ok": False, "error": "Refusing to delete outside extractions."}
    purged = purge_draft_history(item_id)
    regen_catalog()
    return 200, {"ok": True, "message": "Draft item deleted (permanent)",
                 "removed": removed, "history_purged": purged}


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

    def end_headers(self):
        # Local authoring tool: never let the browser serve a stale catalog.js /
        # index.html after an edit (the source of confusing "I changed it but the
        # page didn't" bugs). Force revalidation on every asset.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def _json(self, code: int, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return None

    # ---- candidate-review routing (analysis-only; no publish/registry) ----

    def _candidate_segments(self) -> list[str] | None:
        """Path parts after /api/candidates, URL-decoded. None if not a match."""
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/api/candidates":
            return []
        prefix = "/api/candidates/"
        if path.startswith(prefix):
            return [unquote(p) for p in path[len(prefix):].split("/") if p]
        return None

    def _serve_candidate(self, method: str, segments: list[str]) -> bool:
        """Dispatch a candidate-review request. Returns True if it owned the
        route (response already sent), False to fall through to other handling."""
        try:
            if method == "GET" and segments == []:
                return self._sent(200, {"ok": True, "runs": cr.list_runs()})
            if method == "GET" and len(segments) == 1:
                return self._sent(200, {"ok": True, **cr.get_candidates(segments[0])})
            if method == "PATCH" and len(segments) == 2:
                body = self._read_body()
                if body is None:
                    return self._sent(400, {"ok": False, "error": "Invalid JSON body"})
                review = cr.save_review(segments[0], segments[1],
                                        body.get("metadata", body),
                                        reviewer=body.get("reviewer"))
                return self._sent(200, {"ok": True, "review": review})
            if method == "POST" and len(segments) == 3 and segments[2] == "approve":
                body = self._read_body() or {}
                result = cr.approve(segments[0], segments[1],
                                    reviewer=body.get("reviewer"))
                return self._sent(200, {"ok": True, **result})
            if method == "POST" and len(segments) == 3 and segments[2] == "reject":
                body = self._read_body() or {}
                review = cr.reject(segments[0], segments[1],
                                   body.get("reason", ""),
                                   reviewer=body.get("reviewer"))
                return self._sent(200, {"ok": True, "review": review})
        except cr.CandidateValidationError as exc:
            return self._sent(422, {"ok": False, "error": "Validation failed",
                                    "errors": exc.errors})
        except cr.CandidateError as exc:
            return self._sent(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # never crash the server
            return self._sent(500, {"ok": False, "error": str(exc)})
        return self._sent(404, {"ok": False, "error": "Unknown candidate endpoint"})

    def _sent(self, code: int, payload: dict) -> bool:
        self._json(code, payload)
        return True

    def do_GET(self):
        segments = self._candidate_segments()
        if segments is not None:
            self._serve_candidate("GET", segments)
            return
        super().do_GET()

    def do_PATCH(self):
        segments = self._candidate_segments()
        if segments is not None:
            self._serve_candidate("PATCH", segments)
            return
        self._json(404, {"ok": False, "error": "Unknown endpoint"})

    def do_POST(self):
        segments = self._candidate_segments()
        if segments is not None:
            self._serve_candidate("POST", segments)
            return
        if self.path == "/api/stage-candidates":
            body = self._read_body()
            if body is None:
                return self._json(400, {"ok": False, "error": "Invalid JSON body"})
            extraction_id = str(body.get("extraction_id", ""))
            try:
                rebuild_catalog = body_bool(body, "rebuild_catalog", True)
                build_artifacts = body_bool(body, "build_artifacts", True)
                summary = asc.stage_run(
                    extraction_id,
                    rebuild_catalog=rebuild_catalog,
                    build_artifacts=build_artifacts,
                )
            except ValueError as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            except (cr.CandidateError, asc.AutoStageError) as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:  # surface, never crash the server
                return self._json(500, {"ok": False, "error": str(exc)})
            return self._json(200, {"ok": True, **summary})
        route = ROUTES.get(self.path)
        if not route:
            return self._json(404, {"ok": False, "error": "Unknown endpoint"})
        body = self._read_body()
        if body is None:
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
    print("Mutating endpoints: /api/publish, /api/delete, /api/stage-candidates")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
