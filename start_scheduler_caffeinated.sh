#!/bin/bash
# Start scheduler with caffeinate to prevent MacBook sleep while plugged in
# This keeps the scheduler running even when the lid is closed (as long as power is connected)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Check if scheduler is already running
if [ -f "$LOG_DIR/scheduler.lock" ]; then
    echo "⚠️  Scheduler may already be running (lock file exists)"
    echo "   If you're sure it's not running, delete: $LOG_DIR/scheduler.lock"
    exit 1
fi

# Remove pause file if it exists
if [ -f "$SCRIPT_DIR/.scheduler_paused" ]; then
    echo "🗑️  Removing pause file..."
    rm "$SCRIPT_DIR/.scheduler_paused"
fi

echo "🚀 Starting scheduler with caffeinate..."
echo "   This will prevent sleep while plugged in and scheduler is running"
echo "   Press Ctrl+C to stop"
echo ""

# caffeinate flags:
# -d: prevent display sleep
# -i: prevent idle sleep
# -s: prevent system sleep when on AC power (plugged in)
# The scheduler will keep running even with lid closed as long as MacBook is plugged in

cd "$SCRIPT_DIR"
caffeinate -dis .venv/bin/python3 scheduler_entry.py
