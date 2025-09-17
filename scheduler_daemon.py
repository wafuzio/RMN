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
from datetime import datetime
from pathlib import Path
import glob

class SchedulerDaemon:
    def __init__(self):
        """Initialize the scheduler daemon"""
        self.project_root = Path(__file__).resolve().parent
        self.output_dir = self.project_root / "output"
        self.running = False
        self.threads = {}
        self.last_run_times = {}  # Track last run times to avoid duplicates
        
        # Set up logging
        self.setup_logging()
        
    def setup_logging(self):
        """Set up comprehensive logging for the daemon"""
        log_dir = self.project_root / "logs"
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
        """Find all client schedule configuration files"""
        self.execution_logger.debug("FUNCTION_ENTRY: find_all_client_schedules()")
        schedule_files = []
        
        if not self.output_dir.exists():
            self.execution_logger.debug(f"OUTPUT_DIR_NOT_EXISTS: {self.output_dir}")
            return schedule_files
            
        # Look for schedule_config.json files in all client directories
        pattern = str(self.output_dir / "*" / "schedule_config.json")
        self.execution_logger.debug(f"GLOB_PATTERN: {pattern}")
        schedule_files = glob.glob(pattern)
        
        self.execution_logger.debug(f"FOUND_SCHEDULE_FILES: {len(schedule_files)} files - {schedule_files}")
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
        history_file = self.project_root / "output" / "client_history.json"
        
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
        
    def is_scheduled_time(self, schedule_config):
        """Check if current time matches any scheduled time"""
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_day = now.strftime("%A")
        
        # Check if today is a scheduled day
        scheduled_days = schedule_config.get("days", [])
        if current_day not in scheduled_days:
            return False
            
        # Check each scheduled time
        times = schedule_config.get("times", [])
        for hour_str, minute_str, ampm in times:
            try:
                hour_12 = int(hour_str)
                minute = int(minute_str)
                
                # Convert to 24-hour format
                scheduled_hour = hour_12
                if ampm == "PM" and hour_12 < 12:
                    scheduled_hour += 12
                elif ampm == "AM" and hour_12 == 12:
                    scheduled_hour = 0
                    
                # Check if it's time to run (within a 1-minute window)
                if current_hour == scheduled_hour and current_minute == minute:
                    return True
                    
            except (ValueError, TypeError):
                continue
                
        return False
        
    def create_run_key(self, client_name, schedule_time):
        """Create a unique key for tracking run times"""
        now = datetime.now()
        return f"{client_name}_{now.strftime('%Y-%m-%d_%H:%M')}"
        
    def run_scraper_for_client(self, client_name, client_dir, keywords):
        """Run the scraper for a specific client"""
        self.execution_logger.debug(f"FUNCTION_ENTRY: run_scraper_for_client(client={client_name}, dir={client_dir}, keywords={keywords})")
        
        try:
            self.logger.info(f"Starting scheduled scrape for client: {client_name}")
            self.execution_logger.info(f"SCRAPE_START: Client={client_name}, Keywords={len(keywords)}")
            
            # Create keywords file for this run
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            keywords_file = Path(client_dir) / f"scheduled_keywords_{timestamp}.txt"
            self.execution_logger.debug(f"KEYWORDS_FILE_CREATE: {keywords_file}")
            
            with open(keywords_file, "w", encoding="utf-8") as f:
                f.write("\n".join(keywords))
            self.execution_logger.debug(f"KEYWORDS_FILE_WRITTEN: {len(keywords)} keywords")
                
            # Run scraper for each keyword
            success_count = 0
            for i, keyword in enumerate(keywords, 1):
                self.execution_logger.info(f"KEYWORD_SCRAPE_START: [{i}/{len(keywords)}] '{keyword}'")
                
                cmd = [
                    sys.executable,
                    str(self.project_root / "kroger_search_and_capture.py"),
                    "--search",
                    keyword,
                    "--output-dir",
                    str(client_dir)
                ]
                
                self.execution_logger.debug(f"SUBPROCESS_CMD: {' '.join(cmd)}")
                
                try:
                    self.execution_logger.debug(f"SUBPROCESS_START: kroger_search_and_capture.py for '{keyword}'")
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout per keyword
                    )
                    
                    self.execution_logger.debug(f"SUBPROCESS_RETURN_CODE: {result.returncode}")
                    if result.stdout:
                        self.execution_logger.debug(f"SUBPROCESS_STDOUT: {result.stdout[:500]}...")
                    if result.stderr:
                        self.execution_logger.debug(f"SUBPROCESS_STDERR: {result.stderr[:500]}...")
                    
                    if result.returncode == 0:
                        success_count += 1
                        self.logger.info(f"Successfully scraped keyword '{keyword}' for {client_name}")
                        self.execution_logger.info(f"KEYWORD_SCRAPE_SUCCESS: '{keyword}'")
                    else:
                        self.logger.error(f"Failed to scrape keyword '{keyword}' for {client_name}: {result.stderr}")
                        self.execution_logger.error(f"KEYWORD_SCRAPE_FAILED: '{keyword}' - {result.stderr}")
                        
                except subprocess.TimeoutExpired:
                    self.logger.error(f"Timeout scraping keyword '{keyword}' for {client_name}")
                    self.execution_logger.error(f"KEYWORD_SCRAPE_TIMEOUT: '{keyword}' after 300s")
                except Exception as e:
                    self.logger.error(f"Error scraping keyword '{keyword}' for {client_name}: {e}")
                    self.execution_logger.error(f"KEYWORD_SCRAPE_EXCEPTION: '{keyword}' - {e}")
                    
            # Process HTML files
            self.execution_logger.info(f"HTML_PROCESSING_START: {client_dir}")
            try:
                process_cmd = [
                    sys.executable,
                    str(self.project_root / "process_saved_html.py"),
                    "--input-dir",
                    str(client_dir),
                    "--output-dir", 
                    str(client_dir),
                    "--all-files"
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
                    self.logger.info(f"Successfully processed HTML files for {client_name}")
                    self.execution_logger.info(f"HTML_PROCESSING_SUCCESS: {client_name}")
                else:
                    self.logger.error(f"Failed to process HTML files for {client_name}: {result.stderr}")
                    self.execution_logger.error(f"HTML_PROCESSING_FAILED: {client_name} - {result.stderr}")
                    
            except Exception as e:
                self.logger.error(f"Error processing HTML files for {client_name}: {e}")
                self.execution_logger.error(f"HTML_PROCESSING_EXCEPTION: {client_name} - {e}")
                
            self.logger.info(f"Completed scheduled scrape for {client_name}: {success_count}/{len(keywords)} keywords successful")
            self.execution_logger.info(f"SCRAPE_COMPLETE: Client={client_name}, Success={success_count}/{len(keywords)}")
            
        except Exception as e:
            self.logger.error(f"Error in scheduled scrape for {client_name}: {e}")
            self.execution_logger.error(f"SCRAPE_EXCEPTION: Client={client_name} - {e}")
            
    def monitor_schedules(self):
        """Main monitoring loop"""
        self.logger.info("Scheduler daemon started - monitoring client schedules")
        self.execution_logger.info("DAEMON_START: Monitoring loop initiated")
        
        while self.running:
            try:
                self.execution_logger.debug("MONITOR_LOOP_ITERATION: Starting new monitoring cycle")
                
                # Find all client schedule files
                schedule_files = self.find_all_client_schedules()
                self.execution_logger.debug(f"MONITOR_SCHEDULES_FOUND: {len(schedule_files)} schedule files")
                
                for schedule_file in schedule_files:
                    self.execution_logger.debug(f"PROCESSING_SCHEDULE_FILE: {schedule_file}")
                    
                    config = self.load_schedule_config(schedule_file)
                    if not config:
                        self.execution_logger.debug(f"SKIPPING_INVALID_CONFIG: {schedule_file}")
                        continue
                        
                    # Extract client info
                    client_dir = Path(schedule_file).parent
                    client_name = config.get("client", client_dir.name)
                    self.execution_logger.debug(f"CLIENT_INFO: name={client_name}, dir={client_dir}")
                    
                    # Check if it's time to run
                    self.execution_logger.debug(f"TIME_CHECK_START: {client_name}")
                    if self.is_scheduled_time(config):
                        self.execution_logger.info(f"SCHEDULE_MATCH: {client_name} is scheduled to run now")
                        
                        run_key = self.create_run_key(client_name, datetime.now())
                        self.execution_logger.debug(f"RUN_KEY_CREATED: {run_key}")
                        
                        # Avoid duplicate runs within the same minute
                        if run_key in self.last_run_times:
                            self.execution_logger.debug(f"DUPLICATE_RUN_PREVENTED: {run_key}")
                            continue
                            
                        self.last_run_times[run_key] = datetime.now()
                        self.execution_logger.debug(f"RUN_KEY_REGISTERED: {run_key}")
                        
                        # Load keywords for this client
                        self.execution_logger.debug(f"LOADING_KEYWORDS: {client_name}")
                        keywords = self.load_client_keywords(client_dir)
                        if not keywords:
                            self.logger.warning(f"No keywords found for client {client_name}")
                            self.execution_logger.warning(f"NO_KEYWORDS_FOUND: {client_name}")
                            continue
                        
                        self.execution_logger.info(f"KEYWORDS_LOADED: {client_name} has {len(keywords)} keywords")
                            
                        # Start scraping in a separate thread
                        thread_key = f"{client_name}_{datetime.now().strftime('%H%M')}"
                        self.execution_logger.debug(f"THREAD_KEY: {thread_key}")
                        
                        if thread_key not in self.threads or not self.threads[thread_key].is_alive():
                            self.execution_logger.info(f"THREAD_START: Creating new thread for {client_name}")
                            
                            thread = threading.Thread(
                                target=self.run_scraper_for_client,
                                args=(client_name, client_dir, keywords),
                                daemon=True
                            )
                            thread.start()
                            self.threads[thread_key] = thread
                            
                            self.execution_logger.info(f"THREAD_CREATED: {thread_key} started successfully")
                        else:
                            self.execution_logger.debug(f"THREAD_ALREADY_RUNNING: {thread_key}")
                    else:
                        self.execution_logger.debug(f"NO_SCHEDULE_MATCH: {client_name} not scheduled now")
                            
                # Clean up old run time entries (keep only last hour)
                cutoff_time = datetime.now().replace(minute=0, second=0, microsecond=0)
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
                
            # Check every 30 seconds
            self.execution_logger.debug("MONITOR_SLEEP: Waiting 30 seconds before next cycle")
            time.sleep(30)
            
    def start(self):
        """Start the scheduler daemon"""
        self.running = True
        self.monitor_schedules()
        
    def stop(self):
        """Stop the scheduler daemon"""
        self.running = False
        self.logger.info("Scheduler daemon stopped")


def main():
    """Main entry point"""
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
