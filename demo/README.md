# demo/ — record/replay demo scripts

This directory contains scripts for recording a live CinePal session to a JSONL manifest and replaying it later with zero live LLM calls. Useful for demos, CI smoke tests, and deterministic regression checks.

---

## Scripts

| Script | Description |
|---|---|
| `demo_record.sh` | Launch the backend in record mode; all LLM responses are saved to a JSONL manifest. |
| `demo_replay.sh` | Launch the backend in replay mode against the newest manifest; no live LLM calls are made. |

Manifests are written to and read from `demo/manifests/`.

---

## Usage

### Record a session

```bash
bash demo/demo_record.sh
```

Starts the backend with `CINEPAL_LLM_MODE=record`. Interact with the UI normally. Every LLM response is appended to `demo/manifests/session_<timestamp>.jsonl`. Stop the server when done.

### Replay a session

```bash
bash demo/demo_replay.sh
```

Starts the backend with `CINEPAL_LLM_MODE=replay` pointed at the newest `.jsonl` file in `demo/manifests/`. Replaying the same sequence of user messages produces bit-identical LLM responses from the manifest — no API key needed, no token spend.

---

## `CINEPAL_LLM_MODE` env var

| Value | Behaviour |
|---|---|
| *(unset)* | Normal live mode — all LLM calls go to the configured provider. |
| `record` | Live mode + append each LLM response to the active manifest file. |
| `replay` | Serve LLM responses from the manifest; raise `ReplayDriftError` if the request sequence diverges. |

The manifest path is controlled by `CINEPAL_LLM_MANIFEST` (defaults to the newest file in `demo/manifests/` when replaying, or a new timestamped file when recording).
