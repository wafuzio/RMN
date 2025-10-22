#!/bin/bash
# Check what actually ran in the last 24 hours

HOURS=${1:-24}
LOG_DIR="logs"
OUTPUT_DIR="output"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Scheduler Activity Report - Last $HOURS Hours"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Scheduled runs that were triggered
echo "📅 SCHEDULED RUNS TRIGGERED:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "→ DUE:" "$LOG_DIR/scheduler_daemon.log" | tail -50 | while read -r line; do
    timestamp=$(echo "$line" | awk '{print $1, $2}')
    retailer=$(echo "$line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')
    client=$(echo "$line" | sed -n 's/.*\] \([^@]*\) @.*/\1/p')
    time=$(echo "$line" | sed -n 's/.*@ \([0-9:]*\).*/\1/p')
    echo "  $timestamp | [$retailer] $client @ $time"
done
echo ""

# 2. Successful keyword scrapes
echo "✅ SUCCESSFUL KEYWORD SCRAPES:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "SUCCESS keyword" "$LOG_DIR/scheduler_daemon.log" | tail -30 | while read -r line; do
    timestamp=$(echo "$line" | awk '{print $1, $2}')
    retailer=$(echo "$line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')
    keyword=$(echo "$line" | sed -n "s/.*keyword '\([^']*\)'.*/\1/p")
    client=$(echo "$line" | sed -n 's/.*for \(.*\)/\1/p')
    echo "  $timestamp | [$retailer] '$keyword' for $client"
done
echo ""

# 3. Failed scrapes
echo "❌ FAILED SCRAPES:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -E "FAIL|TIMEOUT|ERROR keyword" "$LOG_DIR/scheduler_daemon.log" | tail -20 | while read -r line; do
    timestamp=$(echo "$line" | awk '{print $1, $2}')
    echo "  $timestamp | $line"
done
if ! grep -q -E "FAIL|TIMEOUT|ERROR keyword" "$LOG_DIR/scheduler_daemon.log"; then
    echo "  (No failures in logs)"
fi
echo ""

# 4. Completed jobs with stats
echo "🎯 COMPLETED JOBS (with success counts):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "Completed scheduled scrape" "$LOG_DIR/scheduler_daemon.log" | tail -20 | while read -r line; do
    timestamp=$(echo "$line" | awk '{print $1, $2}')
    retailer=$(echo "$line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')
    client=$(echo "$line" | sed -n 's/.*for \([^:]*\):.*/\1/p')
    stats=$(echo "$line" | sed -n 's/.*\([0-9]*\/[0-9]* keywords successful\).*/\1/p')
    echo "  $timestamp | [$retailer] $client - $stats"
done
echo ""

# 5. HTML processing results
echo "🖼️  HTML/IMAGE PROCESSING:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep -E "Waiting.*before HTML processing|Successfully processed HTML|Failed to process HTML" "$LOG_DIR/scheduler_daemon.log" | tail -20 | while read -r line; do
    timestamp=$(echo "$line" | awk '{print $1, $2}')
    message=$(echo "$line" | sed 's/.*INFO - //')
    echo "  $timestamp | $message"
done
echo ""

# 6. Recent output files created
echo "📁 NEW FILES CREATED (last $HOURS hours):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
find "$OUTPUT_DIR" -type f \( -name "*.json" -o -name "*.html" -o -name "*.png" \) -mtime -1 2>/dev/null | head -30 | while read -r file; do
    timestamp=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$file")
    size=$(du -h "$file" | awk '{print $1}')
    echo "  $timestamp | $size | $file"
done
echo ""

# 7. Summary stats
echo "📊 SUMMARY STATISTICS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
total_due=$(grep -c "→ DUE:" "$LOG_DIR/scheduler_daemon.log" 2>/dev/null || echo 0)
total_success=$(grep -c "SUCCESS keyword" "$LOG_DIR/scheduler_daemon.log" 2>/dev/null || echo 0)
total_fail=$(grep -c -E "FAIL|TIMEOUT keyword" "$LOG_DIR/scheduler_daemon.log" 2>/dev/null || echo 0)
total_complete=$(grep -c "Completed scheduled scrape" "$LOG_DIR/scheduler_daemon.log" 2>/dev/null || echo 0)
new_json=$(find "$OUTPUT_DIR" -name "*.json" -mtime -1 2>/dev/null | wc -l | tr -d ' ')
new_html=$(find "$OUTPUT_DIR" -name "*.html" -mtime -1 2>/dev/null | wc -l | tr -d ' ')
new_png=$(find "$OUTPUT_DIR" -name "*.png" -mtime -1 2>/dev/null | wc -l | tr -d ' ')

echo "  Schedules triggered:     $total_due"
echo "  Keywords succeeded:      $total_success"
echo "  Keywords failed:         $total_fail"
echo "  Jobs completed:          $total_complete"
echo "  New JSON files:          $new_json"
echo "  New HTML files:          $new_html"
echo "  New PNG images:          $new_png"
echo ""

# 8. Current scheduler status
echo "🔍 CURRENT STATUS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if ps aux | grep -q "[s]cheduler_daemon.py"; then
    echo "  ✅ Scheduler is RUNNING"
    last_tick=$(grep "tick:" "$LOG_DIR/scheduler_daemon.log" | tail -1)
    echo "  Last tick: $last_tick"
else
    echo "  ❌ Scheduler is NOT running"
fi
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
