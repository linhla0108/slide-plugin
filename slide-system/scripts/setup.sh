#!/usr/bin/env bash
# Idempotent setup for the slide-system tooling.
# Detects what is already installed and only installs missing pieces.
# Safe to run repeatedly — skips satisfied steps.
#
# Prerequisites the user must install themselves:
#   - Python 3.10+  (https://www.python.org/downloads/)
#   - Node.js 18+   (https://nodejs.org)
#
# Usage:
#   ./slide-system/scripts/setup.sh

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

SKIP=0
DONE=0
FAIL=0

ok()   { echo "  ✓ $1"; DONE=$((DONE + 1)); }
skip() { echo "  ⏭ $1 (already installed)"; SKIP=$((SKIP + 1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }

echo "=== SUN.RISER slide-system setup ==="
echo ""

# ── Step 1: Python 3 ────────────────────────────────────────────────
echo "[1/6] Python 3"
if command -v python3 &>/dev/null; then
  PY_VERSION=$(python3 --version 2>&1)
  skip "${PY_VERSION}"
else
  fail "Python 3 not found. Install from https://www.python.org/downloads/"
fi

# ── Step 2: Node.js ─────────────────────────────────────────────────
echo "[2/6] Node.js"
if command -v node &>/dev/null; then
  NODE_VERSION=$(node --version)
  skip "Node.js ${NODE_VERSION}"
else
  fail "Node.js not found. Install from https://nodejs.org (LTS recommended)"
fi

# Stop early if prerequisites are missing
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "=== Setup stopped: ${FAIL} prerequisite(s) missing ==="
  echo "Install the items marked ✗ above, then re-run this script."
  exit 1
fi

# ── Step 3: Python venv + deps ──────────────────────────────────────
echo "[3/6] Python virtual environment (.venv)"
NEED_PY_DEPS=false

if [ ! -f "${VENV_DIR}/bin/python3" ]; then
  echo "  → Creating .venv…"
  python3 -m venv "${VENV_DIR}"
  NEED_PY_DEPS=true
  ok "Created .venv"
else
  skip ".venv exists"
fi

echo "[4/6] Python packages (python-pptx, Pillow, PyMuPDF)"
if [ "$NEED_PY_DEPS" = true ]; then
  # Fresh venv — install everything
  "${VENV_DIR}/bin/python3" -m pip install --quiet --upgrade pip
  "${VENV_DIR}/bin/python3" -m pip install --quiet python-pptx Pillow PyMuPDF
  ok "Installed python-pptx, Pillow, PyMuPDF"
else
  # Check each package individually
  MISSING_PY=()
  "${VENV_DIR}/bin/python3" -c "import pptx"  2>/dev/null || MISSING_PY+=("python-pptx")
  "${VENV_DIR}/bin/python3" -c "import PIL"   2>/dev/null || MISSING_PY+=("Pillow")
  "${VENV_DIR}/bin/python3" -c "import fitz"  2>/dev/null || MISSING_PY+=("PyMuPDF")

  if [ ${#MISSING_PY[@]} -gt 0 ]; then
    echo "  → Installing missing: ${MISSING_PY[*]}…"
    "${VENV_DIR}/bin/python3" -m pip install --quiet --upgrade pip
    "${VENV_DIR}/bin/python3" -m pip install --quiet "${MISSING_PY[@]}"
    ok "Installed ${MISSING_PY[*]}"
  else
    skip "python-pptx, Pillow, PyMuPDF"
  fi
fi

# ── Step 5: npm packages (Playwright) ───────────────────────────────
echo "[5/6] Playwright (npm)"
if [ -d "${REPO_ROOT}/node_modules/playwright" ]; then
  skip "playwright npm package"
else
  echo "  → Installing playwright…"
  npm install --prefix "${REPO_ROOT}" --quiet 2>/dev/null
  ok "Installed playwright"
fi

# ── Step 6: Chromium browser for Playwright ─────────────────────────
echo "[6/6] Chromium browser (for Playwright)"
CHROMIUM_DIR=$(npx --prefix "${REPO_ROOT}" playwright install --dry-run chromium 2>&1 \
  | grep "Install location:" | head -1 | awk '{print $NF}')
if [ -n "${CHROMIUM_DIR}" ] && [ -d "${CHROMIUM_DIR}" ]; then
  skip "Chromium (${CHROMIUM_DIR##*/})"
else
  echo "  → Installing Chromium (this may take a minute)…"
  npx --prefix "${REPO_ROOT}" playwright install chromium --with-deps
  ok "Installed Chromium"
fi

# ── Summary ─────────────────────────────────────────────────────────
echo ""
TOTAL=$((SKIP + DONE))
echo "=== Setup complete: ${DONE} installed, ${SKIP} skipped (of ${TOTAL} steps) ==="
if [ "$DONE" -eq 0 ]; then
  echo "Everything was already in place — nothing to do."
fi
