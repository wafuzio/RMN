#!/usr/bin/env python3
"""
Filter schedules to only enable specific clients and disable Kroger across all clients.
"""
import json
import sys
from pathlib import Path

# Clients to keep enabled (case-insensitive matching)
ENABLED_CLIENTS = {"proactiv", "garan", "community coffee", "milkpep"}

# Retailers to disable globally
DISABLED_RETAILERS = ["kroger"]

def filter_schedules(schedules_dir: Path, dry_run: bool = False):
    """Filter schedule files based on client and retailer rules."""
    
    schedule_files = list(schedules_dir.glob("*.json"))
    # Exclude master_schedule.json and frontpage_capture.json
    schedule_files = [f for f in schedule_files if f.name not in ["master_schedule.json", "frontpage_capture.json"]]
    
    disabled_count = 0
    enabled_count = 0
    
    for schedule_file in schedule_files:
        try:
            with open(schedule_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            retailer = config.get("retailer", "").strip().lower()
            client = config.get("client", "").strip()
            current_enabled = config.get("enabled", True)
            
            # Determine if should be enabled
            should_enable = False
            
            # Disable if Kroger
            if retailer in DISABLED_RETAILERS:
                should_enable = False
                reason = f"Kroger disabled globally"
            # Enable if in allowed clients list (case-insensitive)
            elif client.lower() in ENABLED_CLIENTS:
                should_enable = True
                reason = f"Client '{client}' is in enabled list"
            else:
                should_enable = False
                reason = f"Client '{client}' not in enabled list"
            
            # Update if needed
            if current_enabled != should_enable:
                config["enabled"] = should_enable
                
                if not dry_run:
                    with open(schedule_file, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=2)
                
                action = "ENABLE" if should_enable else "DISABLE"
                print(f"{action}: {schedule_file.name} - {reason}")
                
                if should_enable:
                    enabled_count += 1
                else:
                    disabled_count += 1
            else:
                status = "enabled" if current_enabled else "disabled"
                print(f"UNCHANGED: {schedule_file.name} - already {status}")
                
        except Exception as e:
            print(f"ERROR processing {schedule_file.name}: {e}")
    
    print(f"\n{'DRY RUN - ' if dry_run else ''}Summary:")
    print(f"  Enabled: {enabled_count}")
    print(f"  Disabled: {disabled_count}")
    print(f"  Total processed: {len(schedule_files)}")
    
    return enabled_count, disabled_count

if __name__ == "__main__":
    schedules_dir = Path(__file__).resolve().parent.parent / "schedules"
    
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - No files will be modified\n")
    
    print(f"Enabled clients: {', '.join(ENABLED_CLIENTS)}")
    print(f"Disabled retailers: {', '.join(DISABLED_RETAILERS)}\n")
    
    filter_schedules(schedules_dir, dry_run=dry_run)
