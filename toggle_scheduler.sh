#!/bin/bash
# Quick toggle for scheduler master override

CONFIG_FILE="config/scheduler_control.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Creating scheduler control config..."
    mkdir -p config
    echo '{"enabled": true, "notes": "Master override for scheduler"}' > "$CONFIG_FILE"
fi

# Read current state
CURRENT=$(cat "$CONFIG_FILE" | grep -o '"enabled": *[^,}]*' | grep -o '[^:]*$' | tr -d ' ')

case "$1" in
    on|enable|start)
        echo '{"enabled": true, "notes": "Master override for scheduler. Set enabled to false to completely disable all scheduled scraping."}' > "$CONFIG_FILE"
        echo "✅ Scheduler ENABLED (master override)"
        # Remove pause file if it exists
        rm -f .scheduler_paused 2>/dev/null
        ;;
    off|disable|stop)
        echo '{"enabled": false, "notes": "Master override for scheduler. Set enabled to true to re-enable all scheduled scraping."}' > "$CONFIG_FILE"
        echo "🛑 Scheduler DISABLED (master override)"
        # Also create pause file for double protection
        echo "PAUSED via master override" > .scheduler_paused
        # Kill any running scheduler processes
        pkill -9 -f "scheduler_daemon\|scheduler_entry" 2>/dev/null
        echo "   Killed any running scheduler processes"
        ;;
    status)
        if [ "$CURRENT" = "true" ]; then
            echo "✅ Scheduler is ENABLED"
        else
            echo "🛑 Scheduler is DISABLED"
        fi
        if [ -f ".scheduler_paused" ]; then
            echo "⏸️  Pause file exists (.scheduler_paused)"
        fi
        ;;
    *)
        echo "Usage: $0 {on|off|status}"
        echo ""
        echo "Commands:"
        echo "  on/enable/start  - Enable scheduler (master override)"
        echo "  off/disable/stop - Disable scheduler (master override + kill processes)"
        echo "  status           - Check current state"
        echo ""
        echo "Current state: $([ "$CURRENT" = "true" ] && echo "ENABLED" || echo "DISABLED")"
        exit 1
        ;;
esac
