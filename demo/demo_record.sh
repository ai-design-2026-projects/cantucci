#!/usr/bin/env bash
# Starts uvicorn in record mode so every LLM call is captured to
# demo/manifests/<session_id>.jsonl.
#
# Usage:
#   bash demo/demo_record.sh
#
# While uvicorn is running, open a second terminal and run:
#   cd frontend && npm run e2e:headed
#
# The manifest file will appear in demo/manifests/ once the spec completes.
# Commit it so replay runs are reproducible.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST_DIR="$REPO_ROOT/demo/manifests"

mkdir -p "$MANIFEST_DIR"

echo "==> Recording mode: LLM calls will be saved to $MANIFEST_DIR"
echo "==> Run the Playwright spec in another terminal: cd frontend && npm run e2e:headed"
echo ""

CINEPAL_LLM_MODE=record \
CINEPAL_LLM_MANIFEST="$MANIFEST_DIR" \
CONFIG_PATH="$REPO_ROOT/configs/dev.yaml" \
  uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
