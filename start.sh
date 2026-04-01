#!/bin/bash
# AI Deduction Game — single-command startup script
# Usage: ./start.sh
# Starts backend (port 8000) + frontend (port 5173), prints access URLs, and
# kills both servers cleanly on Ctrl-C.

set -e

echo "🎮 AI Deduction Game — Starting..."
echo ""

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

command -v uv >/dev/null 2>&1 || {
  echo "❌  uv not found."
  echo "    Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
}

command -v pnpm >/dev/null 2>&1 || {
  echo "❌  pnpm not found."
  echo "    Install: npm install -g pnpm"
  exit 1
}

# ---------------------------------------------------------------------------
# API key check
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$SCRIPT_DIR/backend/.env" ]; then
  echo "❌  backend/.env not found."
  echo "    Copy the example and add your API key:"
  echo "    cp backend/.env.example backend/.env"
  echo "    Then edit backend/.env and set MINIMAX_API_KEY."
  exit 1
fi

if grep -q "your_minimax_api_key_here" "$SCRIPT_DIR/backend/.env"; then
  echo "❌  backend/.env still contains the placeholder key."
  echo "    Edit backend/.env and replace MINIMAX_API_KEY with your real key."
  exit 1
fi

# ---------------------------------------------------------------------------
# Install dependencies (skip if already up to date)
# ---------------------------------------------------------------------------

echo "📦 Installing dependencies..."
(cd "$SCRIPT_DIR/backend"  && uv sync --quiet)
(cd "$SCRIPT_DIR/frontend" && pnpm install --silent)
echo ""

# ---------------------------------------------------------------------------
# Kill any stale/suspended processes holding our ports (by port number)
# ---------------------------------------------------------------------------

for PORT in 8000 5173 5174 5175 5176 5177; do
  PIDS=$(lsof -ti :$PORT 2>/dev/null) || true
  if [ -n "$PIDS" ]; then
    kill -9 $PIDS 2>/dev/null || true
  fi
done
# Also kill by name as a backup
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "vite" 2>/dev/null || true
sleep 1

# ---------------------------------------------------------------------------
# Detect LAN IP (macOS + Linux)
# ---------------------------------------------------------------------------

LAN_IP=""
# macOS
if command -v ipconfig >/dev/null 2>&1; then
  LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
fi
# Linux fallback
if [ -z "$LAN_IP" ] && command -v hostname >/dev/null 2>&1; then
  LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
fi
[ -z "$LAN_IP" ] && LAN_IP="localhost"

# ---------------------------------------------------------------------------
# Start backend (background)
# ---------------------------------------------------------------------------

echo "🔧 Starting backend on :8000..."
(cd "$SCRIPT_DIR/backend" && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!

# Give the backend a moment to bind before printing URLs
sleep 2

# ---------------------------------------------------------------------------
# Clean shutdown on Ctrl-C / EXIT
# ---------------------------------------------------------------------------

cleanup() {
  echo ""
  echo "Stopping servers..."
  kill "$BACKEND_PID" 2>/dev/null || true
  # pnpm dev will exit on its own because it's in the foreground
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Print access URLs
# ---------------------------------------------------------------------------

echo "🎨 Starting frontend on :5173..."
echo ""
echo "========================================"
echo "  🌐 Local:   http://localhost:5173"
echo "  📱 LAN:     http://${LAN_IP}:5173"
echo "  🌍 Remote:  ngrok http 5173   (in another terminal)"
echo "              cloudflared tunnel --url http://localhost:5173"
echo "========================================"
echo ""
echo "Press Ctrl-C to stop both servers."
echo ""

# ---------------------------------------------------------------------------
# Start frontend (foreground — keeps the script alive)
# ---------------------------------------------------------------------------

(cd "$SCRIPT_DIR/frontend" && pnpm dev --host 0.0.0.0)
