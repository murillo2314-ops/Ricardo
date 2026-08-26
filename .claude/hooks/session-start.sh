#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "Installing dependencies..."
npm install

echo "Seeding data directories..."
OC_SETUP_NO_DEV=true node scripts/setup.mjs
