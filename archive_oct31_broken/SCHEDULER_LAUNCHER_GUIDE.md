# Scheduler Launcher Scripts Guide

## 🚀 Quick Start

### **Terminal.app (Default macOS Terminal):**
```bash
./start_scheduler_and_tail.sh
```

### **iTerm2:**
```bash
./start_scheduler_and_tail_iterm.sh
```

---

## 📋 What It Does

### **Terminal.app script:**
1. ✅ **Shows next 5 scheduled runs** with countdown timers
2. ✅ Launch `scheduler_entry.py` in a new window
3. ✅ Open a second window tailing both log files
4. ✅ Auto-detect Python (venv > PYTHON_EXEC > system)
5. ✅ Support both schedule schemas (old & new)
6. ✅ Create log files if they don't exist
7. ✅ Handle spaces in paths correctly
8. ✅ Respect `SCRAPER_HOME` environment variable

### **iTerm2 script:**
Same features but opens tabs instead of windows

---

## 🎯 Features

### **📅 Next 5 Scheduled Runs Display:**
Shows upcoming scrapes with:
- Day, date, and time
- Countdown timer (e.g., "2h15m" or "45m")
- Retailer and client name
- Supports both schedule formats

**Example output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Next 5 Scheduled Runs (local time)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Found 12 future trigger(s). Showing next 5:

 • Thu 2025-10-16 10:00  (15m)  [kroger]  blue bunny
 • Thu 2025-10-16 14:30  (4h45m)  [instacart]  stonyfield
 • Fri 2025-10-17 09:00  (1d 23h15m)  [kroger]  breyers
 • Fri 2025-10-17 10:00  (1d 0h15m)  [kroger]  blue bunny
 • Mon 2025-10-20 09:00  (4d 23h15m)  [walmart]  halo top
```

### **🐍 Smart Python Detection:**
Priority order:
1. `PYTHON_EXEC` environment variable
2. `.venv/bin/python` (virtual environment)
3. `python3` (system Python)

### **📊 Dual-Schema Support:**
Handles both schedule formats:
- **New:** `{"days": [...], "times": [["8","00","AM"], ...]}`
- **Old:** `{"schedule": {"monday": ["08:00", ...], ...}}`

### **Environment Variables:**
```bash
# Use custom Python interpreter
export PYTHON_EXEC=/usr/local/bin/python3.11
./start_scheduler_and_tail.sh

# Use custom data directory
export SCRAPER_HOME=/path/to/workdir
./start_scheduler_and_tail.sh
```

### **Log Tailing:**
- Tails **both** main log and execution flow log
- Shows last 200 lines
- Uses `tail -F` (follows file rotation)
- Auto-creates log files if missing

---

## 📊 Tail Options

### **Option 1: Main Log Only (Default)**
```bash
tail -n 200 -F logs/scheduler_daemon.log
```
Shows:
- Job starts/completions
- Success/failure/timeout messages
- [retailer] prefixed logs

### **Option 2: Both Logs (Uncomment in script)**
```bash
tail -n 100 -F logs/scheduler_daemon.log logs/scheduler_execution_flow.log
```
Shows:
- Main log (as above)
- Execution flow log (detailed debug info)

**To enable:** Edit the script and uncomment the second `TAIL_CMD` line.

---

## 🔧 Customization

### **Change Tail Lines:**
```bash
# Show last 500 lines instead of 200
TAIL_CMD="... tail -n 500 -F ..."
```

### **Add Filtering:**
```bash
# Only show Kroger logs
TAIL_CMD="... tail -n 200 -F \"$MAIN_LOG\" | grep \"\\[kroger\\]\""
```

### **Different Log File:**
```bash
# Tail execution flow instead
TAIL_CMD="... tail -n 200 -F \"$EXEC_FLOW_LOG\""
```

---

## 💡 Usage Tips

### **If Scheduler Already Running:**
- Entry script will detect existing lock
- Shows: "Scheduler already running (lock held). Exiting."
- Tail window still opens to watch existing daemon

### **Stopping the Scheduler:**
```bash
# In daemon window, press:
Ctrl+C

# Or kill from command line:
pkill -f scheduler_daemon.py
```

### **Closing Windows:**
- Close tail window: Stops tailing (daemon keeps running)
- Close daemon window: Stops scheduler
- Both windows independent

### **Multiple Launches:**
- Safe to run script multiple times
- Only one daemon can run (fcntl lock)
- Multiple tail windows OK

---

## 🔍 Log Filtering Examples

### **In the Tail Window:**
```bash
# Filter by retailer (Ctrl+C first, then run)
tail -F logs/scheduler_daemon.log | grep "\[kroger\]"

