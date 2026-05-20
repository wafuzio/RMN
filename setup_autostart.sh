#!/bin/bash

# Setup script to enable auto-start of Retail Monitor services on login/wake

echo "=============================================="
echo "Retail Monitor - Setup Auto-Start"
echo "=============================================="
echo ""

PLIST_FILE="$HOME/Library/LaunchAgents/com.gale.retailmonitor.plist"

# Load the LaunchAgent
echo "Loading LaunchAgent..."
launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"

if [ $? -eq 0 ]; then
    echo "✅ LaunchAgent loaded successfully"
    echo ""
    echo "Your services will now auto-start:"
    echo "  • On login"
    echo "  • After laptop wake from sleep"
    echo ""
    echo "To manually start now, run:"
    echo "  ./scripts/start_all_services.sh"
    echo ""
    echo "To disable auto-start:"
    echo "  launchctl unload $PLIST_FILE"
else
    echo "❌ Failed to load LaunchAgent"
    exit 1
fi

echo "=============================================="
