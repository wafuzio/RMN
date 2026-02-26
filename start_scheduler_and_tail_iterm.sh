#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Scheduler Launcher + Log Tailer for macOS (iTerm2 version)
# ============================================================================
# Launches scheduler_entry.py in one iTerm2 tab and tails logs in another.
# Robust to spaces in paths, respects SCRAPER_HOME, creates logs if missing.
# ============================================================================

# Resolve project root (directory of this script)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer .venv Python for all dependencies (cv2, etc.)
if [[ -n "${PYTHON_EXEC:-}" ]]; then
  PYTHON="$PYTHON_EXEC"
elif [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PYTHON="$ROOT/.venv/bin/python3"
else
  PYTHON="python3"
fi

# SCRAPER_HOME controls where output/ and logs/ live.
# Default it to the project root if not set.
SCRAPER_HOME="${SCRAPER_HOME:-$ROOT}"
LOG_DIR="$SCRAPER_HOME/logs"
DAEMON="$ROOT/scheduler_entry.py"
MAIN_LOG="$LOG_DIR/scheduler_daemon.log"
EXEC_FLOW_LOG="$LOG_DIR/scheduler_execution_flow.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Ensure log files exist so tail -F never exits
: > "$MAIN_LOG"
: > "$EXEC_FLOW_LOG"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Scheduler Launcher + Log Tailer (iTerm2)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📂 Project root:  $ROOT"
echo "🏠 SCRAPER_HOME:  $SCRAPER_HOME"
echo "📝 Main log:      $MAIN_LOG"
echo "📊 Exec flow log: $EXEC_FLOW_LOG"
echo ""

# Build the commands that will run inside iTerm2 tabs
LAUNCH_CMD="cd '$ROOT' && export SCRAPER_HOME='$SCRAPER_HOME' && clear && echo '🚀 Scheduler Daemon' && echo '' && '$PYTHON' '$DAEMON'"

# Option 1: Tail main log only (default)
TAIL_CMD="cd '$ROOT' && export SCRAPER_HOME='$SCRAPER_HOME' && clear && echo '📝 Scheduler Logs' && echo '' && tail -n 200 -F '$MAIN_LOG'"

# Option 2: Tail BOTH main + execution-flow logs in one tab (uncomment to use)
# TAIL_CMD="cd '$ROOT' && export SCRAPER_HOME='$SCRAPER_HOME' && clear && echo '📝 Scheduler Logs (Main + Exec Flow)' && echo '' && tail -n 100 -F '$MAIN_LOG' '$EXEC_FLOW_LOG'"

# Launch iTerm2 with two tabs via AppleScript
osascript - "$LAUNCH_CMD" "$TAIL_CMD" <<'APPLESCRIPT'
on run argv
    set launchCmd to item 1 of argv
    set tailCmd to item 2 of argv
    
    tell application "iTerm"
        activate
        
        -- Create new window
        set newWindow to (create window with default profile)
        
        tell current session of newWindow
            -- Tab 1: daemon launcher
            set name to "Scheduler Daemon"
            write text launchCmd
        end tell
        
        tell newWindow
            -- Tab 2: tail logs
            set newTab to (create tab with default profile)
            tell current session of newTab
                set name to "Scheduler Logs"
                write text tailCmd
            end tell
        end tell
    end tell
end run
APPLESCRIPT

echo "✅ Started scheduler (in new iTerm2 tab)"
echo "✅ Tailing logs (in another iTerm2 tab)"
echo ""
echo "💡 Tips:"
echo "   - Close iTerm2 tabs to stop tailing"
echo "   - Daemon tab shows start/stop and lock messages"
echo "   - Press Ctrl+C in daemon tab to stop scheduler"
echo ""
echo "🔍 Filter logs:"
echo "   grep \"\\[kroger\\]\" $MAIN_LOG"
echo "   grep \"SUCCESS keyword\" $MAIN_LOG"
echo ""
