# demo/ — record/replay demo scripts

This directory contains scripts and a Playwright-driven demo replay for recording a live CinePal chat session and replaying it later with zero LLM calls. Useful for screen-recording demos and deterministic re-takes.

---

## How it works

Recording operates at the **chat level**: each completed user→assistant turn is saved together with the full cluster snapshot it produced. On replay the backend short-circuits every `POST /conversations/{id}/messages` call and returns the recorded reply and snapshot instantly — no agents, no API spend.

The Playwright script paces itself via **DOM signals** rather than arbitrary sleeps. It waits for the `[data-testid="loading-bubble"]` element to appear and then disappear before proceeding to the next action. This means retiming the backend's synthetic delays (in `demo/utils/state.py`) requires no changes to the Playwright script.

Recordings are self-contained JSON files. You can take them to a fresh machine (or a wiped database) and replay them by running the provided Playwright script.

---

## Quick start

### 1. Record a session

```bash
# Terminal 1 — start the backend in record mode
bash demo/demo_record.sh --name my-demo

# Terminal 2 — start the frontend
cd frontend && npm run dev
```

Chat with the application normally. Every turn you complete is appended to `demo/recordings/my-demo.json`. Stop the backend with Ctrl-C when finished.

### 2. Replay the recording

```bash
# Terminal 1 — start the backend in replay mode
bash demo/demo_replay.sh demo/recordings/my-demo.json

# Terminal 2 — start the frontend
cd frontend && npm run dev

# Terminal 3 — start Chrome with remote debugging enabled
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/cinepal-demo-chrome \
  --new-window http://localhost:5173

# Terminal 4 — run the Playwright demo script
cd demo/playwright
npm install          # first time only
DEMO_RECORDING=../recordings/my-demo.json npm run demo:headed
```

The Playwright script navigates to the app, creates a new conversation, and replays the recorded flow with slower human-like typing, linear pointer movement, visible cluster selection, and real scrolling/clicking for the inspect and evolution-map interactions. The backend serves the recorded assistant replies and cluster snapshots with synthetic processing delays so the step indicator animates naturally.

---

## File layout

```
demo/
  demo_record.sh           Start backend in record mode
  demo_replay.sh           Start backend in replay mode
  recordings/              Recorded sessions (JSON)
  utils/
    state.py               Shared module-level state + mode flags + replay timing constants
    record.py              record_turn() — appends turns to the in-memory recording and flushes to disk
    replay.py              replay_turn(), load_recording(), snapshot getters
  playwright/
    package.json
    playwright.config.ts
    demo-scripted.spec.ts  Main Playwright script that drives the demo
    lib/
      cursor.ts            Cursor class (single position source of truth) + injectMacCursor overlay
      humanize.ts          humanType, smoothScroll, submitMessageLikeHuman, easing helpers
      sync.ts              waitForTurnComplete (DOM-signal wait), fetchSnapshot
      recording.ts         loadRecording + Turn/Recording types
```

---

## Environment variables

| Variable | Where used | Description |
|---|---|---|
| `CINEPAL_DEMO_MODE` | backend | `record` or `replay`; unset for live mode |
| `CINEPAL_DEMO_RECORDING` | backend | Path to the recording JSON file |
| `DEMO_RECORDING` | Playwright | Path to the recording JSON file (relative to `demo/playwright/` or absolute) |
| `APP_URL` | Playwright | Frontend URL (default `http://localhost:5173`) |
| `CDP_ENDPOINT` | Playwright | Chrome DevTools endpoint for the browser used in the screen recording (default `http://localhost:9222`) |

---

## Tuning replay speed

Open `demo/utils/state.py` and adjust the two constants at the top:

```python
_REPLAY_STEP_INTENT_DELAY: float = 1.2      # seconds before clustering step fires
_REPLAY_STEP_CLUSTERING_DELAY: float = 2.2  # seconds before turn_done fires
```

The Playwright script will automatically adapt — no other changes needed.
