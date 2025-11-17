# core/paths.py
from __future__ import annotations
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.path_taxonomy import allowed_subdirs

def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def logs_dir_for(base: str, retailer: str) -> str:
    d = os.path.join(base, "logs", retailer)
    ensure_dir(d); ensure_dir(os.path.join(d, "locks"))
    return d

def output_dir_for(base: str, retailer: str, client: str) -> str:
    """
    Create output directory with retailer-specific folder taxonomy.
    Only creates folders that are allowed for the specific retailer.
    """
    d = os.path.join(base, "output", retailer, client)
    ensure_dir(d)
    
    # Create only the folders allowed for this retailer
    for leaf in allowed_subdirs(retailer):
        ensure_dir(os.path.join(d, leaf))
    
    return d
