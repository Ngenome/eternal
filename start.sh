#!/bin/bash
# Eternal Daemon launcher with auto-restart
cd "$(dirname "$0")"

while true; do
    echo "[$(date)] Starting Eternal Daemon..."
    uv run python daemon.py
    EXIT_CODE=$?
    echo "[$(date)] Daemon exited with code $EXIT_CODE"

    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "[$(date)] Clean exit. Not restarting."
        break
    fi

    echo "[$(date)] Restarting in 5 seconds..."
    sleep 5
done
