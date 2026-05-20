# Scheduler GUI Guide

## Overview

The Scheduler tab in the Retail Ad Monitor app provides complete control and monitoring of automated scraping schedules. All scheduler functionality is now integrated into the Apple app GUI.

## Accessing the Scheduler Tab

1. Launch the Retail Ad Monitor app
2. Click on the **"Scheduler"** tab (third tab after "Ad Scraper" and "Screen Capture")

## Features

### 1. Scheduler Status

**Real-time status display showing:**
- 🟢 **Running** / 🔴 **Stopped** indicator
- **Active schedules count** (enabled/total)
- **Last successful run** timestamp
- **Detailed status information**

Status auto-refreshes every 30 seconds.

### 2. Control Buttons

#### Main Controls
- **▶️ Start Scheduler** - Starts the scheduler with caffeinate (keeps MacBook awake)
- **⏹️ Stop Scheduler** - Stops the scheduler daemon
- **🔄 Restart** - Restarts the scheduler (stop + start)
- **🔃 Refresh Status** - Manually refresh status display

#### Secondary Controls
- **📋 View Logs** - Opens scheduler daemon log in default text editor
- **📊 Run History** - View historical scrape runs
- **⚙️ Edit Schedules** - Opens schedules folder in Finder
- **📂 Open Folder** - Opens output folder in Finder

### 3. Active Schedules Management

**Tree view showing all schedules with:**
- Retailer (Amazon, Walmart, Target, Instacart)
- Client name
- Number of keywords
- Scheduled times
- Days of week
- Status (✅ Enabled / ❌ Disabled)

**Filter options:**
- All schedules
- Enabled only
- Disabled only
- By client (Proactiv, Garanimals, Community Coffee, MilkPEP)

**Right-click context menu:**
- Enable schedule
- Disable schedule
- View detailed JSON configuration

### 4. Recent Audit Results

**Quality monitoring for recent scrapes:**
- Timestamp of each scrape
- Retailer and keyword
- **Quality score** (0-100)
- Total ads captured
- Blank ads count (missing images)
- Unknown brands count

**Color coding:**
- ✅ Green: Score ≥ 80 (excellent)
- ⚠️ Yellow: Score 50-79 (needs attention)
- ❌ Red: Score < 50 (poor quality)

**Controls:**
- Adjust number of recent audits to display (5-50)
- Refresh button

### 5. Unknown Brands Analysis

**Identify patterns in brand detection issues:**
- Analyze last N runs (50-500)
- Statistics by retailer and ad type
- Suggested brand additions based on patterns
- Sample product titles with unknown brands

**Usage:**
1. Set number of runs to analyze
2. Click **🔍 Analyze**
3. Review results in text area
4. Detailed report saved to `logs/unknown_brands_report.json`

## Current Configuration

### Active Clients (as of setup)
- **Proactiv** - 4 schedules across retailers
- **Garanimals (Garan)** - 1 schedule (Walmart only)
- **Community Coffee** - 8 schedules (2 keyword sets × 4 retailers)
- **MilkPEP** - 4 schedules across retailers

**Total: 17 active schedules**

### Disabled
- All Kroger schedules (due to Akamai detection issues)
- All other clients (Barilla, Blue Bunny, Bomb Pop, etc.)

### Front Page Capture
- **Schedule**: Daily at 12:05 PM
- **Retailers**: Walmart, Amazon, Instacart, Target
- **Config**: `schedules/frontpage_capture.json`

## Workflow Examples

### Starting the Scheduler
1. Go to Scheduler tab
2. Check status - should show 🔴 Stopped
3. Click **▶️ Start Scheduler**
4. Wait 2 seconds for confirmation
5. Status should update to 🟢 Running
6. MacBook will stay awake while plugged in

### Monitoring Scrape Quality
1. Go to Scheduler tab
2. Scroll to "Recent Audit Results"
3. Review quality scores
4. Look for patterns:
   - Low scores indicate issues
   - High blank ads = image capture problems
   - High unknown brands = brand detection needs improvement

