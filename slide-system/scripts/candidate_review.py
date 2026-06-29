#!/usr/bin/env python3
"""Candidate review / rename / metadata layer for Docling auto-detect output.

This sits BETWEEN `analyze_with_docling.py` (which emits placeholder candidates)
and `scaffold_extraction.py` (which consumes a cleaned extraction request). It
lets a non-technical reviewer rename each placeholder `item_id` to a semantic id
and attach retrieval-ready metadata, then approve the candidate for extraction
request generation.

It is deliberately inert with respect to shared state, exactly like the Docling
analysis pre-step:

  * It ONLY reads/writes under
    `outputs/component-extractions/<extraction-id>/analysis/`:
      - candidate-reviews.json                  reviewer metadata, keyed by the
                                                original Docling placeholder id
      - approved/<item_id>.extraction-request.json
                                                a schema-compatible extraction
                                                request, written on approval
  * It NEVER publishes, never mutates the registry/visual-library, and never
    scaffolds. Approval writes a reviewed request artifact only; a human still
    runs `scaffold_extraction.py` and the publish gate afterwards.

The validation gate reuses `scaffold_extraction`'s id/intent rules as the single
source of truth, so a candidate that cannot be scaffolded can never be approved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import REPO_ROOT, load_json, normalized_bounds, now_iso, write_json

# Single source of truth for the id/intent gates: the scaffold script. A
# candidate that fails these can never become a stable identity, so approval
# must apply the exact same rules.
import scaffold_extraction as scaffold

ID_OK = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Required retrieval metadata. Free-text fields must be non-empty; list fields
# must carry at least one non-empty value. These mirror the contract in
# slide-system/schemas/candidate-review.schema.json.
REQUIRED_TEXT_FIELDS = (
    "display_name",
    "requested_type",
    "component_type",
    "layout_role",
    "visual_summary",
)
REQUIRED_LIST_FIELDS = (
    "semantic_intent",
    "content_structure",
    "tags",
    "keywords",
    "use_cases",
)
# Fields a reviewer may edit via PATCH. candidate_id / source_path /
# slide_or_page / region are fixed from the Docling detection and are never
# user-editable; review_status moves only through approve()/reject().
EDITABLE_TEXT_FIELDS = REQUIRED_TEXT_FIELDS + ("quality_notes", "retrieval_notes")
EDITABLE_LIST_FIELDS = REQUIRED_LIST_FIELDS + ("anti_use_cases",)


class CandidateError(Exception):
    """A request that cannot be served (bad id, missing run/candidate)."""


class CandidateValidationError(CandidateError):
    """Approval blocked by validation. Carries plain-language messages."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #

def extractions_root() -> Path:
    return REPO_ROOT / "outputs" / "component-extractions"


def _analysis_dir(extraction_id: str, root: Path | None = None) -> Path:
    """Resolve <root>/<extraction_id>/analysis with path-traversal safety.

    ID_OK already forbids slashes and a leading dot (so '..' and 'a/b' are
    rejected), but the containment check is kept as defense in depth.
    """
    root = (root or extractions_root()).resolve()
    if not ID_OK.match(extraction_id or ""):
        raise CandidateError(f"Invalid extraction id: {extraction_id!r}")
    target = (root / extraction_id / "analysis").resolve()
    if target != root and root not in target.parents:
        raise CandidateError("Refusing to resolve outside the extractions root.")
    return target


def _request_path(adir: Path) -> Path:
    return adir / "candidate-extraction-request.json"


def _reviews_path(adir: Path) -> Path:
    return adir / "candidate-reviews.json"


def _approved_dir(adir: Path) -> Path:
    return adir / "approved"


def _approved_request_path(adir: Path, item_id: str) -> Path:
    return _approved_dir(adir) / f"{item_id}.extraction-request.json"


# --------------------------------------------------------------------------- #
# load helpers
# --------------------------------------------------------------------------- #

def _load_request(adir: Path) -> dict:
    path = _request_path(adir)
    if not path.is_file():
        raise CandidateError(
            "No candidate-extraction-request.json in this run "
            "(nothing detected, or analysis not run yet)."
        )
    return load_json(path)


def _load_reviews(adir: Path) -> dict:
    path = _reviews_path(adir)
    if not path.is_file():
        return {}
    data = load_json(path)
    return data.get("reviews", {}) if isinstance(data, dict) else {}


def _request_items_by_id(request: dict) -> dict:
    return {it["item_id"]: it for it in request.get("items", []) if it.get("item_id")}


