#!/usr/bin/env bash
# Launch the backend in record mode.
#
# Every assistant reply and its cluster snapshot are saved to a JSON file
# under demo/recordings/. Stop the server (Ctrl-C) after you finish chatting.
#
# Usage:
#   bash demo/demo_record.sh [--name <recording-name>]
#
# Examples:
#   bash demo/demo_record.sh                        # saves demo/recordings/<timestamp>.json
#   bash demo/demo_record.sh --name sci-fi-session  # saves demo/recordings/sci-fi-session.json
#
# Then start the frontend: cd frontend && npm run dev
# Chat normally in the browser. Each turn is appended to the recording file.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RECORDINGS_DIR="$REPO_ROOT/demo/recordings"
mkdir -p "$RECORDINGS_DIR"

NAME="$(date +%Y%m%d_%H%M%S)"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --name) NAME="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

RECORDING_FILE="$RECORDINGS_DIR/${NAME}.json"
echo "==> Recording mode: turns will be saved to $RECORDING_FILE"
echo "==> Start the frontend: cd frontend && npm run dev"
echo ""

CINEPAL_DEMO_MODE=record \
CINEPAL_DEMO_RECORDING="$RECORDING_FILE" \
CONFIG_PATH="$REPO_ROOT/configs/prod.yaml" \
  python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
