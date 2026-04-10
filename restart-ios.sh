#!/bin/bash
# Start the backend (if not already running) and restart the AIDungeonMaster
# app in the iOS simulator. Boots the simulator first if nothing is running.

BUNDLE_ID="com.aidm.AIDungeonMaster"
PREFERRED_UDID="2E0FDC05-F8A8-44E6-A9E2-76EC734D3790"  # iPhone 17 Pro
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

# ── 1. Start backend if not already listening on port 8000 ──────────────────
if lsof -i tcp:8000 -sTCP:LISTEN -t &>/dev/null; then
  echo "Backend already running on :8000"
else
  echo "Starting backend..."
  cd "$BACKEND_DIR"
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &>/tmp/aidm_backend.log &
  BACKEND_PID=$!
  echo "Backend PID: $BACKEND_PID (logs: /tmp/aidm_backend.log)"
  # Wait up to 8 seconds for it to become ready
  for i in $(seq 1 8); do
    sleep 1
    if lsof -i tcp:8000 -sTCP:LISTEN -t &>/dev/null; then
      echo "Backend ready."
      break
    fi
    if [ "$i" -eq 8 ]; then
      echo "Warning: backend did not start in time — check /tmp/aidm_backend.log"
    fi
  done
  cd "$SCRIPT_DIR"
fi

# ── 2. Boot simulator if needed ─────────────────────────────────────────────
UDID=$(xcrun simctl list devices | grep Booted | grep -oE '[0-9A-F-]{36}' | head -1)

if [ -z "$UDID" ]; then
  echo "No booted simulator — booting iPhone 17 Pro..."
  xcrun simctl boot "$PREFERRED_UDID"
  open -a Simulator
  sleep 5
  UDID="$PREFERRED_UDID"
fi

# ── 3. Restart the app ───────────────────────────────────────────────────────
echo "Simulator: $UDID"
echo "Terminating $BUNDLE_ID..."
xcrun simctl terminate "$UDID" "$BUNDLE_ID" 2>/dev/null || true
sleep 1

echo "Launching $BUNDLE_ID..."
xcrun simctl launch "$UDID" "$BUNDLE_ID"
echo "Done."
