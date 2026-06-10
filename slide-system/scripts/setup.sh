#!/usr/bin/env bash
# One-shot setup for the standalone slide-system tooling.
# Run this ONCE on a new machine before using the standalone export scripts:
#   capture-slides.js, build_hybrid_pptx.py, export-pdf.js.
# Claude Code users do NOT need to run this — gen_pptx and Playwright are
# already built into Claude Code.
#
# Requirements:
#   - Node.js 18+ must be installed on the machine.
#     Download: https://nodejs.org
#
# Usage:
#   ./slide-system/scripts/setup.sh

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== SUN.RISER standalone tooling setup ==="
echo "Repo: ${REPO_ROOT}"
echo ""

# Check node
if ! command -v node &>/dev/null; then
  echo "ERROR: Node.js not found."
  echo "       Download and install it from https://nodejs.org (LTS version),"
  echo "       then re-run this script."
  exit 1
fi
NODE_VERSION=$(node --version)
echo "✓ Node.js ${NODE_VERSION}"

# Check npm
if ! command -v npm &>/dev/null; then
  echo "ERROR: npm not found. It normally ships with Node.js."
  exit 1
fi

# Install npm deps (Playwright only — pptxgenjs not needed)
echo ""
echo "→ Installing npm dependencies (playwright)…"
npm install --prefix "${REPO_ROOT}"

# Install Chromium browser for Playwright
echo ""
echo "→ Installing Chromium for Playwright…"
npx --prefix "${REPO_ROOT}" playwright install chromium --with-deps

# Install Python deps for build_hybrid_pptx.py
echo ""
echo "→ Installing Python dependencies (python-pptx, Pillow)…"
python3 -m pip install python-pptx Pillow --quiet

echo ""
echo "=== Setup complete ==="
echo ""
echo "Full standalone PPTX workflow (2 steps):"
echo ""
echo "  Step 1 — Capture slide renders + DOM layout:"
echo "    node slide-system/scripts/capture-slides.js \\"
echo "      --url http://localhost:8080 \\"
echo "      --slides 8 \\"
echo "      --out-dir outputs/my-job/run-001/qa/export-renders"
echo ""
echo "  Step 2 — Build editable hybrid PPTX:"
echo "    python3 slide-system/scripts/build_hybrid_pptx.py \\"
echo "      --layout  outputs/my-job/run-001/qa/export-renders/export-layout.json \\"
echo "      --renders outputs/my-job/run-001/qa/export-renders \\"
echo "      --slides  8 \\"
echo "      --output  outputs/my-job/run-001/exports/deck.pptx"
echo ""
echo "  Export PDF:"
echo "    node slide-system/scripts/export-pdf.js \\"
echo "      --url http://localhost:8080 --slides 8 \\"
echo "      --output outputs/my-job/run-001/exports/deck.pdf"
