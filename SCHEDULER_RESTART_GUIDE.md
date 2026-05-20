# Scheduler Restart Guide

## Quick Start

The scheduler is now configured for **4 clients only** with **Kroger disabled**:
- ✅ Proactiv
- ✅ Garanimals (Garan)
- ✅ Community Coffee
- ✅ MilkPEP

### Start the Scheduler

```bash
cd /Users/dan.maguire/Documents/Amazon_Scrape
./start_scheduler_caffeinated.sh
```

This will:
- Keep your MacBook awake while plugged in (even with lid closed)
- Run the scheduler with all improvements
- Prevent duplicate runs
- Audit scrape quality automatically

### Stop the Scheduler

Press `Ctrl+C` in the terminal where it's running.

Or from another terminal:
```bash
rm logs/scheduler.lock
pkill -f scheduler_entry.py
```

---

## What's New

### 1. **Caffeinate Integration**
The scheduler now uses macOS `caffeinate` to prevent sleep while running:
- `-d`: Prevents display sleep
- `-i`: Prevents idle sleep  
- `-s`: Prevents system sleep when on AC power (plugged in)

**Result**: Scheduler keeps running even when MacBook lid is closed, as long as it's plugged in.

### 2. **Automatic Quality Audits**
After each successful scrape, the scheduler automatically audits the results:
- **Blank ads**: Ads with missing/broken images
- **Unknown brands**: Ads with brand='unknown'
- **Unbound ads**: Ads missing critical fields
- **Quality score**: 0-100 based on issues found

Audit logs saved to: `output/<retailer>/<client>/runs/audit_log.jsonl`

Low quality scrapes (score < 50) trigger warnings in the scheduler log.

### 3. **Improved Timing Reliability**
- Uses `±2 minute window` for scheduled times (configurable via `SCHEDULER_DUE_WINDOW_MIN`)
- Prevents duplicate runs within the same time slot
- Sleeps until next minute boundary for precise timing
- Tracks last run times to avoid re-running within 2 hours

### 4. **Front Page Capture**
Daily front page screenshots are back on schedule:
- **Time**: 12:05 PM daily
- **Retailers**: Walmart, Amazon, Instacart, Target (Kroger excluded)
- **Config**: `schedules/frontpage_capture.json`

### 5. **Unknown Brand Analysis**
New tool to investigate why brands are marked as "unknown":

```bash
.venv/bin/python3 tools/analyze_unknown_brands.py [limit]
```

This will:
- Scan recent run files for unknown brands
- Show statistics by retailer and ad type
- Suggest potential brand additions based on patterns
- Save detailed report to `logs/unknown_brands_report.json`

---

## Active Schedules

### Walmart
- **Proactiv**: 4 times daily (8:05, 12:05, 16:05, 21:00)
- **Garanimals**: 3 times daily (9:40, 15:40, 18:00)
- **Community Coffee**: 3 times daily (9:30, 13:30, 18:20)
- **MilkPEP**: 3 times daily (00:00, 8:00, 16:00)

### Amazon
- **Proactiv**: 4 times daily
- **Community Coffee**: 3 times daily (2 keyword sets)
- **MilkPEP**: 3 times daily

### Target
- **Proactiv**: 4 times daily
- **Community Coffee**: 3 times daily (2 keyword sets)
- **MilkPEP**: 3 times daily

### Instacart
- **Proactiv**: 4 times daily
- **Community Coffee**: 3 times daily (2 keyword sets)
- **MilkPEP**: 3 times daily

**Total**: 33 enabled schedules across 4 retailers and 4 clients

---

## Disabled Schedules

### All Kroger Schedules
All Kroger schedules are disabled due to ongoing Akamai bot detection issues. These can be re-enabled once the Kroger scraper is fixed.

