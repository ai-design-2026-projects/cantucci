#!/bin/sh
set -e
python -m db.apply
exec uvicorn backend.app:app --host 0.0.0.0 --port 8000
