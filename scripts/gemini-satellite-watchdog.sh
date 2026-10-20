#!/bin/sh
# Gemini Satellite Watchdog Supervisor
# Keeps the satellite node / telemetry HUD alive and handles automatic reboots on upgrade (code 42) or crashes.

export GEMINI_WATCHDOG=1

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "======================================================="
echo "  🛰️  GEMINI SATELLITE WATCHDOG SUPERVISOR ACTIVE"
echo "  Directory: $SCRIPT_DIR"
echo "  Target:    python3 gemini-integrated.py satellite $*"
echo "======================================================="

while true; do
    python3 gemini-integrated.py satellite "$@"
    EXIT_CODE=$?

    if [ "$EXIT_CODE" -eq 42 ]; then
        echo "[watchdog] Satellite requested upgrade restart (exit code 42). Rebooting in 1s..."
        sleep 1
        continue
    elif [ "$EXIT_CODE" -eq 0 ]; then
        echo "[watchdog] Satellite exited cleanly (exit code 0). Shutting down."
        break
    else
        echo "[watchdog] Satellite process exited with code $EXIT_CODE. Crash guard sleeping 5s before respawn..."
        sleep 5
    fi
done