### Other Clients
All other clients (Barilla, Blue Bunny, Bomb Pop, Curology, Goodles, Halo Top, Land O'Frost, Magic Spoon, Pickle, Quip) are disabled.

To re-enable a client, edit their schedule files and set `"enabled": true`, or use the filter tool:

```bash
.venv/bin/python3 tools/filter_schedules.py --dry-run
```

---

## Monitoring

### Logs
- **Main log**: `logs/scheduler_daemon.log`
- **Execution flow**: `logs/scheduler_execution_flow.log`
- **Audit logs**: `output/<retailer>/<client>/runs/audit_log.jsonl`

### Real-time Monitoring
```bash
tail -f logs/scheduler_daemon.log
```

Look for:
- `→ DUE:` - Scheduled scrape starting
- `SUCCESS` - Scrape completed successfully
- `AUDIT:` - Quality audit results
- `LOW QUALITY` - Warning about poor scrape quality

### Check Scheduler Status
```bash
# Check if running
ps aux | grep scheduler_entry

# Check lock file
ls -lh logs/scheduler.lock

# Check PID file
cat logs/scheduler.pid
```

---

## Troubleshooting

### Scheduler Won't Start
1. Check if already running: `ls logs/scheduler.lock`
2. If stale lock exists: `rm logs/scheduler.lock`
3. Check master control: `cat config/scheduler_control.json` (should be `"enabled": true`)
4. Check pause file: `ls .scheduler_paused` (delete if exists)

### Scrapes Not Running
1. Check schedule is enabled: `grep '"enabled"' schedules/<retailer>__<client>__*.json`
2. Check current time matches schedule
3. Check logs for errors: `tail -50 logs/scheduler_daemon.log`

### Low Quality Scores
1. Run unknown brands analysis: `.venv/bin/python3 tools/analyze_unknown_brands.py`
2. Check audit log: `tail -20 output/<retailer>/<client>/runs/audit_log.jsonl`
3. Manually inspect recent run files in `output/<retailer>/<client>/runs/`

### MacBook Going to Sleep
1. Ensure using `start_scheduler_caffeinated.sh` (not `start_scheduler.sh`)
2. Ensure MacBook is plugged in (caffeinate `-s` flag only works on AC power)
3. Check caffeinate is running: `ps aux | grep caffeinate`

---

## Configuration

### Environment Variables
Set in shell before starting scheduler:

```bash
export SCHEDULER_KEYWORD_TIMEOUT=180      # Timeout per keyword (seconds)
export SCHEDULER_JOB_BUDGET_SEC=600       # Max time per client job (seconds)
export SCHEDULER_MAX_CONCURRENCY=5        # Max concurrent retailer jobs
export SCHEDULER_DUE_WINDOW_MIN=2         # Time window for schedule matching (minutes)
export SCHEDULER_MISSING_GAP_SEC=120      # Wait before HTML processing (seconds)
export SCHEDULER_PROCESS_TIMEOUT_SEC=300  # HTML processing timeout (seconds)
```

### Master Control
Edit `config/scheduler_control.json`:
```json
{
  "enabled": true,
  "notes": "Master override for scheduler"
}
```

Set `"enabled": false` to disable ALL scheduling without stopping the daemon.

---

## Next Steps

1. **Start the scheduler**: `./start_scheduler_caffeinated.sh`
2. **Monitor the first few runs**: `tail -f logs/scheduler_daemon.log`
3. **Check audit results** after first scrapes complete
4. **Run unknown brands analysis** after 24 hours: `.venv/bin/python3 tools/analyze_unknown_brands.py 200`
5. **Review and add missing brands** to improve quality scores

---

## Tools Reference

### Filter Schedules
```bash
# Preview changes
.venv/bin/python3 tools/filter_schedules.py --dry-run

# Apply changes
.venv/bin/python3 tools/filter_schedules.py
```

### Audit Single Run
```bash
.venv/bin/python3 utils/scrape_audit.py output/<retailer>/<client>/runs/<file>.json
```

### Analyze Unknown Brands
```bash
# Analyze last 100 runs
.venv/bin/python3 tools/analyze_unknown_brands.py

# Analyze last 500 runs
.venv/bin/python3 tools/analyze_unknown_brands.py 500
```
