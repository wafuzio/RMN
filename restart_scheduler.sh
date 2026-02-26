#!/bin/bash
# Restart Scheduler Daemon - Clean restart with all fixes

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Scheduler Daemon Restart"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🛑 Stopping old scheduler daemons..."
pkill -9 -f "scheduler_daemon.py"

echo "🗑️  Removing lock files..."
rm -f /tmp/scheduler_daemon.lock
rm -f logs/scheduler.lock
rm -f logs/scheduler.pid

echo "⏳ Waiting 2 seconds..."
sleep 2

echo "✅ Verifying no daemons running..."
if ps -ef | grep -i 'scheduler_daemon.py' | grep -v grep; then
    echo ""
    echo "❌ Old daemon still running! Kill manually:"
    echo "   ps -ef | grep scheduler_daemon.py"
    echo "   kill -9 <PID>"
    echo ""
    exit 1
fi

echo "✓ No old daemons found"
echo ""

echo "📋 Checking schedule configs..."
CONFIGS=$(find output -maxdepth 3 -type f -name 'schedule_config.json' 2>/dev/null)
if [ -z "$CONFIGS" ]; then
    echo "⚠️  No schedule configs found in output/*/*/*/"
    echo "   Create one first or daemon will have nothing to monitor"
else
    COUNT=$(echo "$CONFIGS" | wc -l | tr -d ' ')
    echo "✓ Found $COUNT schedule config(s):"
    echo "$CONFIGS" | sed 's/^/   - /'
fi
echo ""

echo "🚀 Starting fresh scheduler daemon..."
echo "   (Press Ctrl+C to stop)"
echo ""
# Use .venv Python to ensure all dependencies (cv2, etc.) are available
VENV_PYTHON="$(dirname "$0")/.venv/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
    "$VENV_PYTHON" scheduler_entry.py
else
    echo "⚠️  .venv not found, falling back to system python3"
    python3 scheduler_entry.py
fi
