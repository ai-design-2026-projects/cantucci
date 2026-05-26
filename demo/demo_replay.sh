#!/usr/bin/env bash
# Launch the backend in replay mode against a recording file.
#
# No live LLM calls are made; every assistant reply and cluster snapshot are
# served directly from the recording. Responses appear instantly.
#
# Usage:
#   bash demo/demo_replay.sh [<path-to-recording.json>]
#
# Examples:
#   bash demo/demo_replay.sh                              # uses newest file in demo/recordings/
#   bash demo/demo_replay.sh demo/recordings/smoke.json  # explicit file
#
# After the backend starts:
#   1. Start the frontend: cd frontend && npm run dev
#   2. Run the Playwright demo script:
#      cd demo/playwright && DEMO_RECORDING=../recordings/smoke.json npx playwright test --headed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RECORDINGS_DIR="$REPO_ROOT/demo/recordings"

if [[ $# -ge 1 ]]; then
    RECORDING_FILE="$1"
else
    RECORDING_FILE="$(ls -t "$RECORDINGS_DIR"/*.json 2>/dev/null | head -1)"
    if [[ -z "$RECORDING_FILE" ]]; then
        echo "ERROR: No recordings found in $RECORDINGS_DIR"
        echo "Run 'bash demo/demo_record.sh' first to record a session."
        exit 1
    fi
fi

echo "==> Replay mode: serving turns from $RECORDING_FILE"
echo "==> Start the frontend: cd frontend && npm run dev"
echo "==> Then run: cd demo/playwright && DEMO_RECORDING=../recordings/$(basename "$RECORDING_FILE") npx playwright test --headed"
echo ""

CINEPAL_DEMO_MODE=replay \
CINEPAL_DEMO_RECORDING="$RECORDING_FILE" \
CONFIG_PATH="$REPO_ROOT/configs/prod.yaml" \
  python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