### Enabling/Disabling a Client
1. Go to Scheduler tab
2. Scroll to "Active Schedules"
3. Find the client's schedules in the tree
4. Right-click on a schedule
5. Select "Enable" or "Disable"
6. Scheduler will pick up changes on next cycle

### Investigating Unknown Brands
1. Go to Scheduler tab
2. Scroll to "Unknown Brands Analysis"
3. Set analysis limit (e.g., 200 runs)
4. Click **🔍 Analyze**
5. Wait for results
6. Review suggested brand additions
7. Add promising brands to `data/brands.json`

## Integration with Existing Features

### Daemon Controls in Footer
The main GUI footer still has daemon control buttons:
- **🔄 Refresh** - Quick status check
- **▶️ Start** - Alternative start button
- **⏹️ Stop** - Alternative stop button
- **📅 See Full Schedule** - View all schedules

These work in conjunction with the Scheduler tab controls.

### Schedule Settings in Ad Scraper Tab
The "Schedule Settings" section in the Ad Scraper tab is for **creating new schedules**:
- Set runs per day
- Choose times
- Select days of week
- Save schedule for current client

The Scheduler tab is for **managing existing schedules**.

## Files and Locations

### Scheduler Files
- **Start script**: `start_scheduler_caffeinated.sh`
- **Entry point**: `scheduler_entry.py`
- **Daemon**: `scheduler_daemon.py`
- **Schedules**: `schedules/*.json`
- **Master control**: `config/scheduler_control.json`

### Logs
- **Main log**: `logs/scheduler_daemon.log`
- **Execution flow**: `logs/scheduler_execution_flow.log`
- **Audit logs**: `output/<retailer>/<client>/runs/audit_log.jsonl`

### Tools
- **Filter schedules**: `tools/filter_schedules.py`
- **Audit scrapes**: `utils/scrape_audit.py`
- **Analyze brands**: `tools/analyze_unknown_brands.py`

## Troubleshooting

### Scheduler Won't Start
1. Check if already running (look for 🟢 in status)
2. Check `logs/scheduler.lock` - delete if stale
3. Check `config/scheduler_control.json` - ensure `"enabled": true`
4. View logs for errors

### Schedules Not Running
1. Verify schedule is enabled (✅ in tree view)
2. Check current time matches schedule
3. View scheduler logs for errors
4. Ensure retailer is not globally disabled (e.g., Kroger)

### Low Quality Scores
1. Check audit log for specific issues
2. Run unknown brands analysis
3. Review recent run files manually
4. Check scraper logs for errors

### GUI Not Showing Scheduler Tab
1. Ensure `gui/scheduler_tab.py` exists
2. Check `gui/__init__.py` is present
3. Restart the app
4. Check console for import errors

## Best Practices

1. **Monitor regularly** - Check audit results daily
2. **Review unknown brands** - Run analysis weekly
3. **Keep MacBook plugged in** - Caffeinate only works on AC power
4. **Don't over-schedule** - Respect retailer rate limits
5. **Test changes** - Use dry-run mode when filtering schedules
6. **Back up schedules** - Keep copies of working configurations

## Advanced Usage

### Command Line Tools

All GUI functions can also be run from command line:

```bash
# Start scheduler
./start_scheduler_caffeinated.sh

# Stop scheduler
rm logs/scheduler.lock && pkill -f scheduler_entry.py

# Filter schedules
.venv/bin/python3 tools/filter_schedules.py --dry-run

# Audit a run
.venv/bin/python3 utils/scrape_audit.py output/walmart/Proactiv/runs/file.json

# Analyze brands
.venv/bin/python3 tools/analyze_unknown_brands.py 200
```

### Customizing the GUI

The scheduler tab is modular and can be extended:
- Edit `gui/scheduler_tab.py`
- Add new sections with `_build_*_section()` methods
- Integrate with existing app methods via `self.app`

## Support

For issues or questions:
1. Check `logs/scheduler_daemon.log`
2. Review `SCHEDULER_RESTART_GUIDE.md`
3. Check `logs/gui_boot.log` for GUI startup issues
