#!/usr/bin/env python3
"""
TikTok Shop diagnostic logging system.

Similar to kroger_diagnostics.py, provides step-by-step logging with
screenshots, HTML captures, and structured JSON logs for debugging.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path


class TikTokShopDiagnostics:
    """
    Diagnostic logger for TikTok Shop scraping sessions.
    
    Captures:
    - Step-by-step actions with timestamps
    - Screenshots at each step
    - HTML snapshots
    - Error conditions
    - Final summary report
    """
    
    def __init__(self, output_dir: str, keyword: str):
        """
        Initialize diagnostic logger.
        
        Args:
            output_dir: Base output directory
            keyword: Search keyword for this session
        """
        self.keyword = keyword
        self.start_time = time.time()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create diagnostic output directory
        self.diag_dir = os.path.join(
            output_dir,
            "diagnostics",
            f"tiktokshop_{self.timestamp}"
        )
        os.makedirs(self.diag_dir, exist_ok=True)
        
        # Step log file (JSONL format)
        self.steps_file = os.path.join(self.diag_dir, "steps.jsonl")
        self.steps = []
        
        # Counters
        self.step_num = 0
        self.screenshot_num = 0
        
        print(f"📊 Diagnostics enabled: {self.diag_dir}")
    
    def log(self, event_type: str, **kwargs):
        """
        Log a diagnostic event.
        
        Args:
            event_type: Type of event (e.g., 'navigation', 'click', 'error')
            **kwargs: Additional event data
        """
        self.step_num += 1
        
        entry = {
            "step": self.step_num,
            "timestamp": datetime.now().isoformat(),
            "elapsed_sec": round(time.time() - self.start_time, 2),
            "event": event_type,
            **kwargs
        }
        
        self.steps.append(entry)
        
        # Write to JSONL file immediately
        with open(self.steps_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        
        # Print to console
        elapsed = entry["elapsed_sec"]
        print(f"  [{elapsed:6.2f}s] {event_type}: {kwargs}")
    
    async def screenshot(self, page, name: str):
        """
        Capture screenshot with diagnostic naming.
        
        Args:
            page: Playwright page object
            name: Descriptive name for screenshot
        """
        self.screenshot_num += 1
        filename = f"step{self.step_num:02d}_{name}.png"
        filepath = os.path.join(self.diag_dir, filename)
        
        try:
            await page.screenshot(path=filepath, full_page=False)
            self.log("screenshot", file=filename, description=name)
            return filepath
        except Exception as e:
            self.log("screenshot_error", error=str(e), description=name)
            return None
    
    async def save_html(self, page, name: str):
        """
        Save HTML snapshot with diagnostic naming.
        
        Args:
            page: Playwright page object
            name: Descriptive name for HTML file
        """
        filename = f"step{self.step_num:02d}_{name}.html"
        filepath = os.path.join(self.diag_dir, filename)
        
        try:
            content = await page.content()
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            self.log("html_snapshot", file=filename, description=name)
            return filepath
        except Exception as e:
            self.log("html_error", error=str(e), description=name)
            return None
    
    def finalize(self, success: bool, **kwargs):
        """
        Generate final diagnostic report.
        
        Args:
            success: Whether scrape succeeded
            **kwargs: Additional summary data
        """
        duration = time.time() - self.start_time
        
        report = {
            "keyword": self.keyword,
            "timestamp": self.timestamp,
            "duration_sec": round(duration, 2),
            "success": success,
            "total_steps": self.step_num,
            "total_screenshots": self.screenshot_num,
            **kwargs
        }
        
        # Save JSON report
        report_file = os.path.join(self.diag_dir, "report.json")
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Save markdown report
        md_file = os.path.join(self.diag_dir, "report.md")
        with open(md_file, 'w') as f:
            f.write(f"# TikTok Shop Diagnostic Report\n\n")
            f.write(f"**Keyword**: {self.keyword}\n")
            f.write(f"**Timestamp**: {self.timestamp}\n")
            f.write(f"**Duration**: {duration:.2f}s\n")
            f.write(f"**Success**: {'✅' if success else '❌'}\n")
            f.write(f"**Total Steps**: {self.step_num}\n")
            f.write(f"**Screenshots**: {self.screenshot_num}\n\n")
            
            if kwargs:
                f.write("## Summary\n\n")
                for key, value in kwargs.items():
                    f.write(f"- **{key}**: {value}\n")
                f.write("\n")
            
            f.write("## Steps\n\n")
            for step in self.steps:
                elapsed = step.get('elapsed_sec', 0)
                event = step.get('event', 'unknown')
                f.write(f"{step['step']}. [{elapsed:6.2f}s] **{event}**")
                
                # Add relevant details
                details = {k: v for k, v in step.items() 
                          if k not in ['step', 'timestamp', 'elapsed_sec', 'event']}
                if details:
                    f.write(f" - {details}")
                f.write("\n")
        
        print(f"📊 Diagnostic report saved: {self.diag_dir}")
        print(f"   - steps.jsonl: {self.step_num} events")
        print(f"   - report.json: Summary")
        print(f"   - report.md: Human-readable report")
        print(f"   - {self.screenshot_num} screenshots")
