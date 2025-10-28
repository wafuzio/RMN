#!/usr/bin/env python3
"""
Move legacy Instacart JSON files to backup directory after migration.

This moves legacy files to a backup folder for safekeeping while cleaning
up the runs directory to show only canonical files.

Usage:
    python3 tools/cleanup_instacart_legacy_files.py --dry-run  # Preview
    python3 tools/cleanup_instacart_legacy_files.py            # Move to backup
"""

import json
import sys
import shutil
from pathlib import Path
import argparse
from datetime import datetime

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

INST = project_root / "output" / "instacart"

def cleanup_client(client_dir: Path, dry_run: bool = True):
    """Move legacy JSON files to backup directory"""
    runs_dir = client_dir / "runs"
    if not runs_dir.exists():
        return 0, 0
    
    # Create backup directory
    backup_dir = client_dir / "legacy_backup"
    if not dry_run:
        backup_dir.mkdir(exist_ok=True)
    
    json_files = list(runs_dir.glob("run_results_*.json")) + \
                list(runs_dir.glob("*/run_results_*.json"))
    
    moved = 0
    kept = 0
    
    for json_file in json_files:
        try:
            data = json.loads(json_file.read_text())
            
            # Check if legacy (has results[] instead of ads[])
            is_legacy = "results" in data and "ads" not in data
            
            if is_legacy:
                # Determine destination path
                rel_path = json_file.relative_to(runs_dir)
                dest_path = backup_dir / rel_path
                
                if dry_run:
                    print(f"Would move: {json_file.relative_to(INST)} → legacy_backup/{rel_path}")
                else:
                    # Create parent directory if needed
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    # Move the file
                    shutil.move(str(json_file), str(dest_path))
                    print(f"✅ Moved: {json_file.name} → legacy_backup/")
                moved += 1
            else:
                kept += 1
        except Exception as e:
            print(f"⚠️  Error processing {json_file.name}: {e}")
    
    return moved, kept

def main():
    parser = argparse.ArgumentParser(description="Move legacy Instacart JSON files to backup")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving files")
    args = parser.parse_args()
    
    if not INST.exists():
        print(f"❌ No instacart directory at {INST}")
        return
    
    print("=" * 60)
    print("Instacart Legacy File Backup")
    print("=" * 60)
    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be moved")
    else:
        print("📦 Moving legacy files to backup directories...")
    print()
    
    total_moved = 0
    total_kept = 0
    
    clients = sorted([d for d in INST.iterdir() if d.is_dir()])
    
    for client_dir in clients:
        moved, kept = cleanup_client(client_dir, args.dry_run)
        if moved > 0 or kept > 0:
            print(f"   {client_dir.name}: {moved} legacy moved, {kept} canonical kept")
        total_moved += moved
        total_kept += kept
    
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Legacy files {'would be ' if args.dry_run else ''}moved to backup: {total_moved}")
    print(f"Canonical files kept in runs/: {total_kept}")
    
    if not args.dry_run and total_moved > 0:
        print()
        print(f"✅ Legacy files backed up to: output/instacart/<client>/legacy_backup/")
        print("   You can safely delete these backup directories later if needed.")
    
    if args.dry_run and total_moved > 0:
        print()
        print("Run without --dry-run to move files:")
        print("  python3 tools/cleanup_instacart_legacy_files.py")

if __name__ == "__main__":
    main()
