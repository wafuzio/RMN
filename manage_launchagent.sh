#!/bin/bash
# Manage the scheduler LaunchAgent

PLIST=~/Library/LaunchAgents/com.rmn.scheduler.plist
LABEL=com.rmn.scheduler

case "$1" in
    install)
        echo "📦 Installing LaunchAgent..."
        launchctl unload "$PLIST" 2>/dev/null || true
        launchctl load "$PLIST"
        echo "✅ LaunchAgent installed and loaded"
        echo ""
        echo "To start now:"
        echo "  launchctl start $LABEL"
        ;;
    
    start)
        echo "🚀 Starting scheduler..."
        launchctl start "$LABEL"
        sleep 2
        echo "✅ Started. Checking status..."
        launchctl list | grep "$LABEL" || echo "⚠️  Not running"
        ;;
    
    stop)
        echo "🛑 Stopping scheduler..."
        launchctl stop "$LABEL"
        echo "✅ Stopped"
        ;;
    
    restart)
        echo "🔄 Restarting scheduler..."
        launchctl stop "$LABEL" 2>/dev/null || true
        sleep 1
        launchctl start "$LABEL"
        sleep 2
        echo "✅ Restarted. Checking status..."
        launchctl list | grep "$LABEL" || echo "⚠️  Not running"
        ;;
    
    uninstall)
        echo "🗑️  Uninstalling LaunchAgent..."
        launchctl stop "$LABEL" 2>/dev/null || true
        launchctl unload "$PLIST" 2>/dev/null || true
        echo "✅ LaunchAgent uninstalled"
        ;;
    
    status)
        echo "📊 Scheduler Status:"
        echo ""
        if launchctl list | grep -q "$LABEL"; then
            echo "✅ LaunchAgent is loaded"
            launchctl list | grep "$LABEL"
        else
            echo "❌ LaunchAgent is NOT loaded"
        fi
        echo ""
        echo "Process check:"
        ps aux | grep scheduler_daemon | grep -v grep || echo "  No scheduler_daemon process found"
        echo ""
        echo "Recent logs:"
        tail -5 logs/scheduler_daemon.log 2>/dev/null || echo "  No logs found"
        ;;
    
    logs)
        echo "📋 Tailing scheduler logs (Ctrl+C to stop)..."
        tail -f logs/scheduler_daemon.log logs/scheduler_execution_flow.log
        ;;
    
    *)
        echo "Usage: $0 {install|start|stop|restart|uninstall|status|logs}"
        echo ""
        echo "Commands:"
        echo "  install   - Install and load the LaunchAgent"
        echo "  start     - Start the scheduler"
        echo "  stop      - Stop the scheduler"
        echo "  restart   - Restart the scheduler"
        echo "  uninstall - Remove the LaunchAgent"
        echo "  status    - Check if scheduler is running"
        echo "  logs      - Tail the scheduler logs"
        exit 1
        ;;
esac
