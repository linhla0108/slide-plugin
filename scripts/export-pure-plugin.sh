#!/usr/bin/env bash
# Export a clean, shareable plugin snapshot from this workspace.
# Usage:
#   ./scripts/export-plugin.sh              → creates dist/sun-riser-plugin-YYYYMMDD/ + .tar.gz
#   ./scripts/export-plugin.sh --no-zip    → skip the tar.gz, keep only the folder
#   ./scripts/export-plugin.sh --dry-run   → print what would be included, do nothing

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_TAG="$(date +%Y%m%d)"
DIST_NAME="sun-riser-plugin-${DATE_TAG}"
DIST_DIR="${REPO_ROOT}/dist/${DIST_NAME}"

NO_ZIP=false
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --no-zip)   NO_ZIP=true ;;
    --dry-run)  DRY_RUN=true ;;
  esac
done

# ---------------------------------------------------------------------------
# Allowlist: only these paths are included in the plugin export.
# Add new entries here if the plugin grows new top-level dirs.
# ---------------------------------------------------------------------------
INCLUDES=(
  ".agents/skills"
  "slide-system"
  "AGENTS.md"
  "README.md"
  "REQUIREMENTS.md"
  "skills-lock.json"
  ".gitignore"
  ".gitattributes"
)

# ---------------------------------------------------------------------------
# Patterns stripped from the export even if inside an included path.
# ---------------------------------------------------------------------------
RSYNC_EXCLUDES=(
  "__pycache__/"
  "*.pyc"
  ".DS_Store"
  ".codegraph/"
  "*.log"
  # strip run-time registries that are machine-generated
  "slide-system/registries/extract-readiness.json"
  "slide-system/registries/extraction-history.json"
)

if $DRY_RUN; then
  echo "=== DRY RUN — nothing will be written ==="
  echo "Destination: ${DIST_DIR}"
  echo ""
  echo "Included paths:"
  for p in "${INCLUDES[@]}"; do
    src="${REPO_ROOT}/${p}"
    if [ -e "$src" ]; then
      echo "  ✓  ${p}"
    else
      echo "  ✗  ${p}  (missing — skipped)"
    fi
  done
  echo ""
  echo "Excluded patterns:"
  for ex in "${RSYNC_EXCLUDES[@]}"; do
    echo "  –  ${ex}"
  done
  exit 0
fi

# ---------------------------------------------------------------------------
# Build the export
# ---------------------------------------------------------------------------
if [ -d "$DIST_DIR" ]; then
  echo "→ Removing existing export: ${DIST_DIR}"
  rm -rf "$DIST_DIR"
fi
mkdir -p "$DIST_DIR"

RSYNC_ARGS=(-a --no-perms)
for ex in "${RSYNC_EXCLUDES[@]}"; do
  RSYNC_ARGS+=(--exclude="$ex")
done

echo "→ Copying plugin files…"
for p in "${INCLUDES[@]}"; do
  src="${REPO_ROOT}/${p}"
  if [ ! -e "$src" ]; then
    echo "  ⚠  Skipping missing path: ${p}"
    continue
  fi

  dest_parent="${DIST_DIR}/$(dirname "$p")"
  mkdir -p "$dest_parent"

  rsync "${RSYNC_ARGS[@]}" "$src" "${dest_parent}/"
  echo "  ✓  ${p}"
done

# ---------------------------------------------------------------------------
# Zip
# ---------------------------------------------------------------------------
if ! $NO_ZIP; then
  ARCHIVE="${REPO_ROOT}/dist/${DIST_NAME}.tar.gz"
  echo "→ Creating archive: dist/${DIST_NAME}.tar.gz"
  tar -czf "$ARCHIVE" -C "${REPO_ROOT}/dist" "$DIST_NAME"
  ARCHIVE_SIZE="$(du -sh "$ARCHIVE" | cut -f1)"
  echo "  ✓  ${ARCHIVE_SIZE}  dist/${DIST_NAME}.tar.gz"
fi

echo ""
echo "Done. Plugin export → dist/${DIST_NAME}/"
if ! $NO_ZIP; then
  echo "       Archive     → dist/${DIST_NAME}.tar.gz"
fi
