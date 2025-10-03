#!/usr/bin/env python3
"""
Auto-generate retailer taxonomy table in README.md from code.
Single source of truth: utils/path_taxonomy.py

Usage:
    python scripts/docs/update_docs.py          # Update README
    python scripts/docs/update_docs.py --check  # Check if stale (for CI)
"""
import os
import sys
import re
from pathlib import Path

# Adjust import path so we can import utils.path_taxonomy in any working dir
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Import the taxonomy from code (single source of truth)
try:
    from utils.path_taxonomy import TAXONOMY as RETAILER_TAXONOMY
except Exception as e:
    print(f"[update_docs] Failed to import utils.path_taxonomy: {e}")
    sys.exit(2)

README = REPO_ROOT / "README.md"
START = "<!-- TAXONOMY_START -->"
END = "<!-- TAXONOMY_END -->"


def render_taxonomy_md() -> str:
    """Render the taxonomy table as Markdown."""
    rows = []
    for retailer in sorted(RETAILER_TAXONOMY.keys()):
        subs = sorted(RETAILER_TAXONOMY[retailer])
        subs_md = ", ".join(f"`{s}`" for s in subs)
        rows.append(f"| **{retailer.capitalize()}** | {subs_md} |")
    
    table = [
        "| Retailer | Allowed subfolders |",
        "|----------|-------------------|",
        *rows,
    ]
    return "\n".join(table) + "\n"


def replace_block(text: str, start: str, end: str, payload_md: str) -> str:
    """Replace content between start and end markers."""
    pattern = re.compile(
        re.escape(start) + r"(.*?)" + re.escape(end),
        flags=re.DOTALL,
    )
    replacement = f"{start}\n{payload_md}{end}"
    
    if pattern.search(text):
        return pattern.sub(replacement, text)
    
    # If markers missing, append a new block at the end
    return text.strip() + "\n\n" + replacement + "\n"


def main():
    if not README.exists():
        print(f"[update_docs] README not found at {README}")
        sys.exit(1)
    
    readme = README.read_text(encoding="utf-8")
    payload = render_taxonomy_md()
    new_text = replace_block(readme, START, END, payload)
    
    # --check only mode for CI: python scripts/docs/update_docs.py --check
    if "--check" in sys.argv:
        if new_text != readme:
            print("[update_docs] README taxonomy is stale. Run: python scripts/docs/update_docs.py")
            sys.exit(1)
        print("[update_docs] ✅ README taxonomy is up to date.")
        return
    
    if new_text != readme:
        README.write_text(new_text, encoding="utf-8")
        print("[update_docs] ✅ README taxonomy updated.")
    else:
        print("[update_docs] ℹ️  No changes needed.")


if __name__ == "__main__":
    main()
