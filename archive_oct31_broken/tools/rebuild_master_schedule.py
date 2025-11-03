#!/usr/bin/env python3
"""
Rebuild master_schedule.json index and validate all schedules.
CI-friendly tool for schedule management.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schedules.schedules_lib import build_master_index, scan_schedules, detect_conflicts

ROOT = Path(os.environ.get("SCRAPER_HOME") or Path(__file__).resolve().parents[1])


def main():
    """Rebuild master schedule index and validate"""
    print("🔄 Rebuilding master schedule index...")
    print(f"   SCRAPER_HOME: {ROOT}")
    
    # Scan and validate all schedules
    try:
        schedules = scan_schedules(ROOT)
        print(f"\n✅ Found {len(schedules)} valid schedules:")
        
        for s in schedules:
            status = "✓" if s.enabled else "○"
            source = "NEW" if "/schedules/" in s.source_path else "LEGACY"
            print(f"   {status} [{source}] {s.retailer}/{s.client} - {len(s.keywords)} keywords, {len(s.days)} days, {len(s.times)} times")
        
        # Detect conflicts
        print(f"\n🔍 Checking for scheduling conflicts...")
        conflicts = detect_conflicts(schedules, window_minutes=5)
        
        if conflicts:
            print(f"\n⚠️  Found {len(conflicts)} potential conflicts:")
            for s1, s2, reason in conflicts:
                print(f"   • {s1.retailer}/{s1.client} ↔ {s2.retailer}/{s2.client}")
                print(f"     {reason}")
        else:
            print("   ✓ No conflicts detected")
        
        # Build master index
        print(f"\n📝 Building master index...")
        out = build_master_index(ROOT)
        print(f"   ✓ Wrote {out.relative_to(ROOT)}")
        
        print(f"\n✅ Rebuild complete!")
        print(f"   Total schedules: {len(schedules)}")
        print(f"   Enabled: {sum(1 for s in schedules if s.enabled)}")
        print(f"   Disabled: {sum(1 for s in schedules if not s.enabled)}")
        
        if conflicts:
            print(f"\n⚠️  Warning: {len(conflicts)} conflicts detected (see above)")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
