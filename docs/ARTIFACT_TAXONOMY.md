# Artifact Taxonomy and Directory Hygiene

This document defines the folder structure for each retailer and explains how to prevent "directory gore" (cross-retailer folder contamination).

## Problem Statement

**Before taxonomy enforcement:**
```
output/instacart/cheese_dip/
├── TOA/              ❌ Kroger folder in Instacart directory
├── Skyscraper/       ❌ Kroger folder in Instacart directory
├── Carousel/         ❌ Kroger folder in Instacart directory
├── Display_Ads/      ✅ Valid for Instacart
└── runs/             ✅ Valid for all retailers
```

**Root cause:** `core/paths.py` hardcoded Kroger folders for ALL retailers.

## Solution: Retailer-Specific Taxonomy

### Taxonomy Definition (`utils/path_taxonomy.py`)

```python
RETAILER_SUBDIRS = {
    "kroger": ["TOA", "Skyscraper", "Carousel", "Display_Ads", "Main", "runs"],
    "instacart": ["Shoppable_Display_Ads", "Shoppable_Video_Ads", "Display_Ads", "Main", "runs"],
    "amazon": ["TOA", "Skyscraper", "Carousel", "Main", "runs"],
}

def allowed_subdirs(retailer: str) -> list[str]:
    """Returns list of allowed subdirectories for a retailer."""
    return RETAILER_SUBDIRS.get(retailer.lower(), ["Main", "runs"])
```

### Enforced in `core/paths.py`

```python
from utils.path_taxonomy import allowed_subdirs

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
```

## Retailer Taxonomy Reference

### Kroger
```
output/kroger/<client>/
├── TOA/              # Top of Ad (banner ads)
├── Skyscraper/       # Vertical sidebar ads
├── Carousel/         # Product carousels
├── Display_Ads/      # Generic display ads
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

### Instacart
```
output/instacart/<client>/
├── Shoppable_Display_Ads/    # Display ads with product links
├── Shoppable_Video_Ads/      # Video ads with product links
├── Display_Ads/              # Generic display ads
├── Main/                     # Main search results
└── runs/                     # Run artifacts (JSON, HTML)
```

### Amazon
```
output/amazon/<client>/
├── TOA/              # Top of Ad (banner ads)
├── Skyscraper/       # Vertical sidebar ads
├── Carousel/         # Product carousels
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

### Default (New Retailers)
```
output/<retailer>/<client>/
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

## Adding a New Retailer

### 1. Define Taxonomy

Edit `utils/path_taxonomy.py`:
```python
RETAILER_SUBDIRS = {
    # ... existing retailers ...
    "target": ["Display_Ads", "Sponsored_Products", "Main", "runs"],
}
```

### 2. Use in Code

```python
from core.paths import output_dir_for

# This will create only Target-allowed folders
output_dir = output_dir_for(base=".", retailer="target", client="test_client")
```

### 3. Verify

```bash
tree output/target/test_client/
# Should show only: Display_Ads/, Sponsored_Products/, Main/, runs/
```

## Cleanup Script

### Remove Disallowed Folders

`scripts/maintenance/cleanup_taxonomy.py` removes folders that shouldn't exist:

```python
def cleanup_retailer_directories(retailer: str, base_dir: str = "output"):
    """Remove disallowed folders from existing client directories."""
    retailer_dir = os.path.join(base_dir, retailer)
    if not os.path.isdir(retailer_dir):
        return
    
    allowed = set(allowed_subdirs(retailer))
    
    for client_dir in os.listdir(retailer_dir):
        client_path = os.path.join(retailer_dir, client_dir)
        if not os.path.isdir(client_path):
            continue
        
        for item in os.listdir(client_path):
            item_path = os.path.join(client_path, item)
            if os.path.isdir(item_path) and item not in allowed:
                print(f"Removing disallowed folder: {item_path}")
                shutil.rmtree(item_path)
