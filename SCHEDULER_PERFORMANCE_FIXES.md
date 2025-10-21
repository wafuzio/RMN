# Scheduler Performance & Timeout Fixes

## 🎯 Problem Identified

From your log at 09:10:
```
2025-10-16 09:10:00 - INFO - → DUE: kroger / blue bunny @ 09:10
2025-10-16 09:14:59 - ERROR - Timeout scraping keyword 'ice cream bar' for blue bunny
2025-10-16 09:15:44 - INFO - Completed scheduled scrape for blue bunny: 0/1 keywords successful
```

**Issues:**
1. **5-minute timeout** (300s) was too long - keyword timed out
2. **Synchronous execution** - blocked other retailers for 5m44s
3. **No process group cleanup** - Chromium children not killed on timeout
4. **Wasted post-processing** - Ran even with 0 successful scrapes

---

## ✅ All Fixes Implemented

### **1. Configurable Keyword Timeout** ✅
**Default:** 180 seconds (3 minutes) instead of 300 seconds

```python
self.keyword_timeout = int(os.environ.get("SCHEDULER_KEYWORD_TIMEOUT", "180"))
```

**Override:**
```bash
export SCHEDULER_KEYWORD_TIMEOUT=120  # 2 minutes
./restart_scheduler.sh
```

---

### **2. Process Group Cleanup on Timeout** ✅
**Problem:** Old code used `subprocess.run()` which doesn't kill Chromium children

**Fix:** Use `Popen` with `start_new_session=True` and `os.killpg()`:
```python
proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    start_new_session=True  # New process group
)

try:
    stdout, stderr = proc.communicate(timeout=self.keyword_timeout)
except subprocess.TimeoutExpired:
    # Kill entire process group (scraper + Chromium)
    os.killpg(proc.pid, signal.SIGKILL)
```

---

### **3. Job Budget Enforcement** ✅
**Default:** 600 seconds (10 minutes) per client

```python
self.job_budget = int(os.environ.get("SCHEDULER_JOB_BUDGET_SEC", "600"))
```

**Stops early if budget exceeded:**
```python
for i, keyword in enumerate(keywords, 1):
    if time.time() - job_start > self.job_budget:
        self.logger.warning(f"Job budget exceeded; stopping early")
        break
```

**Override:**
```bash
export SCHEDULER_JOB_BUDGET_SEC=900  # 15 minutes
```

---

### **4. Skip Post-Processing if No Successes** ✅
**Saves time when all keywords fail:**
```python
if success_count == 0:
    self.logger.info(f"Skipping HTML post-processing (no successful scrapes)")
    return
```

---

### **5. Async Job Execution** ✅
**Problem:** Synchronous execution blocked other retailers

**Fix:** Launch jobs in background threads with concurrency control

**Default:** 2 concurrent retailers
```python
self.max_concurrent = int(os.environ.get("SCHEDULER_MAX_CONCURRENCY", "2"))
```

**Benefits:**
- Kroger @ 09:10 and Instacart @ 09:10 can run simultaneously
- Per-client locks still prevent same-client overlap
- Concurrency cap prevents resource exhaustion

**Override:**
```bash
export SCHEDULER_MAX_CONCURRENCY=3  # 3 concurrent retailers
```

---

### **6. Keyword Truncation (Respect "runs")** ✅
**Honors the `"runs"` field in schedule_config.json:**
```json
{
  "runs": 5,
  "keywords": ["kw1", "kw2", "kw3", "kw4", "kw5", "kw6", "kw7"]
}
```
**Result:** Only first 5 keywords run

---

## 📊 Performance Comparison

### **Before (Your 09:10 Run):**
```
09:10:00 - Job starts
09:14:59 - Timeout (300s)
09:15:44 - Post-processing (wasted)
Total: 5m44s
Success: 0/1
```

### **After (With Fixes):**
```
09:10:00 - Job starts (async)
09:13:00 - Timeout (180s)
09:13:00 - Skip post-processing
Total: 3m0s
Success: 0/1
Other retailers: Can start at 09:10 too!
```

---

## 🚀 Configuration Examples

### **Fast & Aggressive (Development):**
```bash
export SCHEDULER_KEYWORD_TIMEOUT=60      # 1 minute per keyword
export SCHEDULER_JOB_BUDGET_SEC=300      # 5 minutes per job
export SCHEDULER_MAX_CONCURRENCY=4       # 4 concurrent retailers
```

### **Conservative (Production):**
```bash
export SCHEDULER_KEYWORD_TIMEOUT=240     # 4 minutes per keyword
export SCHEDULER_JOB_BUDGET_SEC=900      # 15 minutes per job
export SCHEDULER_MAX_CONCURRENCY=2       # 2 concurrent retailers
```

### **Default (Balanced):**
```bash
# No exports needed - uses defaults:
# KEYWORD_TIMEOUT=180 (3 min)
# JOB_BUDGET=600 (10 min)
# MAX_CONCURRENCY=2
```

---

## 🔍 Monitoring

### **Watch Active Jobs:**
```bash
# Main log shows async launches
tail -f logs/scheduler_daemon.log | grep -E "(DUE|async|Timeout|Completed)"
```

### **Check Concurrency:**
```bash
# See how many jobs are running
tail -f logs/scheduler_daemon.log | grep "Concurrency cap"
```

### **Monitor Timeouts:**
```bash
# Track timeout patterns
grep "TIMEOUT" logs/scheduler_execution_flow.log
```

---

## 📝 Files Modified

1. **`scheduler_daemon.py`**
   - Added `signal` import
   - Added timeout/concurrency config in `__init__`
   - Replaced `subprocess.run()` with `Popen` + process group cleanup
   - Added job budget enforcement
   - Added skip-if-no-successes logic
   - Added `_start_job_async()` method
   - Updated monitor loop for async execution
   - Added thread cleanup

---

## ✅ Testing

### **Test Timeout Handling:**
```bash
# Set aggressive timeout
export SCHEDULER_KEYWORD_TIMEOUT=30
./restart_scheduler.sh

# Schedule a scrape and watch for 30s timeout
tail -f logs/scheduler_daemon.log
```

### **Test Concurrency:**
```bash
# Create 3 schedules for same time
# Set max concurrency to 2
export SCHEDULER_MAX_CONCURRENCY=2

# Should see: "Concurrency cap reached (2/2); delaying <client>"
```

### **Test Job Budget:**
```bash
# Set low budget
export SCHEDULER_JOB_BUDGET_SEC=120

# Schedule with many keywords
# Should see: "Job budget exceeded; stopping early"
```

---

## 🎯 Expected Behavior Now

1. **Faster failures** - 3 min timeout instead of 5 min
2. **Clean cleanup** - Chromium processes killed on timeout
3. **Parallel execution** - Multiple retailers run simultaneously
4. **No wasted work** - Skip post-processing if no successes
5. **Budget enforcement** - Jobs stop if taking too long
6. **Keyword limiting** - Respects `"runs"` field

---

## 🚨 Important Notes

### **Lock Files:**
- Still created at `output/<retailer>/<client>/locks/run.lock`
- Prevent same-client overlap (even with async)
- Auto-cleared after 30 minutes if stale

### **Thread Safety:**
- Each client runs in its own thread
- Threads are daemon threads (exit with main process)
- Thread cleanup happens every minute

### **Logging:**
- Async launches logged as `SCRAPE_LAUNCHED_ASYNC`
- Concurrency delays logged as `Concurrency cap reached`
- Timeouts logged with actual timeout value

---

**All performance fixes implemented! Restart the daemon to apply.** 🚀
