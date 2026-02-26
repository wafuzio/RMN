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
    
    # Retailers that support front page capture
    FRONTPAGE_RETAILERS = ["kroger", "walmart", "target", "amazon", "instacart"]
    
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
        
        # Prefer .venv Python for all subprocesses
        venv_python = self.code_dir / ".venv" / "bin" / "python3"
        self._python_exec = str(venv_python) if venv_python.exists() else sys.executable
        
        # Configurable timeouts and concurrency
        self.keyword_timeout = int(os.environ.get("SCHEDULER_KEYWORD_TIMEOUT", "180"))  # 3 minutes default
        self.job_budget = int(os.environ.get("SCHEDULER_JOB_BUDGET_SEC", "600"))  # 10 minutes per job
        self.max_concurrent = int(os.environ.get("SCHEDULER_MAX_CONCURRENCY", "2"))  # 2 concurrent retailers
        self.due_window_min = int(os.environ.get("SCHEDULER_DUE_WINDOW_MIN", "2"))  # fire if within ±2 min
        self.missing_gap_sec = int(os.environ.get("SCHEDULER_MISSING_GAP_SEC", "120"))  # wait 2 min before extraction
        self.process_timeout = int(os.environ.get("SCHEDULER_PROCESS_TIMEOUT_SEC", "300"))  # 5 min for HTML processing
        
        # Set up logging
        self.setup_logging()
        
        # Log environment snapshot at boot
        self.logger.info("ENV SNAPSHOT: SCRAPER_HOME=%s TZ=%s", os.environ.get("SCRAPER_HOME"), os.environ.get("TZ"))
        for k in ("KROGER_PROFILE_DIR","AMZ_PROFILE_DIR","INSTACART_PROFILE_DIR","INSTACART_STORE","WALMART_PROFILE_DIR"):
            self.logger.info("ENV %s=%s", k, os.environ.get(k))
        
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
    
    def _proc_env(self):
        """Child process environment (pin SCRAPER_HOME and inherit parent env)."""
        env = os.environ.copy()
        env["SCRAPER_HOME"] = str(self.root_dir)
        # Optional but useful: unbuffered IO for logs
        env.setdefault("PYTHONUNBUFFERED", "1")
        return env
    
    def _hhmm_to_min(self, hhmm: str) -> int:
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m
    
    def _within_window(self, now_min: int, slot_hhmm: str, window: int) -> bool:
        """Return True if now_min within ±window minutes of slot_hhmm (wrap-aware)."""
        tgt = self._hhmm_to_min(slot_hhmm)
        diff = abs(now_min - tgt)
        # wrap around midnight (e.g., 1439 vs 0)
        diff = min(diff, 1440 - diff)
        return diff <= window
        
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
            
            # Compute log_dir if not present (for new schedule format)
            if "log_dir" not in config:
                retailer = config.get("retailer", "").strip().lower()
                client = config.get("client", "").strip()
                if retailer and client:
                    # Use output/<retailer>/<client>/runs as the base directory
                    config["log_dir"] = str(self.output_dir / retailer / client / "runs")
                    self.execution_logger.debug(f"COMPUTED_LOG_DIR: {config['log_dir']}")
            
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
    
    def _cleanup_orphaned_chrome(self, profile_pattern: str = None):
        """Kill any orphaned Chrome/Chromium processes using scraper profiles.
        
        Args:
            profile_pattern: Optional pattern to match specific profile (e.g., 'walmart')
        """
        try:
            import subprocess
            # Find Chrome processes using ChromeProfiles
            result = subprocess.run(
                ['pgrep', '-f', 'ChromeProfiles'],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                return  # No matching processes
            
            pids = result.stdout.strip().split('\n')
            if not pids or pids == ['']:
                return
                
            for pid in pids:
                try:
                    # Check if this PID matches our profile pattern
                    proc_info = subprocess.run(
                        ['ps', '-p', pid, '-o', 'args='],
                        capture_output=True, text=True
                    )
                    if 'ChromeProfiles' in proc_info.stdout:
                        if profile_pattern is None or profile_pattern in proc_info.stdout:
                            os.kill(int(pid), signal.SIGTERM)
                            self.logger.debug(f"Cleaned up orphaned Chrome PID {pid}")
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
        except Exception as e:
            self.logger.debug(f"Chrome cleanup failed: {e}")
    
    def run_frontpage_capture(self, retailers: list = None):
        """Run front page screenshot capture for specified retailers.
        
        Args:
            retailers: List of retailer slugs to capture. Defaults to all FRONTPAGE_RETAILERS.
        """
        retailers = retailers or self.FRONTPAGE_RETAILERS
        self.execution_logger.info(f"FRONTPAGE_CAPTURE_START: retailers={retailers}")
        
        script_path = self.code_dir / "scripts" / "screenshot_front_page.py"
        if not script_path.exists():
            self.logger.error(f"Front page capture script not found: {script_path}")
            self.execution_logger.error(f"FRONTPAGE_SCRIPT_NOT_FOUND: {script_path}")
            return
        
        # Run capture for each retailer
        today_str = datetime.now().strftime("D%Y-%m-%d")
        
        for retailer in retailers:
            if retailer not in self.FRONTPAGE_RETAILERS:
                self.logger.warning(f"Skipping unsupported retailer for front page: {retailer}")
                continue
            
            # Check if we already captured this retailer today
            frontpage_dir = self.code_dir / "output" / "screen_capture" / retailer / "front_pages"
            if frontpage_dir.exists():
                existing_today = list(frontpage_dir.glob(f"*__{today_str}_*.png"))
                if existing_today:
                    self.logger.info(f"[frontpage] SKIP: {retailer} already captured today ({existing_today[0].name})")
                    self.execution_logger.info(f"FRONTPAGE_SKIP_ALREADY_CAPTURED: {retailer} file={existing_today[0].name}")
                    continue
            
            self.logger.info(f"[frontpage] Capturing {retailer} front page...")
            self.execution_logger.info(f"FRONTPAGE_CAPTURE_RETAILER: {retailer}")
            
            cmd = [
                self._python_exec,
                str(script_path),
                "--retailer",
                retailer
            ]
            
            try:
                # Run as normal foreground process - Chrome needs real display session
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(self.code_dir),
                    env=self._proc_env(),
                )
                
                stdout, stderr = proc.communicate(timeout=120)  # 2 min timeout per retailer
                rc = proc.returncode
                
                if rc == 0:
                    self.logger.info(f"[frontpage] SUCCESS: {retailer}")
                    self.execution_logger.info(f"FRONTPAGE_CAPTURE_SUCCESS: {retailer}")
                    if stdout:
                        # Log last few lines of stdout for success confirmation
                        last_lines = '\n'.join(stdout.strip().split('\n')[-5:])
                        self.execution_logger.debug(f"FRONTPAGE_STDOUT: {last_lines}")
                else:
                    self.logger.error(f"[frontpage] FAIL: {retailer} rc={rc}")
                    self.execution_logger.error(f"FRONTPAGE_CAPTURE_FAILED: {retailer} rc={rc}")
                    # Log both stdout and stderr for debugging
                    if stdout:
                        self.logger.error(f"[frontpage] STDOUT: {stdout[:1000]}")
                        self.execution_logger.error(f"FRONTPAGE_STDOUT: {stdout[:1000]}")
                    if stderr:
                        self.logger.error(f"[frontpage] STDERR: {stderr[:1000]}")
                        self.execution_logger.error(f"FRONTPAGE_STDERR: {stderr[:1000]}")
                        
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
                self.logger.error(f"[frontpage] TIMEOUT: {retailer}")
                self.execution_logger.error(f"FRONTPAGE_CAPTURE_TIMEOUT: {retailer}")
            except Exception as e:
                self.logger.error(f"[frontpage] ERROR: {retailer} - {e}")
                self.execution_logger.error(f"FRONTPAGE_CAPTURE_EXCEPTION: {retailer} - {e}")
        
        self.execution_logger.info(f"FRONTPAGE_CAPTURE_COMPLETE: {len(retailers)} retailers")
    
    def _frontpage_already_captured_today(self, retailers: list, date_str: str) -> bool:
        """Check if front page screenshots already exist for today.
        
        Returns True if ALL retailers have at least one capture for today,
        meaning we can skip catch-up. Returns False if any retailer is missing.
        
        Args:
            retailers: List of retailer slugs to check
            date_str: Date string in YYYY-MM-DD format
        """
        screen_capture_root = self.root_dir / "output" / "screen_capture"
        
        for retailer in retailers:
            front_pages_dir = screen_capture_root / retailer / "front_pages"
            if not front_pages_dir.exists():
                return False
            
            # Look for files matching today's date pattern
            # Filename format: <retailer>__front_page__D<YYYY-MM-DD>_*.png
            date_pattern = f"{retailer}__front_page__D{date_str}_*.png"
            matches = list(front_pages_dir.glob(date_pattern))
            
            if not matches:
                self.logger.debug(f"[frontpage] No capture found for {retailer} on {date_str}")
                return False
        
        self.logger.info(f"[frontpage] All {len(retailers)} retailers already captured today ({date_str})")
        return True
    
    def _check_frontpage_schedule(self, now: datetime, today: str, hhmm: str):
        """Check if front page capture is due and run it.
        
        Reads schedule from schedules/frontpage_capture.json or uses defaults.
        Includes catch-up logic: if a scheduled time was missed (e.g., system was asleep),
        run on the next wake within the same day.
        """
        # Load front page schedule config
        config_path = self.root_dir / "schedules" / "frontpage_capture.json"
        
        # Default schedule: 8:00 AM daily
        default_config = {
            "enabled": True,
            "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            "times": ["08:00"],
            "retailers": self.FRONTPAGE_RETAILERS
        }
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # Merge with defaults for missing keys
                for key, val in default_config.items():
                    config.setdefault(key, val)
            except Exception as e:
                self.logger.error(f"Failed to load frontpage config: {e}")
                config = default_config
        else:
            config = default_config
        
        if not config.get("enabled", True):
            return
        
        # Check if today matches
        days = set(d.lower() for d in config.get("days", []))
        if today not in days:
            return
        
        now_min = now.hour * 60 + now.minute
        times = config.get("times", [])
        retailers = config.get("retailers", self.FRONTPAGE_RETAILERS)
        
        # Check each scheduled time for today
        for scheduled_time in times:
            scheduled_min = self._hhmm_to_min(scheduled_time)
            
            # Create a daily run key (not minute-specific) to track if we've run today for this slot
            run_key = f"frontpage_{now.strftime('%Y-%m-%d')}_{scheduled_time}"
            
            if run_key in self.last_run_times:
                # Already ran for this scheduled slot today
                continue
            
            # Check if this scheduled time has passed (catch-up) or is within window (on-time)
            is_within_window = self._within_window(now_min, scheduled_time, self.due_window_min)
            is_missed = now_min > scheduled_min + self.due_window_min  # Past the window
            
            if is_within_window:
                # On-time execution
                self.last_run_times[run_key] = now
                self.logger.info(f"→ DUE: [frontpage] Capturing {len(retailers)} retailer front pages @ {hhmm}")
                self.execution_logger.info(f"FRONTPAGE_SCHEDULE_MATCH: {hhmm}, retailers={retailers}")
                self._launch_frontpage_capture(retailers, run_key, scheduled_time, "on-time")
                return  # Only run once per tick
                
            elif is_missed:
                # Catch-up execution - we missed this slot
                # But first check if we already have captures for today (prevents duplicate runs after restart)
                date_str = now.strftime('%Y-%m-%d')
                if self._frontpage_already_captured_today(retailers, date_str):
                    # Mark as done so we don't check again this session
                    self.last_run_times[run_key] = now
                    self.logger.info(f"→ SKIP: [frontpage] Already captured today ({date_str}), skipping catch-up for {scheduled_time}")
                    self.execution_logger.info(f"FRONTPAGE_SKIP_EXISTS: date={date_str}, scheduled={scheduled_time}")
                    continue  # Check next scheduled time
                
                # No existing captures, run catch-up
                self.last_run_times[run_key] = now
                self.logger.info(f"→ CATCH-UP: [frontpage] Missed {scheduled_time}, capturing {len(retailers)} retailer front pages now @ {hhmm}")
                self.execution_logger.info(f"FRONTPAGE_CATCHUP: missed={scheduled_time}, now={hhmm}, retailers={retailers}")
                self._launch_frontpage_capture(retailers, run_key, scheduled_time, "catch-up")
                return  # Only run once per tick
    
    def _launch_frontpage_capture(self, retailers: list, run_key: str, scheduled_time: str, mode: str):
        """Launch front page capture in a background thread.
        
        Args:
            retailers: List of retailer slugs to capture
            run_key: Unique key for tracking this run
            scheduled_time: The originally scheduled time (HH:MM)
            mode: 'on-time' or 'catch-up'
        """
        def worker():
            self.run_frontpage_capture(retailers)
        
        t = threading.Thread(target=worker, name=f"frontpage-{mode}-{scheduled_time}", daemon=False)
        t.start()
        self.inflight[run_key] = t
        
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
                        self._python_exec,
                        str(script_path),
                        "--search",
                        keyword,
                        "--output-dir",
                        str(client_dir)
                    ]
                elif retailer == "amazon":
                    # Amazon uses positional args only (no --output-dir flag)
                    cmd = [
                        self._python_exec,
                        str(script_path),
                        keyword,
                        str(client_dir)
                    ]
                else:
                    # Instacart, Walmart use positional keyword arg + --output-dir flag
                    cmd = [
                        self._python_exec,
                        str(script_path),
                        keyword,
                        "--output-dir",
                        str(client_dir)
                    ]
                
                self.execution_logger.debug(f"SUBPROCESS_CMD: {' '.join(cmd)}")
                
                try:
                    self.execution_logger.debug(f"SUBPROCESS_START: {script} for '{keyword}'")
                    
                    # Run as normal foreground process - Chrome needs real display session
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        cwd=str(self.code_dir),
                        env=self._proc_env(),
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
                    # Kill the process and clean up orphaned Chrome
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        stdout, stderr = proc.communicate()
                    except:
                        pass
                    # Clean up any orphaned Chrome for this retailer
                    self._cleanup_orphaned_chrome(retailer)
                    self.logger.error(f"[{retailer}] TIMEOUT keyword '{keyword}' for {client_name} after {self.keyword_timeout}s")
                    self.execution_logger.error(f"KEYWORD_SCRAPE_TIMEOUT: Retailer={retailer}, Client={client_name}, Keyword='{keyword}', Timeout={self.keyword_timeout}s")
                except Exception as e:
                    self.logger.error(f"[{retailer}] ERROR keyword '{keyword}' for {client_name}: {e}")
                    self.execution_logger.error(f"KEYWORD_SCRAPE_EXCEPTION: Retailer={retailer}, Client={client_name}, Keyword='{keyword}', Error={e}")
                    # Clean up any orphaned Chrome for this retailer
                    self._cleanup_orphaned_chrome(retailer)
                    
            # Skip post-processing if no successful scrapes
            if success_count == 0:
                self.logger.info(f"[{retailer}] Skipping HTML post-processing for {client_name} (0 successes)")
                self.execution_logger.info(f"HTML_PROCESSING_SKIPPED: Retailer={retailer}, Client={client_name}")
                return
            
            # Give the newest runs a moment so '--latest-missing --missing-gap-minutes 2' won't skip them
            if self.missing_gap_sec > 0:
                self.logger.info(f"[{retailer}] Waiting {self.missing_gap_sec}s before HTML processing")
                time.sleep(self.missing_gap_sec)
            
            # Process only newest HTMLs missing images (per-run, no mixing)
            self.execution_logger.info(f"HTML_PROCESSING_START: {client_dir} (latest-missing)")
            try:
                process_cmd = [
                    self._python_exec,
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
                    timeout=self.process_timeout,
                    cwd=str(self.code_dir),
                    env=self._proc_env(),
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
        t = threading.Thread(target=worker, name=f"run-{retailer}-{client_name}", daemon=False)
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
                    else:
                        check_time = now
                    check_today = check_time.strftime("%A").lower()
                    now_min = check_time.hour * 60 + check_time.minute
                    
                    # Check if today and time match (with window)
                    if check_today in s.days and any(self._within_window(now_min, t, self.due_window_min) for t in s.times):
                        client_name = s.client
                        retailer = s.retailer
                        check_hhmm = check_time.strftime("%H:%M")
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
                        
                        # Create run key for duplicate prevention using SCHEDULED time, not current time
                        # This ensures the same scheduled slot produces the same key across the window
                        matching_time = next((t for t in s.times if self._within_window(now_min, t, self.due_window_min)), None)
                        if matching_time:
                            run_key = f"{s.id}_{check_time.strftime('%Y-%m-%d')}_{matching_time}"
                        else:
                            run_key = f"{s.id}_{check_time.strftime('%Y-%m-%d%H:%M')}"
                        
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
                
                # 4) Check for front page capture schedule
                self._check_frontpage_schedule(now, today, hhmm)
                
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
