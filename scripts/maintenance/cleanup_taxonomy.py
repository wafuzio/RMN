#!/usr/bin/env python3
"""
Clean up disallowed folders from retailer output directories.
Removes folders that don't belong to a retailer's taxonomy.
"""
import sys
import shutil
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.path_taxonomy import allowed_subdirs


def cleanup(root: Path, retailer: str):
    """Remove folders that aren't allowed for the given retailer."""
    if not root.exists():
        print(f"[cleanup] Directory doesn't exist: {root}")
        return
    
    allowed = allowed_subdirs(retailer)
    removed_count = 0
    
    for sub in root.iterdir():
        if sub.is_dir() and sub.name not in allowed:
            print(f"[cleanup] Removing disallowed folder: {sub}")
            shutil.rmtree(sub, ignore_errors=True)
            removed_count += 1
    
    if removed_count == 0:
        print(f"[cleanup] No disallowed folders found in {root}")
    else:
        print(f"[cleanup] Removed {removed_count} disallowed folder(s)")


def cleanup_all_clients(retailer: str, base_dir: Path = None):
    """Clean up all client directories for a retailer."""
    if base_dir is None:
        base_dir = project_root
    
    output_dir = base_dir / "output" / retailer
    
    if not output_dir.exists():
        print(f"[cleanup] No output directory for {retailer}")
        return
    
    print(f"[cleanup] Cleaning up {retailer} directories...")
    print(f"[cleanup] Allowed folders: {sorted(allowed_subdirs(retailer))}")
    
    for client_dir in output_dir.iterdir():
        if client_dir.is_dir():
            print(f"\n[cleanup] Processing: {client_dir.name}")
            cleanup(client_dir, retailer)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/maintenance/cleanup_taxonomy.py <retailer>")
        print("  python scripts/maintenance/cleanup_taxonomy.py <path> <retailer>")
        print("\nExamples:")
        print("  python scripts/maintenance/cleanup_taxonomy.py instacart")
        print("  python scripts/maintenance/cleanup_taxonomy.py ~/RMN/output/instacart/cheese_dip instacart")
        sys.exit(2)
    
    if len(sys.argv) == 2:
        # Clean all clients for a retailer
        cleanup_all_clients(sys.argv[1].lower())
    else:
        # Clean specific directory
        cleanup(Path(sys.argv[1]).expanduser(), sys.argv[2].lower())
