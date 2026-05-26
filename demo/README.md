# demo/ — record/replay demo scripts

This directory contains scripts and a Playwright spec for recording a live CinePal chat session and replaying it later with zero LLM calls. Useful for screen-recording demos and deterministic re-takes.

---

## How it works

Recording operates at the **chat level**: each completed user→assistant turn is saved together with the full cluster snapshot it produced. On replay the backend short-circuits every `POST /conversations/{id}/messages` call and returns the recorded reply and snapshot instantly — no agents, no API spend.

Recordings are self-contained JSON files. You can take them to a fresh machine (or a wiped database) and replay them by running the provided Playwright spec.

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

# Terminal 3 — run the Playwright demo script
cd demo/playwright
npm install          # first time only
DEMO_RECORDING=../recordings/my-demo.json npx playwright test --headed
```

The Playwright spec navigates to the app, creates a new conversation, and types each recorded user message. The backend serves the recorded assistant replies and cluster snapshots instantly.

---

## File layout

```
demo/
  demo_record.sh           Start backend in record mode
  demo_replay.sh           Start backend in replay mode
  chat_record_replay.py    Core Python module (imported by backend)
  recordings/              Recorded sessions (JSON)
  playwright/
    package.json
    playwright.config.ts
    tests/demo.spec.ts     Playwright test that drives the demo
```

---

## Environment variables

| Variable | Where used | Description |
|---|---|---|
| `CINEPAL_DEMO_MODE` | backend | `record` or `replay`; unset for live mode |
| `CINEPAL_DEMO_RECORDING` | backend | Path to the recording JSON file |
| `DEMO_RECORDING` | Playwright | Path to the recording JSON file (relative to `demo/playwright/` or absolute) |
| `DEMO_TURN_PAUSE_MS` | Playwright | Milliseconds to pause between turns (default `1500`) |
| `APP_URL` | Playwright | Frontend URL (default `http://127.0.0.1:5173`) |
| `RECORD_VIDEO` | Playwright | Set to `1` to capture a video of the run |