def _default_review(extraction_id: str, source_path: str, item: dict) -> dict:
    """Seed a review object from a raw Docling candidate. item_id starts as the
    placeholder so the gate keeps rejecting it until a human renames it."""
    return {
        "candidate_id": item["item_id"],
        "item_id": item["item_id"],
        "display_name": "",
        "requested_type": item.get("requested_type", "component"),
        "semantic_intent": list(item.get("semantic_intent", [])),
        "component_type": "",
        "layout_role": "",
        "visual_summary": "",
        "content_structure": [],
        "tags": [],
        "keywords": [],
        "use_cases": [],
        "anti_use_cases": [],
        "source_path": source_path,
        "slide_or_page": item.get("slide_or_page"),
        "region": item.get("region"),
        "review_status": "pending",
        "reviewer": None,
        "reviewed_at": None,
        "reject_reason": None,
        "quality_notes": "",
        "retrieval_notes": "",
    }


# --------------------------------------------------------------------------- #
# read API
# --------------------------------------------------------------------------- #

def list_runs(root: Path | None = None) -> list[dict]:
    """Every analysis run that carries a candidate request, with status counts."""
    root = (root or extractions_root())
    if not root.exists():
        return []
    runs: list[dict] = []
    for req_path in sorted(root.glob("*/analysis/candidate-extraction-request.json")):
        extraction_id = req_path.parent.parent.name
        try:
            request = load_json(req_path)
        except (OSError, json.JSONDecodeError):
            continue
        reviews = _load_reviews(req_path.parent)
        items = request.get("items", [])
        statuses = [
            (reviews.get(it.get("item_id"), {}) or {}).get("review_status", "pending")
            for it in items
        ]
        runs.append({
            "extraction_id": extraction_id,
            "source_path": request.get("source_path", ""),
            "candidate_count": len(items),
            "pending": sum(s == "pending" for s in statuses),
            "approved": sum(s == "approved_for_extraction" for s in statuses),
            "rejected": sum(s == "rejected" for s in statuses),
        })
    return runs


def get_candidates(extraction_id: str, root: Path | None = None) -> dict:
    """Merge raw candidates with any saved review metadata for one run."""
    adir = _analysis_dir(extraction_id, root)
    request = _load_request(adir)
    reviews = _load_reviews(adir)
    source_path = request.get("source_path", "")
    out: list[dict] = []
    for item in request.get("items", []):
        cid = item.get("item_id")
        if not cid:
            continue
        review = reviews.get(cid)
        if not review:
            review = _default_review(extraction_id, source_path, item)
            saved = False
        else:
            saved = True
        out.append({
            "candidate_id": cid,
            "detected_type": cid.split("-", 1)[0],
            "detected_intent": list(item.get("semantic_intent", [])),
            "slide_or_page": item.get("slide_or_page"),
            "region": item.get("region"),
            "notes": item.get("notes", ""),
            "saved": saved,
            "review": review,
        })
    return {"extraction_id": extraction_id, "source_path": source_path, "candidates": out}


# --------------------------------------------------------------------------- #
# write API
# --------------------------------------------------------------------------- #

