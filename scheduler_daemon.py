#!/usr/bin/env python3
"""
Scheduler Daemon for Grocery Retail Ad Monitor

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
        """Set up logging for the daemon"""
        log_dir = self.project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / "scheduler_daemon.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        
    def find_all_client_schedules(self):
        """Find all client schedule configuration files"""
        schedule_files = []
        
        if not self.output_dir.exists():
            return schedule_files
            
        # Look for schedule_config.json files in all client directories
        pattern = str(self.output_dir / "*" / "schedule_config.json")
        schedule_files = glob.glob(pattern)
        
        return schedule_files
        
    def load_schedule_config(self, config_file):
        """Load a schedule configuration from file"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except (json.JSONDecodeError, IOError) as e:
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
        try:
            self.logger.info(f"Starting scheduled scrape for client: {client_name}")
            
            # Create keywords file for this run
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            keywords_file = Path(client_dir) / f"scheduled_keywords_{timestamp}.txt"
            
            with open(keywords_file, "w", encoding="utf-8") as f:
                f.write("\n".join(keywords))
                
            # Run scraper for each keyword
            success_count = 0
            for keyword in keywords:
                cmd = [
                    sys.executable,
                    str(self.project_root / "kroger_search_and_capture.py"),
                    "--search",
                    keyword,
                    "--output-dir",
                    str(client_dir)
                ]
                
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout per keyword
                    )
                    
                    if result.returncode == 0:
                        success_count += 1
                        self.logger.info(f"Successfully scraped keyword '{keyword}' for {client_name}")
                    else:
                        self.logger.error(f"Failed to scrape keyword '{keyword}' for {client_name}: {result.stderr}")
                        
                except subprocess.TimeoutExpired:
                    self.logger.error(f"Timeout scraping keyword '{keyword}' for {client_name}")
                except Exception as e:
                    self.logger.error(f"Error scraping keyword '{keyword}' for {client_name}: {e}")
                    
            # Process HTML files
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
                
                result = subprocess.run(
                    process_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout for processing
                )
                
                if result.returncode == 0:
                    self.logger.info(f"Successfully processed HTML files for {client_name}")
                else:
                    self.logger.error(f"Failed to process HTML files for {client_name}: {result.stderr}")
                    
            except Exception as e:
                self.logger.error(f"Error processing HTML files for {client_name}: {e}")
                
            self.logger.info(f"Completed scheduled scrape for {client_name}: {success_count}/{len(keywords)} keywords successful")
            
        except Exception as e:
            self.logger.error(f"Error in scheduled scrape for {client_name}: {e}")
            
    def monitor_schedules(self):
        """Main monitoring loop"""
        self.logger.info("Scheduler daemon started - monitoring client schedules")
        
        while self.running:
            try:
                # Find all client schedule files
                schedule_files = self.find_all_client_schedules()
                
                for schedule_file in schedule_files:
                    config = self.load_schedule_config(schedule_file)
                    if not config:
                        continue
                        
                    # Extract client info
                    client_dir = Path(schedule_file).parent
                    client_name = config.get("client", client_dir.name)
                    
                    # Check if it's time to run
                    if self.is_scheduled_time(config):
                        run_key = self.create_run_key(client_name, datetime.now())
                        
                        # Avoid duplicate runs within the same minute
                        if run_key in self.last_run_times:
                            continue
                            
                        self.last_run_times[run_key] = datetime.now()
                        
                        # Load keywords for this client
                        keywords = self.load_client_keywords(client_dir)
                        if not keywords:
                            self.logger.warning(f"No keywords found for client {client_name}")
                            continue
                            
                        # Start scraping in a separate thread
                        thread_key = f"{client_name}_{datetime.now().strftime('%H%M')}"
                        if thread_key not in self.threads or not self.threads[thread_key].is_alive():
                            thread = threading.Thread(
                                target=self.run_scraper_for_client,
                                args=(client_name, client_dir, keywords),
                                daemon=True
                            )
                            thread.start()
                            self.threads[thread_key] = thread
                            
                # Clean up old run time entries (keep only last hour)
                cutoff_time = datetime.now().replace(minute=0, second=0, microsecond=0)
                self.last_run_times = {
                    k: v for k, v in self.last_run_times.items() 
                    if v >= cutoff_time
                }
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                
            # Check every 30 seconds
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
