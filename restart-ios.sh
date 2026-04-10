#!/bin/bash
# Build, start backend, and run the AIDungeonMaster app in the iOS simulator.
# Pass --no-build to skip the Xcode build step (relaunch only).

BUNDLE_ID="com.aidm.AIDungeonMaster"
PREFERRED_UDID="2E0FDC05-F8A8-44E6-A9E2-76EC734D3790"  # iPhone 17 Pro
SCHEME="AIDungeonMaster"
PROJECT="ios/AIDungeonMaster.xcodeproj"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
SKIP_BUILD=false

for arg in "$@"; do
  [[ "$arg" == "--no-build" ]] && SKIP_BUILD=true
done

# ── 1. Start backend if not already listening on port 8000 ──────────────────
if lsof -i tcp:8000 -sTCP:LISTEN -t &>/dev/null; then
  echo "Backend already running on :8000"
else
  echo "Starting backend..."
  cd "$BACKEND_DIR"
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &>/tmp/aidm_backend.log &
  BACKEND_PID=$!
  echo "Backend PID: $BACKEND_PID (logs: /tmp/aidm_backend.log)"
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

# ── 3. Build with xcodebuild (unless --no-build) ─────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
  echo "Building $SCHEME for simulator..."
  cd "$SCRIPT_DIR"
  xcodebuild \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -destination "id=$UDID" \
    -configuration Debug \
    -derivedDataPath /tmp/aidm_build \
    build 2>&1 | tee /tmp/aidm_build.log | grep -E "(error:|BUILD SUCCEEDED|BUILD FAILED)" | tail -20

  if grep -q "BUILD FAILED" /tmp/aidm_build.log; then
    echo "Build FAILED — last errors:"
    grep "error:" /tmp/aidm_build.log | tail -20
    exit 1
  fi

  # Install the freshly built app
  APP_PATH=$(find /tmp/aidm_build -name "AIDungeonMaster.app" -not -path "*/\.*" 2>/dev/null | head -1)
  if [ -n "$APP_PATH" ]; then
    echo "Installing $APP_PATH..."
    xcrun simctl install "$UDID" "$APP_PATH"
  else
    echo "Warning: could not find built .app — install manually from Xcode."
  fi
fi

# ── 4. Relaunch the app ──────────────────────────────────────────────────────
echo "Simulator: $UDID"
echo "Terminating $BUNDLE_ID..."
xcrun simctl terminate "$UDID" "$BUNDLE_ID" 2>/dev/null || true
sleep 1

echo "Launching $BUNDLE_ID..."
xcrun simctl launch "$UDID" "$BUNDLE_ID"
echo "Done."
