#!/usr/bin/env python3
"""
Scheduler Daemon for Kroger TOA Scraper

This daemon runs independently and monitors all client schedule configurations,
executing scraping tasks at the specified times for each client.
"""

import os
import sys
import json
import time
import logging
import subprocess
import threading
import calendar
import signal
from datetime import datetime, timedelta
from pathlib import Path
import glob

# Import shared schedule library
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schedules.schedules_lib import scan_schedules, now_in_tz

# --- Time parsing and normalization helpers ---

def _parse_time_12h(tup):
    """
    Accepts ["8","00","AM"] or ["12","05","AM"] or ["10","00","PM"] and returns "HH:MM" 24h zero-padded.
    Also accepts already-formatted "8:00" or "08:00".
    """
    if isinstance(tup, str):
        # tolerate "8:00" / "08:00"
        parts = tup.strip().split(":")
        if len(parts) == 2:
            hh, mm = parts
            hh = int(hh)
            mm = int(mm)
            return f"{hh:02d}:{mm:02d}"
        raise ValueError(f"Unrecognized time string: {tup}")

    if not isinstance(tup, (list, tuple)) or len(tup) < 2:
        raise ValueError(f"Unrecognized time tuple: {tup}")

    # ["8","00","AM"] or ["8","00"] (assume 24h if no AM/PM)
    hh = int(tup[0])
    mm = int(tup[1])
    ampm = tup[2].strip().upper() if len(tup) >= 3 else None

    if ampm in ("AM","PM"):
        if ampm == "AM":
            if hh == 12: hh = 0
        else:  # PM
            if hh != 12: hh += 12

    return f"{hh:02d}:{mm:02d}"

def _normalize_days(days):
    """
    Accept "Monday" or "monday" or ["Mon", ...] → return a set of lowercase full names ("monday"...)
    """
    full = []
    for d in days:
        s = str(d).strip().lower()
        # Expand abbreviations if needed
        mapping = {
            'mon': 'monday','tue':'tuesday','wed':'wednesday','thu':'thursday',
            'thur':'thursday','fri':'friday','sat':'saturday','sun':'sunday'
        }
        full.append(mapping.get(s[:3], s))
    return set(full)

def _load_schedule_config(cfg_path):
    """
    Supports both schemas:
    - {"schedule": {"monday":["08:00","14:00"], ...}, "retailer": "...", "client": "..."}
    - {"days":[...], "times":[["8","00","AM"],...], "retailer":"...", "client":"..."}
    Returns:
      {
        "retailer": "...",
        "client": "...",
        "days": set(["monday",...]),
        "times": set(["08:00","14:00",...]),
        "keywords": [...],
        "raw_path": cfg_path,
        "log_dir": os.path.dirname(cfg_path)
      }
    """
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    retailer = data.get("retailer","").strip().lower()
    client = data.get("client","").strip()
    keywords = data.get("keywords", [])

    times = set()
    days = set()

    if "schedule" in data and isinstance(data["schedule"], dict):
        # Old schema
        for day, tlist in data["schedule"].items():
            days.add(str(day).strip().lower())
            for t in tlist:
                times.add(_parse_time_12h(t))
    else:
        # New schema
        days = _normalize_days(data.get("days", []))
        for t in data.get("times", []):
            times.add(_parse_time_12h(t))

    return {
        "retailer": retailer,
        "client": client,
        "days": days,
        "times": times,
        "keywords": keywords,
        "raw_path": cfg_path,
        "log_dir": os.path.dirname(cfg_path)
    }

def _now_local():
    """Return (datetime, day_name_lowercase, HH:MM)"""
    now = datetime.now()
    day = calendar.day_name[now.weekday()].lower()  # e.g., "thursday"
    hhmm = now.strftime("%H:%M")
    return now, day, hhmm

def _sleep_until_next_minute():
    """Sleep until the next minute boundary (aligned to :00 seconds)"""
    now = datetime.now()
    nxt = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    sleep_time = max(0.0, (nxt - now).total_seconds())
    time.sleep(sleep_time)

def _running_lock_dir(schedule):
    """Get lock directory for a schedule (next to config file)"""
    return os.path.join(schedule["log_dir"], "locks")

