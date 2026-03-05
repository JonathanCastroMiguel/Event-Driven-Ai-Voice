#!/usr/bin/env bash
set -euo pipefail

echo "======================================"
echo "      SDD Framework Bootstrap"
echo "======================================"
echo

ROOT="$(pwd)"

# ------------------------------------------------------------
# 1. Ensure we are in repo root
# ------------------------------------------------------------
if [[ ! -d ".claude" ]]; then
  echo "❌ ERROR: .claude/ directory not found."
  echo "You must run this script from the repository root."
  exit 1
fi

if [[ ! -d ".claude/commands" ]]; then
  echo "❌ ERROR: .claude/commands directory not found."
  echo "This repo may be incomplete."
  exit 1
fi

echo "✅ Repository root detected."
echo

# ------------------------------------------------------------
# 2. Verify custom command folders
# ------------------------------------------------------------
OPSX_DIR=".claude/commands/opsx"
AISPECS_DIR=".claude/commands/ai-specs"

if [[ ! -d "$OPSX_DIR" ]]; then
  echo "❌ ERROR: Missing $OPSX_DIR"
  exit 1
fi

if [[ ! -d "$AISPECS_DIR" ]]; then
  echo "❌ ERROR: Missing $AISPECS_DIR"
  exit 1
fi

OPSX_COUNT=$(find "$OPSX_DIR" -type f -name "*.md" | wc -l | tr -d ' ')
AISPECS_COUNT=$(find "$AISPECS_DIR" -type f -name "*.md" | wc -l | tr -d ' ')

if [[ "$OPSX_COUNT" -eq 0 ]]; then
  echo "❌ ERROR: No opsx command files found."
  exit 1
fi

if [[ "$AISPECS_COUNT" -eq 0 ]]; then
  echo "❌ ERROR: No ai-specs command files found."
  exit 1
fi

echo "✅ opsx commands detected: $OPSX_COUNT"
echo "✅ ai-specs commands detected: $AISPECS_COUNT"
echo

# ------------------------------------------------------------
# 3. Check OpenSpec CLI installation
# ------------------------------------------------------------
echo "Checking OpenSpec CLI..."

if command -v openspec >/dev/null 2>&1; then
  echo "✅ OpenSpec CLI detected: $(openspec --version 2>/dev/null || echo 'version unknown')"
else
  echo "⚠️  OpenSpec CLI is NOT installed."
  echo
  echo "Install it using your preferred method:"
  echo "  npm install -g openspec"
  echo "  or"
  echo "  pnpm add -g openspec"
  echo
fi

echo

# ------------------------------------------------------------
# 4. Detect potential misuse of 'openspec init'
# ------------------------------------------------------------
echo "Verifying repository integrity..."

if [[ ! -d "openspec" ]]; then
  echo "⚠️ WARNING: openspec/ directory not found."
  echo "This template should include it."
fi

# Optional heuristic check:
DEFAULT_MARKER=".claude/commands/default"

if [[ -d "$DEFAULT_MARKER" ]]; then
  echo
  echo "⚠️ It looks like default OpenSpec commands may have been generated."
  echo "If someone ran 'openspec init', custom commands might be overwritten."
  echo
  echo "DO NOT run 'openspec init' in this repository."
fi

echo "✅ Repository structure looks correct."
echo

# ------------------------------------------------------------
# 5. Claude Code reminder
# ------------------------------------------------------------
echo "Next Steps:"
echo
echo "1) Open this folder in VS Code."
echo "2) Ensure Workspace Trust is enabled."
echo "3) Open Claude Code (NOT Copilot Chat)."
echo "4) Type '/' in Claude Code to verify commands are detected."
echo
echo "IMPORTANT:"
echo "This repository is already initialized."
echo "DO NOT run: openspec init"
echo
echo "Bootstrap completed successfully."
echo "======================================"