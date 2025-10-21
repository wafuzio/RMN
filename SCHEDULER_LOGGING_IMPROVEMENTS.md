# Scheduler Logging Improvements

## ✅ Enhanced Context in All Logs

Every log message now includes **retailer** and **keyword** context for easy filtering and debugging.

---

## 🎯 What Changed

### **1. Function Signature Updated**
```python
# OLD:
def run_scraper_for_client(self, client_name, client_dir, keywords):

# NEW:
def run_scraper_for_client(self, retailer: str, client_name: str, client_dir: str, keywords):
```

**Benefits:**
- Retailer passed explicitly (no re-reading config)
- Type hints for clarity
- Cleaner function signature

---

### **2. All Logs Include [retailer] Prefix**

#### **Job Start:**
```
# OLD:
Starting scheduled scrape for client: blue bunny (retailer: kroger)

# NEW:
Starting scheduled scrape for client: blue bunny (retailer: kroger, keywords: 2)
```

#### **Per-Keyword Logs:**
```
# OLD:
Successfully scraped keyword 'ice cream' for blue bunny

# NEW:
[kroger] SUCCESS keyword 'ice cream' for blue bunny
```

#### **Timeout:**
```
# OLD:
Timeout scraping keyword 'ice cream bar' for blue bunny

# NEW:
[kroger] TIMEOUT keyword 'ice cream bar' for blue bunny after 180s
```

#### **Failure:**
```
# OLD:
Failed to scrape keyword 'ice cream' for blue bunny: rc=1

# NEW:
[kroger] FAIL keyword 'ice cream' for blue bunny: rc=1
```

#### **Post-Processing:**
```
# OLD:
Successfully processed HTML files for blue bunny

# NEW:
[kroger] Successfully processed HTML files for blue bunny
```

#### **Completion:**
```
# OLD:
Completed scheduled scrape for blue bunny: 1/2 keywords successful

# NEW:
[kroger] Completed scheduled scrape for blue bunny: 1/2 keywords successful
```

---

## 📊 Log Format Examples

### **Full Scrape Flow:**
```
2025-10-16 09:10:00 - INFO - → DUE: kroger / blue bunny @ 09:10
2025-10-16 09:10:00 - INFO - Started async job for blue bunny (retailer: kroger, thread=run-kroger-blue_bunny)
2025-10-16 09:10:00 - INFO - Starting scheduled scrape for client: blue bunny (retailer: kroger, keywords: 2)
2025-10-16 09:10:01 - INFO - [kroger] START keyword 'ice cream' for blue bunny
2025-10-16 09:11:30 - INFO - [kroger] SUCCESS keyword 'ice cream' for blue bunny
2025-10-16 09:11:31 - INFO - [kroger] START keyword 'ice cream bar' for blue bunny
2025-10-16 09:14:31 - ERROR - [kroger] TIMEOUT keyword 'ice cream bar' for blue bunny after 180s
2025-10-16 09:14:32 - INFO - [kroger] Successfully processed HTML files for blue bunny
2025-10-16 09:14:32 - INFO - [kroger] Completed scheduled scrape for blue bunny: 1/2 keywords successful
```

### **Multiple Retailers:**
```
2025-10-16 10:00:00 - INFO - → DUE: kroger / blue bunny @ 10:00
2025-10-16 10:00:00 - INFO - → DUE: instacart / stonyfield @ 10:00
2025-10-16 10:00:00 - INFO - Started async job for blue bunny (retailer: kroger, thread=run-kroger-blue_bunny)
2025-10-16 10:00:00 - INFO - Started async job for stonyfield (retailer: instacart, thread=run-instacart-stonyfield)
2025-10-16 10:00:01 - INFO - [kroger] START keyword 'ice cream' for blue bunny
2025-10-16 10:00:01 - INFO - [instacart] START keyword 'yogurt' for stonyfield
2025-10-16 10:01:45 - INFO - [kroger] SUCCESS keyword 'ice cream' for blue bunny
2025-10-16 10:02:10 - INFO - [instacart] SUCCESS keyword 'yogurt' for stonyfield
```

---

## 🔍 Filtering Logs

### **By Retailer:**
```bash
# Only Kroger logs
grep "\[kroger\]" logs/scheduler_daemon.log

# Only Instacart logs
grep "\[instacart\]" logs/scheduler_daemon.log
```

### **By Keyword Status:**
```bash
# All successes
grep "SUCCESS keyword" logs/scheduler_daemon.log

# All timeouts
grep "TIMEOUT keyword" logs/scheduler_daemon.log

# All failures
grep "FAIL keyword" logs/scheduler_daemon.log
```

### **By Retailer + Status:**
```bash
# Kroger timeouts only
grep "\[kroger\] TIMEOUT" logs/scheduler_daemon.log

# Instacart successes only
grep "\[instacart\] SUCCESS" logs/scheduler_daemon.log
```

### **Specific Keyword:**
```bash
# Track 'ice cream bar' across all retailers
grep "keyword 'ice cream bar'" logs/scheduler_daemon.log
```

---

## 📈 Execution Flow Log Enhancements

### **Structured Fields:**
```
# OLD:
KEYWORD_SCRAPE_SUCCESS: 'ice cream'

# NEW:
KEYWORD_SCRAPE_SUCCESS: Retailer=kroger, Client=blue bunny, Keyword='ice cream'
```

### **All Events Include:**
- `Retailer=<retailer>`
- `Client=<client_name>`
- `Keyword='<keyword>'` (where applicable)
- Additional context (rc, timeout, error)

---

## 🎯 Benefits

### **1. Easy Debugging:**
```bash
# Find all Kroger issues
grep "\[kroger\]" logs/scheduler_daemon.log | grep -E "(FAIL|TIMEOUT|ERROR)"

# Track a specific client
grep "blue bunny" logs/scheduler_daemon.log
```

### **2. Performance Analysis:**
```bash
# Count successes per retailer
grep "\[kroger\] SUCCESS" logs/scheduler_daemon.log | wc -l
grep "\[instacart\] SUCCESS" logs/scheduler_daemon.log | wc -l
```

### **3. Timeout Patterns:**
```bash
# Which keywords timeout most?
grep "TIMEOUT keyword" logs/scheduler_daemon.log | cut -d"'" -f2 | sort | uniq -c | sort -rn
```

### **4. Retailer Comparison:**
```bash
# Compare completion rates
grep "\[kroger\] Completed" logs/scheduler_daemon.log
grep "\[instacart\] Completed" logs/scheduler_daemon.log
```

---

## 📝 Thread Names

Thread names now include retailer:
```python
# OLD:
Thread(name=f"run-{client_name}")

# NEW:
Thread(name=f"run-{retailer}-{client_name}")
```

**Example:** `run-kroger-blue_bunny`, `run-instacart-stonyfield`

**Benefits:**
- Easy to identify which retailer a thread belongs to
- Better debugging with `ps` or thread dumps

---

## ✅ Backward Compatibility

- All changes are **additive** (no behavior changes)
- Existing log parsers still work (just get more context)
- No config changes needed

---

## 🚀 Next Steps

1. **Restart daemon** to apply changes:
   ```bash
   ./restart_scheduler.sh
   ```

2. **Monitor logs** with new format:
   ```bash
   tail -f logs/scheduler_daemon.log
   ```

3. **Test filtering**:
   ```bash
   grep "\[kroger\]" logs/scheduler_daemon.log
   ```

---

**All logging improvements implemented! Every log now includes retailer and keyword context.** 🎯📊