# Filter by status
tail -F logs/scheduler_daemon.log | grep -E "(SUCCESS|TIMEOUT|FAIL)"

# Specific keyword
tail -F logs/scheduler_daemon.log | grep "ice cream"
```

### **From Command Line:**
```bash
# Recent errors
grep "ERROR" logs/scheduler_daemon.log | tail -20

# Today's successes
grep "$(date +%Y-%m-%d)" logs/scheduler_daemon.log | grep SUCCESS

# Count timeouts
grep "TIMEOUT keyword" logs/scheduler_daemon.log | wc -l
```

---

## 📁 File Locations

### **Scripts:**
- `start_scheduler_and_tail.sh` - Terminal.app version
- `start_scheduler_and_tail_iterm.sh` - iTerm2 version

### **Logs (default):**
- `logs/scheduler_daemon.log` - Main scheduler log
- `logs/scheduler_execution_flow.log` - Detailed execution log
- `logs/scheduler.lock` - Single-instance lock file
- `logs/scheduler.pid` - Process ID file

### **Logs (custom SCRAPER_HOME):**
- `$SCRAPER_HOME/logs/scheduler_daemon.log`
- `$SCRAPER_HOME/logs/scheduler_execution_flow.log`

---

## 🐛 Troubleshooting

### **"Permission denied":**
```bash
chmod +x start_scheduler_and_tail.sh
```

### **"Python not found":**
```bash
export PYTHON_EXEC=/path/to/python3
./start_scheduler_and_tail.sh
```

### **"Log file not found":**
- Script creates it automatically
- Check `SCRAPER_HOME` is correct
- Verify `logs/` directory permissions

### **Windows don't open:**
- Check Terminal.app/iTerm2 is installed
- Try running commands manually:
  ```bash
  python3 scheduler_entry.py
  tail -F logs/scheduler_daemon.log
  ```

### **Scheduler won't start:**
```bash
# Check for existing daemon
ps -ef | grep scheduler_daemon.py

# Check lock file
ls -l logs/scheduler.lock

# Remove stale lock
rm -f logs/scheduler.lock logs/scheduler.pid
```

---

## 🎨 iTerm2 vs Terminal.app

### **Terminal.app:**
- ✅ Default macOS terminal
- ✅ Opens new windows
- ✅ Sets window titles
- ❌ Less customizable

### **iTerm2:**
- ✅ Opens tabs in same window
- ✅ Sets tab names
- ✅ Better color support
- ✅ More features (split panes, etc.)
- ❌ Requires iTerm2 installation

**Choose based on your preference!**

---

## 📝 Example Session

```bash
$ ./start_scheduler_and_tail.sh
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Scheduler Launcher + Log Tailer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📂 Project root:  /Users/dan/Amazon_Scrape
🏠 SCRAPER_HOME:  /Users/dan/Amazon_Scrape
📝 Main log:      /Users/dan/Amazon_Scrape/logs/scheduler_daemon.log
📊 Exec flow log: /Users/dan/Amazon_Scrape/logs/scheduler_execution_flow.log

✅ Started scheduler (in new Terminal window)
✅ Tailing logs (in another Terminal window)

💡 Tips:
   - Close Terminal windows to stop tailing
   - Daemon window shows start/stop and lock messages
   - Press Ctrl+C in daemon window to stop scheduler

🔍 Filter logs:
   grep "\[kroger\]" /Users/dan/Amazon_Scrape/logs/scheduler_daemon.log
   grep "SUCCESS keyword" /Users/dan/Amazon_Scrape/logs/scheduler_daemon.log
```

**Two new Terminal windows open:**
1. **"Scheduler Daemon"** - Running scheduler
2. **"Scheduler Logs"** - Tailing logs in real-time

---

## ✅ Summary

- ✅ **Created:** `start_scheduler_and_tail.sh` (Terminal.app)
- ✅ **Created:** `start_scheduler_and_tail_iterm.sh` (iTerm2)
- ✅ **Made executable:** Both scripts
- ✅ **Robust:** Handles spaces, creates logs, respects env vars
- ✅ **Documented:** Full guide with examples

**Ready to use! Just run `./start_scheduler_and_tail.sh`** 🚀