def _run_with_lock(schedule, fn):
    """
    Execute fn() with a lock file to prevent concurrent runs.
    Returns True if executed, False if skipped due to lock.
    """
    ldir = _running_lock_dir(schedule)
    os.makedirs(ldir, exist_ok=True)
    lock = os.path.join(ldir, "run.lock")
    
    if os.path.exists(lock):
        # Check if stale (older than 30 minutes)
        age = time.time() - os.path.getmtime(lock)
        if age > 1800:  # 30 minutes
            try:
                os.remove(lock)
            except:
                pass
        else:
            print(f"⏭️  Skipping (active lock): {lock}")
            return False
    
    # Acquire lock
    try:
        with open(lock, "w") as f:
            f.write(f"pid={os.getpid()} ts={datetime.now().isoformat()}\n")
    except Exception as e:
        print(f"⚠️  Could not acquire lock: {e}")
        return False
    
    # Execute with lock
    try:
        fn()
    finally:
        try:
            os.remove(lock)
        except:
            pass
    
    return True

# Old single-instance lock functions removed - now handled by scheduler_entry.py

class SchedulerDaemon:
    # Retailer script mapping (scripts live at project root)
    SCRIPT_MAP = {
        "kroger": "kroger_search_and_capture.py",
        "instacart": "instacart_search_and_capture.py",
        "walmart": "walmart_search_and_capture.py",
        "amazon": "amazon_search_and_capture.py",
    }
    
    def __init__(self):
        """Initialize the scheduler daemon"""
        # Code directory (where scripts live)
        self.code_dir = Path(__file__).resolve().parent
        # Data root (where output/, logs/, etc. live). Defaults to code_dir unless SCRAPER_HOME is set
        self.root_dir = Path(os.environ.get("SCRAPER_HOME", str(self.code_dir))).resolve()
        # Backward-compatible alias
        self.project_root = self.code_dir
        # Output directory now roots under SCRAPER_HOME
        self.output_dir = self.root_dir / "output"
        self.running = False
        self.threads = {}
        self.last_run_times = {}  # Track last run times to avoid duplicates
        self.inflight = {}  # run_key -> thread for async jobs
        
        # Configurable timeouts and concurrency
        self.keyword_timeout = int(os.environ.get("SCHEDULER_KEYWORD_TIMEOUT", "180"))  # 3 minutes default
        self.job_budget = int(os.environ.get("SCHEDULER_JOB_BUDGET_SEC", "600"))  # 10 minutes per job
        self.max_concurrent = int(os.environ.get("SCHEDULER_MAX_CONCURRENCY", "2"))  # 2 concurrent retailers
        
        # Set up logging
        self.setup_logging()
        
    def setup_logging(self):
        """Set up comprehensive logging for the daemon"""
        # Logs under SCRAPER_HOME/logs
        log_dir = self.root_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # Main scheduler log
        log_file = log_dir / "scheduler_daemon.log"
        
        # Detailed execution flow log
        execution_log_file = log_dir / "scheduler_execution_flow.log"
        
        # Configure main logger
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        
        # Create detailed execution flow logger
        self.execution_logger = logging.getLogger('execution_flow')
        self.execution_logger.setLevel(logging.DEBUG)
        
        # Create file handler for execution flow
        execution_handler = logging.FileHandler(execution_log_file)
        execution_handler.setLevel(logging.DEBUG)
        
        # Create detailed formatter for execution flow
        execution_formatter = logging.Formatter(
            '%(asctime)s - EXEC_FLOW - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        )
        execution_handler.setFormatter(execution_formatter)
        
        self.execution_logger.addHandler(execution_handler)
        self.execution_logger.propagate = False  # Don't propagate to root logger
        
    def find_all_client_schedules(self):
        """Find all client schedule configuration files from schedules/ (preferred) or output/ (legacy)"""
        self.execution_logger.debug("FUNCTION_ENTRY: find_all_client_schedules()")
        schedule_files = []
        
        # NEW: Check schedules/ directory first (preferred location)
        schedules_dir = self.root_dir / "schedules"
        if schedules_dir.exists():
            pattern = str(schedules_dir / "*.json")
            self.execution_logger.debug(f"GLOB_PATTERN_NEW: {pattern}")
            new_files = [f for f in glob.glob(pattern) if not f.endswith("master_schedule.json")]
            schedule_files.extend(new_files)
            self.execution_logger.debug(f"FOUND_NEW_SCHEDULE_FILES: {len(new_files)} files")
        
        # LEGACY: Fall back to output/<retailer>/<client>/schedule_config.json
        if self.output_dir.exists():
            pattern = str(self.output_dir / "*" / "*" / "schedule_config.json")
            self.execution_logger.debug(f"GLOB_PATTERN_LEGACY: {pattern}")
            legacy_files = glob.glob(pattern)
            schedule_files.extend(legacy_files)
            self.execution_logger.debug(f"FOUND_LEGACY_SCHEDULE_FILES: {len(legacy_files)} files")
        
        self.execution_logger.debug(f"TOTAL_SCHEDULE_FILES: {len(schedule_files)} files - {schedule_files}")
        return schedule_files
        
    def load_schedule_config(self, config_file):
        """Load a schedule configuration from file"""
        self.execution_logger.debug(f"FUNCTION_ENTRY: load_schedule_config({config_file})")
        try:
            self.execution_logger.debug(f"FILE_READ_ATTEMPT: {config_file}")
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.execution_logger.debug(f"CONFIG_LOADED_SUCCESS: {config}")
            return config
        except (json.JSONDecodeError, IOError) as e:
            self.execution_logger.error(f"CONFIG_LOAD_FAILED: {config_file} - {e}")
            self.logger.error(f"Failed to load schedule config {config_file}: {e}")
            return None
            
    def load_client_keywords(self, client_dir):
        """Load keywords for a client from their history"""
        # History under SCRAPER_HOME/output
        history_file = self.output_dir / "client_history.json"
        
        if not history_file.exists():
            return []
            
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                
            # Extract client name from directory path
            client_name = Path(client_dir).name
            
            # Try to find matching client in history
            for client, keywords in history.items():
                # Create sanitized folder name to match
                sanitized = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client)
                if sanitized == client_name:
                    return keywords
                    
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Failed to load client history: {e}")
            
        return []
        
    # Legacy is_scheduled_time() removed - now using _load_schedule_config() + _now_local() in monitor loop
        
    def create_run_key(self, client_name, schedule_time):
        """Create a unique key for tracking run times"""
        now = datetime.now()
        return f"{client_name}_{now.strftime('%Y-%m-%d_%H:%M')}"
        
    def run_scraper_for_client(self, retailer: str, client_name: str, client_dir: str, keywords):
        """Run the scraper for a specific client with retailer-aware script dispatch"""
        self.execution_logger.debug(f"FUNCTION_ENTRY: run_scraper_for_client(retailer={retailer}, client={client_name}, dir={client_dir}, keywords={len(keywords)})")
        
        try:
            # Get retailer script
            script = self.SCRIPT_MAP.get(retailer)
            if not script:
                self.logger.error(f"[{retailer}] Unsupported retailer for client {client_name}")
                self.execution_logger.error(f"UNSUPPORTED_RETAILER: {retailer}")
                return
            
            script_path = self.code_dir / script
            if not script_path.exists():
                self.logger.error(f"[{retailer}] Scraper script not found: {script_path}")
                self.execution_logger.error(f"SCRIPT_NOT_FOUND: {script_path}")
                return
            
            self.logger.info(f"Starting scheduled scrape for client: {client_name} (retailer: {retailer}, keywords: {len(keywords)})")
            self.execution_logger.info(f"SCRAPE_START: Retailer={retailer}, Client={client_name}, Keywords={len(keywords)}")
            
            # Create keywords file for this run
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            keywords_file = Path(client_dir) / f"scheduled_keywords_{timestamp}.txt"
            self.execution_logger.debug(f"KEYWORDS_FILE_CREATE: {keywords_file}")
            
            with open(keywords_file, "w", encoding="utf-8") as f:
                f.write("\n".join(keywords))
            self.execution_logger.debug(f"KEYWORDS_FILE_WRITTEN: {len(keywords)} keywords")
                
            # Run scraper for each keyword with job budget enforcement
            success_count = 0
            job_start = time.time()
            
            for i, keyword in enumerate(keywords, 1):
                # Check job budget
                if time.time() - job_start > self.job_budget:
                    self.logger.warning(f"[{retailer}] Job budget ({self.job_budget}s) exceeded for {client_name}; stopping early")
                    self.execution_logger.warning(f"JOB_BUDGET_EXCEEDED: Retailer={retailer}, Client={client_name} after {i-1}/{len(keywords)} keywords")
                    break
                
                self.logger.info(f"[{retailer}] START keyword '{keyword}' for {client_name}")
                self.execution_logger.info(f"KEYWORD_SCRAPE_START: Retailer={retailer}, Client={client_name}, Keyword=[{i}/{len(keywords)}] '{keyword}'")
                
                # Build command based on retailer
                if retailer == "kroger":
                    cmd = [
                        sys.executable,
                        str(script_path),
                        "--search",
                        keyword,
                        "--output-dir",
                        str(client_dir)
                    ]
                else:
                    # Instacart, Walmart, Amazon use positional keyword arg
                    cmd = [
                        sys.executable,
                        str(script_path),
                        keyword,
                        "--output-dir",
                        str(client_dir)
                    ]
                
                self.execution_logger.debug(f"SUBPROCESS_CMD: {' '.join(cmd)}")
                
                try:
                    self.execution_logger.debug(f"SUBPROCESS_START: {script} for '{keyword}'")
                    
                    # Launch in its own process group so we can kill all children on timeout
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        start_new_session=True  # puts child in a new process group
                    )
                    
                    stdout, stderr = proc.communicate(timeout=self.keyword_timeout)
                    rc = proc.returncode
                    
                    self.execution_logger.debug(f"SUBPROCESS_RETURN_CODE: {rc}")
                    if stdout:
                        self.execution_logger.debug(f"SUBPROCESS_STDOUT: {stdout[:500]}...")
                    if stderr:
                        self.execution_logger.debug(f"SUBPROCESS_STDERR: {stderr[:500]}...")
                    
                    if rc == 0:
                        success_count += 1
                        self.logger.info(f"[{retailer}] SUCCESS keyword '{keyword}' for {client_name}")
                        self.execution_logger.info(f"KEYWORD_SCRAPE_SUCCESS: Retailer={retailer}, Client={client_name}, Keyword='{keyword}'")
                    else:
                        self.logger.error(f"[{retailer}] FAIL keyword '{keyword}' for {client_name}: rc={rc}")
                        self.execution_logger.error(f"KEYWORD_SCRAPE_FAILED: Retailer={retailer}, Client={client_name}, Keyword='{keyword}', rc={rc}")
                        
                except subprocess.TimeoutExpired:
                    # Kill the whole process group (the scraper and any Chromium children)
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        pass
                    try:
                        stdout, stderr = proc.communicate()
                    except:
                        pass
                    self.logger.error(f"[{retailer}] TIMEOUT keyword '{keyword}' for {client_name} after {self.keyword_timeout}s")
                    self.execution_logger.error(f"KEYWORD_SCRAPE_TIMEOUT: Retailer={retailer}, Client={client_name}, Keyword='{keyword}', Timeout={self.keyword_timeout}s")
                except Exception as e:
                    self.logger.error(f"[{retailer}] ERROR keyword '{keyword}' for {client_name}: {e}")
                    self.execution_logger.error(f"KEYWORD_SCRAPE_EXCEPTION: Retailer={retailer}, Client={client_name}, Keyword='{keyword}', Error={e}")
                    
            # Skip post-processing if no successful scrapes
            if success_count == 0:
                self.logger.info(f"[{retailer}] Skipping HTML post-processing for {client_name} (0 successes)")
                self.execution_logger.info(f"HTML_PROCESSING_SKIPPED: Retailer={retailer}, Client={client_name}")
                return
            
            # Process only newest HTMLs missing images (per-run, no mixing)
            self.execution_logger.info(f"HTML_PROCESSING_START: {client_dir} (latest-missing)")
            try:
                process_cmd = [
                    sys.executable,
                    str(self.code_dir / "process_saved_html.py"),
                    "--input-dir",
                    str(client_dir),
                    "--output-dir",
                    str(client_dir),
                    "--latest-missing",
                    "--missing-gap-minutes",
                    "2",
                    "--force-images",  # Always force image extraction regardless of existing files
                ]
                
                self.execution_logger.debug(f"HTML_PROCESS_CMD: {' '.join(process_cmd)}")
                self.execution_logger.debug(f"SUBPROCESS_START: process_saved_html.py")
                
                result = subprocess.run(
                    process_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout for processing
                )
                
                self.execution_logger.debug(f"HTML_PROCESS_RETURN_CODE: {result.returncode}")
                if result.stdout:
                    self.execution_logger.debug(f"HTML_PROCESS_STDOUT: {result.stdout[:500]}...")
                if result.stderr:
                    self.execution_logger.debug(f"HTML_PROCESS_STDERR: {result.stderr[:500]}...")
                
                if result.returncode == 0:
                    self.logger.info(f"[{retailer}] Successfully processed HTML files for {client_name}")
                    self.execution_logger.info(f"HTML_PROCESSING_SUCCESS: Retailer={retailer}, Client={client_name}")
                else:
                    self.logger.error(f"[{retailer}] Failed to process HTML files for {client_name}: {result.stderr}")
                    self.execution_logger.error(f"HTML_PROCESSING_FAILED: Retailer={retailer}, Client={client_name}, Error={result.stderr}")
                    
            except Exception as e:
                self.logger.error(f"[{retailer}] Error processing HTML files for {client_name}: {e}")
                self.execution_logger.error(f"HTML_PROCESSING_EXCEPTION: Retailer={retailer}, Client={client_name}, Error={e}")
                
            self.logger.info(f"[{retailer}] Completed scheduled scrape for {client_name}: {success_count}/{len(keywords)} keywords successful")
            self.execution_logger.info(f"SCRAPE_COMPLETE: Retailer={retailer}, Client={client_name}, Success={success_count}/{len(keywords)}")
            
        except Exception as e:
            self.logger.error(f"[{retailer}] Error in scheduled scrape for {client_name}: {e}")
            self.execution_logger.error(f"SCRAPE_EXCEPTION: Retailer={retailer}, Client={client_name}, Error={e}")
    
    def _start_job_async(self, schedule, keywords):
        """Launch a scrape job asynchronously with concurrency and lock management"""
        # Cap concurrency across retailers
        active = sum(1 for t in self.inflight.values() if t.is_alive())
        if active >= self.max_concurrent:
            self.logger.info(f"Concurrency cap reached ({active}/{self.max_concurrent}); delaying {schedule['client']}")
            return False

        # Per-client lock (same lock file)
        ldir = _running_lock_dir(schedule)
        os.makedirs(ldir, exist_ok=True)
        lock = os.path.join(ldir, "run.lock")
        if os.path.exists(lock):
            age = time.time() - os.path.getmtime(lock)
            if age <= 1800:  # 30 minutes
                self.logger.info(f"⏭️  Skipping {schedule['client']} (active lock): {lock}")
                return False
            try:
                os.remove(lock)
            except Exception:
                pass
        
        # Acquire lock
        with open(lock, "w") as f:
            f.write(f"pid={os.getpid()} ts={datetime.now().isoformat()}\n")

        retailer = schedule["retailer"]
        client_name = schedule["client"]
        client_dir = schedule["log_dir"]
        
        # Enforce max runs limit
        max_runs = int(schedule.get("runs", 0) or 0)
        if max_runs > 0 and len(keywords) > max_runs:
            keywords = keywords[:max_runs]
            self.execution_logger.info(f"KEYWORDS_TRUNCATED: Retailer={retailer}, Client={client_name} to {max_runs}")

        def worker():
            try:
                self.run_scraper_for_client(retailer, client_name, client_dir, keywords)
            finally:
                try:
                    os.remove(lock)
                except:
                    pass

        run_key = f"{client_name}_{datetime.now().strftime('%Y-%m-%d_%H:%M')}"
        t = threading.Thread(target=worker, name=f"run-{retailer}-{client_name}", daemon=True)
        t.start()
        self.inflight[run_key] = t
        self.logger.info(f"Started async job for {client_name} (retailer: {retailer}, thread={t.name})")
        return True
            
    def monitor_schedules(self):
        """Main monitoring loop - uses new helper functions for robust time matching"""
        self.logger.info("Scheduler daemon started - monitoring client schedules")
        self.execution_logger.info("DAEMON_START: Monitoring loop initiated")
        
        while self.running:
            try:
                # 0) Clean up finished threads
                finished = [k for k, t in list(self.inflight.items()) if not t.is_alive()]
                for k in finished:
                    self.inflight.pop(k, None)
                if finished:
                    self.execution_logger.debug(f"THREAD_CLEANUP: removed {len(finished)} finished job(s)")
                
                # 1) Load all schedules using shared library (new schedules/ + legacy output/)
                schedules = scan_schedules(self.root_dir)
                
                # 2) Get current time
                now = datetime.now()
                today = now.strftime("%A").lower()  # monday, tuesday, etc.
                hhmm = now.strftime("%H:%M")  # 24-hour format
                
                self.logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] tick: {today} {hhmm} | {len(schedules)} schedule(s)")
                self.execution_logger.debug(f"MONITOR_TICK: day={today}, time={hhmm}, schedules={len(schedules)}")
                
                # 3) Check each schedule for due jobs
                for s in schedules:
                    # Respect 'enabled' flag
                    if not s.enabled:
                        continue
                    
                    # Use timezone if specified
                    if s.tz:
                        check_time = now_in_tz(s.tz)
                        check_today = check_time.strftime("%A").lower()
                        check_hhmm = check_time.strftime("%H:%M")
                    else:
                        check_today = today
                        check_hhmm = hhmm
                    
                    # Check if today and time match
                    if check_today in s.days and check_hhmm in s.times:
                        client_name = s.client
                        retailer = s.retailer
                        self.logger.info(f"→ DUE: [{retailer}] {client_name} @ {check_hhmm} ({s.source_path})")
                        self.execution_logger.info(f"SCHEDULE_MATCH: [{retailer}] {client_name} @ {check_hhmm}")
                        
                        # Check for keywords
                        keywords = s.keywords
                        if not keywords:
                            # Fallback to client_history.json
                            keywords = self.load_client_keywords(s.output_dir)
                            self.execution_logger.debug(f"KEYWORDS_SOURCE: client_history.json ({len(keywords)})")
                        else:
                            self.execution_logger.debug(f"KEYWORDS_SOURCE: schedule ({len(keywords)})")
                        
                        if not keywords:
                            self.logger.warning(f"[{retailer}] No keywords found for {client_name}")
                            self.execution_logger.warning(f"NO_KEYWORDS_FOUND: [{retailer}] {client_name}")
                            continue
                        
                        # Create run key for duplicate prevention
                        run_key = f"{retailer}_{client_name}_{now.strftime('%Y-%m-%d_%H:%M')}"
                        if run_key in self.last_run_times:
                            self.execution_logger.debug(f"DUPLICATE_RUN_PREVENTED: {run_key}")
                            continue
                        
                        self.last_run_times[run_key] = now
                        
                        # Convert Schedule object to dict for _start_job_async
                        schedule_dict = {
                            "retailer": retailer,
                            "client": client_name,
                            "log_dir": s.output_dir,
                            "keywords": keywords
                        }
                        
                        # Launch async job with concurrency control
                        started = self._start_job_async(schedule_dict, keywords)
                        if started:
                            self.execution_logger.info(f"SCRAPE_LAUNCHED_ASYNC: [{retailer}] {client_name}")
                        else:
                            self.execution_logger.info(f"SCRAPE_NOT_STARTED: [{retailer}] {client_name} (lock or concurrency)")
                
                # 5) Clean up old run time entries (keep only last 2 hours)
                cutoff_time = now - timedelta(hours=2)
                old_count = len(self.last_run_times)
                self.last_run_times = {
                    k: v for k, v in self.last_run_times.items() 
                    if v >= cutoff_time
                }
                new_count = len(self.last_run_times)
                
                if old_count != new_count:
                    self.execution_logger.debug(f"CLEANUP_RUN_TIMES: Removed {old_count - new_count} old entries")
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                self.execution_logger.error(f"MONITOR_LOOP_EXCEPTION: {e}")
                
            # 6) Sleep until next minute boundary (aligned)
            self.execution_logger.debug("MONITOR_SLEEP: Waiting until next minute boundary")
            _sleep_until_next_minute()
            
    def start(self):
        """Start the scheduler daemon"""
        self.running = True
        self.monitor_schedules()
        
    def stop(self):
        """Stop the scheduler daemon"""
        self.running = False
        self.logger.info("Scheduler daemon stopped")


def main():
    """Main entry point - single-instance enforcement handled by scheduler_entry.py"""
    daemon = SchedulerDaemon()
    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.logger.info("Received interrupt signal")
        daemon.stop()
    except Exception as e:
        daemon.logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
