#!/usr/bin/env python3
"""
Quick debug log viewer for Walmart scraper runs.
Shows the most recent run's debug logs in a readable format.
"""
import json
import os
import glob
from datetime import datetime

def find_latest_run():
    """Find the most recent run directory."""
    pattern = "/Users/dan.maguire/Documents/Amazon_Scrape/output/walmart/wmt/runs/*/walmart_*_steps.jsonl"
    files = glob.glob(pattern)
    if not files:
        print("❌ No debug logs found")
        return None
    
    # Sort by modification time
    latest = max(files, key=os.path.getmtime)
    return latest

def view_debug_log(log_path):
    """View debug log in readable format."""
    print(f"\n{'='*80}")
    print(f"DEBUG LOG: {log_path}")
    print(f"{'='*80}\n")
    
    run_dir = os.path.dirname(log_path)
    
    # Show all files in run directory
    print("📁 FILES IN RUN DIRECTORY:")
    for f in os.listdir(run_dir):
        fpath = os.path.join(run_dir, f)
        size = os.path.getsize(fpath)
        print(f"   - {f} ({size:,} bytes)")
    print()
    
    # Parse and display log entries
    print("📋 DEBUG LOG ENTRIES:")
    print("-" * 80)
    
    with open(log_path, 'r') as f:
        for i, line in enumerate(f, 1):
            try:
                entry = json.loads(line)
                
                # Format timestamp
                ts = entry.get('ts', 0)
                dt = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                
                # Format elapsed time
                elapsed = entry.get('t', 0)
                
                # Get event type
                event = entry.get('event', 'unknown')
                
                # Color code by event type
                if event == 'step_error' or event == 'outer_error':
                    prefix = "❌"
                elif event == 'milestone' and entry.get('ok'):
                    prefix = "✅"
                elif event == 'px_trip' or 'px' in event:
                    prefix = "🔴"
                elif event == 'step_start':
                    prefix = "▶️ "
                elif event == 'step_end':
                    prefix = "✓"
                else:
                    prefix = "  "
                
                # Build output line
                print(f"{prefix} [{dt}] +{elapsed:6.2f}s | {event:20s}", end="")
                
                # Add relevant details
                if 'error' in entry:
                    print(f" | ERROR: {entry['error']}")
                elif 'name' in entry:
                    print(f" | {entry['name']}", end="")
                    if 'dur' in entry:
                        print(f" ({entry['dur']:.2f}s)", end="")
                    print()
                elif 'msg' in entry:
                    print(f" | {entry['msg']}")
                else:
                    # Show first few keys
                    keys = [k for k in entry.keys() if k not in ['ts', 't', 'event']]
                    if keys:
                        details = {k: entry[k] for k in keys[:3]}
                        print(f" | {details}")
                    else:
                        print()
                        
            except json.JSONDecodeError:
                print(f"⚠️  Line {i}: Invalid JSON")
            except Exception as e:
                print(f"⚠️  Line {i}: Error parsing - {e}")
    
    print("-" * 80)
    print(f"\n✅ Viewed {log_path}\n")

def main():
    latest = find_latest_run()
    if latest:
        view_debug_log(latest)
        
        # Show trace file if exists
        run_dir = os.path.dirname(latest)
        trace_files = glob.glob(os.path.join(run_dir, "*trace.zip"))
        if trace_files:
            print(f"🎯 Playwright trace available: {trace_files[0]}")
            print(f"   View with: playwright show-trace {trace_files[0]}\n")

if __name__ == "__main__":
    main()
