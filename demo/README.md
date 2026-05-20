# Demo Recording

## Prerequisites

All commands run from the repo root. Chrome must be running with remote debugging enabled before the Playwright spec:

```bash
pkill -f chrome; google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug --start-maximized "http://localhost:5173"
```

---

## Step 1 — Record (one-time, real LLM calls)

**Terminal 1** — backend in record mode:
```bash
bash scripts/demo_record.sh
```

**Terminal 2** — frontend:
```bash
cd frontend && npm run dev
```

**Terminal 3** — Playwright spec (drives the chat automatically):
```bash
cd frontend && npm run e2e:headed
```

The spec types these three messages:
1. *"I've seen recently Interstellar, can you suggest something similar"*
2. *"The sheer sense of cosmic awe"*
3. *"A mix of both"*

When the spec finishes, a manifest is saved to `demo/manifests/<session_id>.jsonl`. Commit it:

```bash
git add demo/manifests/<session_id>.jsonl
git commit -m "Add demo manifest"
```

---

## Step 2 — Replay (every subsequent take, no API cost)

**Terminal 1** — backend in replay mode (serves pre-recorded LLM responses):
```bash
bash scripts/demo_replay.sh
```

**Terminal 2** — frontend:
```bash
cd frontend && npm run dev
```

Start your screen recorder (OBS, QuickTime, etc.), then:

**Terminal 3**:
```bash
cd frontend && npm run e2e:headed
```

The spec replays the exact same conversation instantly. Stop the recorder when it ends.

---

## Re-recording

If the backend call order changes (you will see `ReplayDriftError` in the logs), delete the old manifest and repeat Step 1:

```bash
rm demo/manifests/*.jsonl
```

## Notes

- `CINEPAL_LLM_REPLAY_REALTIME=0` in `scripts/demo_replay.sh` — responses are instant during replay. Set to `1` to re-introduce original latency.
- The Playwright spec has a 1 s initial pause before any action starts.
- The spec is in `frontend/e2e/demo.spec.ts`. Edit the messages there if you re-record a different conversation.