def _coerce_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # tolerate comma/newline-separated input from a plain text field
        return [part.strip() for part in re.split(r"[\n,]", value) if part.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    raise CandidateError("Expected a list or comma-separated string.")


def _write_reviews(adir: Path, extraction_id: str, source_path: str,
                   reviews: dict) -> None:
    write_json(_reviews_path(adir), {
        "extraction_id": extraction_id,
        "source_path": source_path,
        "updated_at": now_iso(),
        "schema": "slide-system/schemas/candidate-review.schema.json",
        "reviews": reviews,
    })


def save_review(extraction_id: str, candidate_id: str, patch: dict,
                reviewer: str | None = None, root: Path | None = None) -> dict:
    """Save reviewer-edited draft metadata for one candidate. Editing always
    resets the candidate to `pending` (and drops any stale approved artifact) so
    an approval can never outlive the metadata it was based on."""
    adir = _analysis_dir(extraction_id, root)
    request = _load_request(adir)
    source_path = request.get("source_path", "")
    items = _request_items_by_id(request)
    if candidate_id not in items:
        raise CandidateError(f"Unknown candidate: {candidate_id}")

    reviews = _load_reviews(adir)
    review = reviews.get(candidate_id) or _default_review(
        extraction_id, source_path, items[candidate_id])
    # The artifact (if any) is keyed by the item_id as it stood when approved.
    # Capture it before a rename so the stale file is removed, not orphaned.
    prior_item_id = review.get("item_id")

    for field in EDITABLE_TEXT_FIELDS:
        if field in patch and patch[field] is not None:
            review[field] = str(patch[field]).strip()
    for field in EDITABLE_LIST_FIELDS:
        if field in patch:
            review[field] = _coerce_list(patch[field])
    if "item_id" in patch and patch["item_id"] is not None:
        review["item_id"] = str(patch["item_id"]).strip()

    # Immutable provenance, always taken from the detection (never the patch).
    item = items[candidate_id]
    review["candidate_id"] = candidate_id
    review["source_path"] = source_path
    review["slide_or_page"] = item.get("slide_or_page")
    review["region"] = item.get("region")

    review["review_status"] = "pending"
    review["reject_reason"] = None
    review["reviewer"] = reviewer
    review["reviewed_at"] = now_iso()

    # A prior approval is now stale; remove its artifact so disk and state agree.
    # Cover both the old name (in case of a rename) and the new one.
    _remove_approved_artifact(adir, prior_item_id)
    _remove_approved_artifact(adir, review.get("item_id"))

    reviews[candidate_id] = review
    _write_reviews(adir, extraction_id, source_path, reviews)
    return review


def validate_review(review: dict) -> list[str]:
    """Plain-language validation messages (empty list == ready to approve)."""
    errors: list[str] = []
    item_id = (review.get("item_id") or "").strip()
    if not item_id:
        errors.append("Item ID is required.")
    else:
        if not ID_OK.match(item_id):
            errors.append(
                "Item ID may only contain lowercase letters, numbers, dot, "
                "dash, and underscore, and must start with a letter or number.")
        if scaffold._DOCLING_DRAFT_ID.match(item_id):
            errors.append(
                f"Item ID '{item_id}' is still the Docling placeholder. Rename "
                "it to a semantic descriptor (e.g. 'kickoff-2026-hero-visual').")
        if scaffold._BANNED_ID.match(item_id):
            errors.append(
                f"Item ID '{item_id}' is positional/generic. Describe the visual "
                "content instead (e.g. 'metric-card', 'timeline-horizontal').")

    for field in REQUIRED_TEXT_FIELDS:
        if not str(review.get(field, "") or "").strip():
            errors.append(f"{_label(field)} is required.")

    for field in REQUIRED_LIST_FIELDS:
        values = [v for v in (review.get(field) or []) if str(v).strip()]
        if not values:
            errors.append(f"At least one {_label(field)} value is required.")

    intent = {str(v).lower().strip() for v in (review.get("semantic_intent") or [])}
    if intent and intent <= scaffold._GENERIC_INTENT:
        errors.append(
            "Semantic intent is only generic. Add descriptive intent values "
            "(e.g. 'cover', 'salary-table', 'org-chart').")

    region = review.get("region")
    if not isinstance(region, dict):
        errors.append("Region is missing.")
    else:
        try:
            normalized_bounds(region)
        except (KeyError, TypeError, ValueError):
            errors.append("Region is malformed (need x, y, width, height, unit).")
    return errors


def _label(field: str) -> str:
    return field.replace("_", " ").capitalize()


def approved_extraction_id(run_id: str, item_id: str) -> str:
    """Per-candidate scaffold namespace: `<run-id>-<item-id>`.

    The Docling run id (e.g. `docling-demo`) is shared by every candidate, so if
    each approved request reused it, scaffolding the second candidate would fail
    with "Extraction output already exists" (they would all target the same
    outputs/component-extractions/<run-id> directory). Giving every approved
    request its own extraction id keeps each scaffold output isolated.
    """
    return f"{run_id}-{item_id}"


def build_approved_request(extraction_id: str, source_path: str,
                           review: dict) -> dict:
    """Construct a schema-compatible single-item extraction request.

    Only fields the extraction-request schema allows are emitted (it sets
    additionalProperties:false); the rich retrieval metadata stays in
    candidate-reviews.json. The request carries a per-candidate extraction id so
    multiple approvals from one run scaffold into separate output dirs.
    """
    return {
        "extraction_id": approved_extraction_id(extraction_id, review["item_id"]),
        "source_path": source_path,
        "items": [{
            "item_id": review["item_id"],
            "slide_or_page": review["slide_or_page"],
            "region": normalized_bounds(review["region"]),
            "object_ids": [],
            "requested_type": review["requested_type"],
            "semantic_intent": [v for v in review["semantic_intent"] if str(v).strip()],
            "notes": (
                f"Reviewed & approved Docling candidate (candidate_id="
                f"{review['candidate_id']}). Approved for extraction request "
                "generation; scaffold and the publish gate are still required."),
            "replacement_for": None,
        }],
    }


def approve(extraction_id: str, candidate_id: str, reviewer: str | None = None,
            root: Path | None = None) -> dict:
    """Validate a reviewed candidate and write its approved request artifact.

    No registry/library/publish mutation: only analysis/approved/<id>.json is
    written, plus the review status update.
    """
    adir = _analysis_dir(extraction_id, root)
    request = _load_request(adir)
    source_path = request.get("source_path", "")
    items = _request_items_by_id(request)
    if candidate_id not in items:
        raise CandidateError(f"Unknown candidate: {candidate_id}")

    reviews = _load_reviews(adir)
    review = reviews.get(candidate_id)
    if not review:
        raise CandidateValidationError([
            "Add and save the required metadata before approving."])

    errors = validate_review(review)
    if errors:
        raise CandidateValidationError(errors)

    approved_request = build_approved_request(extraction_id, source_path, review)
    # Hard guard: the approved request must pass the exact scaffold gate, so an
    # approval can never produce something scaffold_extraction would reject.
    try:
        scaffold.validate_request_item(approved_request["items"][0])
    except SystemExit as exc:
        raise CandidateValidationError([str(exc)]) from exc

    request_path = _approved_request_path(adir, review["item_id"])
    write_json(request_path, approved_request)

    review["review_status"] = "approved_for_extraction"
    review["reject_reason"] = None
    review["reviewer"] = reviewer
    review["reviewed_at"] = now_iso()
    reviews[candidate_id] = review
    _write_reviews(adir, extraction_id, source_path, reviews)

    try:
        rel_path = request_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:  # a custom root outside the repo (tests/scripting)
        rel_path = request_path.as_posix()
    return {"review": review, "approved_request_path": rel_path}


def reject(extraction_id: str, candidate_id: str, reason: str,
           reviewer: str | None = None, root: Path | None = None) -> dict:
    """Mark a candidate rejected. Drops any approved artifact it may have left."""
    if not (reason or "").strip():
        raise CandidateError("A rejection reason is required.")
    adir = _analysis_dir(extraction_id, root)
    request = _load_request(adir)
    source_path = request.get("source_path", "")
    items = _request_items_by_id(request)
    if candidate_id not in items:
        raise CandidateError(f"Unknown candidate: {candidate_id}")

    reviews = _load_reviews(adir)
    review = reviews.get(candidate_id) or _default_review(
        extraction_id, source_path, items[candidate_id])

    _remove_approved_artifact(adir, review.get("item_id"))
    review["review_status"] = "rejected"
    review["reject_reason"] = reason.strip()
    review["reviewer"] = reviewer
    review["reviewed_at"] = now_iso()
    reviews[candidate_id] = review
    _write_reviews(adir, extraction_id, source_path, reviews)
    return review


def _remove_approved_artifact(adir: Path, item_id: str | None) -> None:
    if not item_id or not ID_OK.match(item_id):
        return
    path = _approved_request_path(adir, item_id)
    try:
        if path.is_file() and _approved_dir(adir).resolve() in path.resolve().parents:
            path.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# CLI (review without the UI; handy for scripting/tests)
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review/rename/approve Docling candidates (analysis-only; "
                    "never publishes or mutates the registry/library).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List analysis runs with candidate requests.")

    p_show = sub.add_parser("show", help="Show candidates for one run.")
    p_show.add_argument("extraction_id")

    p_approve = sub.add_parser("approve", help="Approve a saved candidate.")
    p_approve.add_argument("extraction_id")
    p_approve.add_argument("candidate_id")
    p_approve.add_argument("--reviewer", default=None)

    p_reject = sub.add_parser("reject", help="Reject a candidate with a reason.")
    p_reject.add_argument("extraction_id")
    p_reject.add_argument("candidate_id")
    p_reject.add_argument("--reason", required=True)
    p_reject.add_argument("--reviewer", default=None)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "list":
            print(json.dumps(list_runs(), indent=2))
        elif args.cmd == "show":
            print(json.dumps(get_candidates(args.extraction_id), indent=2))
        elif args.cmd == "approve":
            print(json.dumps(approve(args.extraction_id, args.candidate_id,
                                     args.reviewer), indent=2))
        elif args.cmd == "reject":
            print(json.dumps(reject(args.extraction_id, args.candidate_id,
                                    args.reason, args.reviewer), indent=2))
    except CandidateValidationError as exc:
        print("Validation failed:", file=sys.stderr)
        for err in exc.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    except CandidateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
