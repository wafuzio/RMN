#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]  # repo root
code_file = ROOT / "walmart_search_and_capture.py"

def scan_code():
    hits = []
    if code_file.exists():
        text = code_file.read_text(errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\bTop_Banner\b", line) or re.search(r"\bBanner\b", line):
                hits.append((i, line.strip()))
    return hits

def scan_outputs():
    folders = {}
    out = ROOT / "output" / "walmart"
    if out.exists():
        for client_dir in out.iterdir():
            if client_dir.is_dir():
                for sub in client_dir.iterdir():
                    if sub.is_dir():
                        folders.setdefault(sub.name, 0)
                        folders[sub.name] += 1
    return folders

if __name__ == "__main__":
    print("Code references in walmart_search_and_capture.py:")
    for i, line in scan_code():
        print(f"  {i:>4}: {line}")

    print("\nOutput folders under output/walmart/*/:")
    for name, count in sorted(scan_outputs().items()):
        print(f"  {name}: {count} client(s)")