```

### Usage

```bash
# Clean all retailers
python3 scripts/maintenance/cleanup_taxonomy.py

# Clean specific retailer
python3 -c "
from scripts.maintenance.cleanup_taxonomy import cleanup_retailer_directories
cleanup_retailer_directories('instacart')
"
```

## Validation

### Pre-Commit Check

Add to your workflow:
```bash
# Check for invalid folders
python3 -c "
from utils.path_taxonomy import allowed_subdirs
import os

for retailer in ['kroger', 'instacart', 'amazon']:
    retailer_dir = f'output/{retailer}'
    if not os.path.isdir(retailer_dir):
        continue
    
    allowed = set(allowed_subdirs(retailer))
    
    for client in os.listdir(retailer_dir):
        client_path = os.path.join(retailer_dir, client)
        if not os.path.isdir(client_path):
            continue
        
        for folder in os.listdir(client_path):
            folder_path = os.path.join(client_path, folder)
            if os.path.isdir(folder_path) and folder not in allowed:
                print(f'❌ Invalid folder: {folder_path}')
                exit(1)

print('✅ All folders valid')
"
```

### CI Check

Add to GitHub Actions:
```yaml
- name: Validate artifact taxonomy
  run: |
    python3 scripts/maintenance/cleanup_taxonomy.py --dry-run --strict
```

## Common Mistakes

### ❌ Hardcoding Folder Names
```python
# Wrong
os.makedirs(os.path.join(output_dir, "TOA"), exist_ok=True)
os.makedirs(os.path.join(output_dir, "Skyscraper"), exist_ok=True)
```

### ✅ Using Taxonomy System
```python
# Correct
from core.paths import output_dir_for
output_dir = output_dir_for(base, retailer, client)
# Folders already created based on retailer
```

### ❌ Creating Folders Manually
```python
# Wrong
for folder in ["TOA", "Skyscraper", "Carousel"]:
    os.makedirs(os.path.join(output_dir, folder), exist_ok=True)
```

### ✅ Letting paths.py Handle It
```python
# Correct
output_dir = output_dir_for(base, retailer, client)
# Done! Correct folders exist
```

## Migration Guide

### Cleaning Existing Directories

1. **Backup first:**
   ```bash
   tar -czf output_backup_$(date +%Y%m%d).tar.gz output/
   ```

2. **Run cleanup:**
   ```bash
   python3 scripts/maintenance/cleanup_taxonomy.py
   ```

3. **Verify:**
   ```bash
   tree output/ -L 3
   ```

4. **Check for issues:**
   ```bash
   git status output/
   # Should show deleted folders only
   ```

### Updating Existing Code

1. **Find hardcoded folder creation:**
   ```bash
   grep -r "makedirs.*TOA" .
   grep -r "makedirs.*Skyscraper" .
   ```

2. **Replace with:**
   ```python
   from core.paths import output_dir_for
   output_dir = output_dir_for(base, retailer, client)
   ```

3. **Remove manual folder creation**

## Testing

### Unit Test Example

```python
def test_taxonomy_enforcement():
    """Test that only allowed folders are created."""
    import tempfile
    import shutil
    from core.paths import output_dir_for
    from utils.path_taxonomy import allowed_subdirs
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create output directory for Instacart
        output_dir = output_dir_for(tmpdir, "instacart", "test_client")
        
        # Check created folders
        created = set(os.listdir(output_dir))
        allowed = set(allowed_subdirs("instacart"))
        
        assert created == allowed, f"Created {created}, expected {allowed}"
        
        # Verify Kroger folders NOT created
        assert "TOA" not in created
        assert "Skyscraper" not in created
        assert "Carousel" not in created
```

## References

- `utils/path_taxonomy.py` - Taxonomy definitions
- `core/paths.py` - Path creation with enforcement
- `scripts/maintenance/cleanup_taxonomy.py` - Cleanup tool
- `docs/RETAILER_ONBOARDING_CHECKLIST.md` - Section 1 (Output and taxonomy)
