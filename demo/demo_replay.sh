#!/usr/bin/env bash
# Starts uvicorn in replay mode so the demo script runs against the recorded
# manifest in demo/manifests/ — no real API calls, no cost per take.
#
# Usage:
#   bash demo/demo_replay.sh
#
# Then start your screen recorder and run:
#   cd frontend && npm run e2e:headed
#
# Set CINEPAL_LLM_REPLAY_REALTIME=0 below to skip the recorded latency (faster).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST_DIR="$REPO_ROOT/demo/manifests"

if [ -z "$(ls -A "$MANIFEST_DIR" 2>/dev/null)" ]; then
  echo "ERROR: No manifests found in $MANIFEST_DIR"
  echo "Run 'bash demo/demo_record.sh' first to record a session."
  exit 1
fi

DEMO_SESSION_ID="$(ls -t "$MANIFEST_DIR"/*.jsonl | head -1 | xargs basename | sed 's/.jsonl//')"
export DEMO_SESSION_ID

echo "==> Replay mode: serving LLM responses from $MANIFEST_DIR"
echo "==> Session: $DEMO_SESSION_ID"
echo "==> Start your screen recorder, then: cd frontend && npm run e2e:headed"
echo ""

CINEPAL_LLM_MODE=replay \
CINEPAL_LLM_MANIFEST="$MANIFEST_DIR" \
CINEPAL_LLM_REPLAY_REALTIME=0 \
CONFIG_PATH="$REPO_ROOT/configs/default.yaml" \
  uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
