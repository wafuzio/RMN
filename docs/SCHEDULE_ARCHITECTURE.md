# Schedule Architecture

## Overview

As of October 2025, the scraper uses a **centralized schedule system** with schedules stored in the `schedules/` directory. This replaces the legacy distributed approach where schedules were scattered across `output/<retailer>/<client>/schedule_config.json`.

**Status: ✅ Refactor Complete** - All components now use a shared validation library with normalized schemas, conflict detection, and timezone support.

## Directory Structure

```
schedules/
├── kroger__blue_bunny__ice_cream.json
├── kroger__bandaid__first_aid.json
├── instacart__blue_bunny__ice_cream.json
├── walmart__blue_bunny__ice_cream.json
└── master_schedule.json (generated index)
```

## Schedule File Format

Each schedule file uses a normalized schema with 24-hour times and lowercase day names:

```json
{
  "id": "kroger_blue_bunny_ice_cream_7d181867",
  "retailer": "kroger",
  "client": "blue bunny",
  "keywords": ["ice cream", "frozen dessert"],
  "days": ["monday", "wednesday", "friday"],
  "times": ["08:00", "12:00", "16:00"],
  "enabled": true,
  "created_at": "2025-10-16T18:32:00Z",
  "updated_at": "2025-10-16T18:32:00Z"
}
```

### Schema Fields

- **id** (string): Unique identifier for the schedule
- **retailer** (string): Retailer slug (kroger, walmart, instacart, etc.)
- **client** (string): Client/product name
- **keywords** (array): Search terms to scrape
- **days** (array): Days of week (lowercase: monday, tuesday, etc.)
- **times** (array): Run times in 24-hour HH:MM format
- **enabled** (boolean): Whether this schedule is active
- **created_at** (string): ISO 8601 timestamp
- **updated_at** (string): ISO 8601 timestamp

## Master Schedule Index

The `master_schedule.json` file is a generated index containing all schedules:

```json
{
  "schedules": [
    { /* schedule 1 */ },
    { /* schedule 2 */ },
    ...
  ],
  "version": "1.0"
}
```

This file is **generated** by the migration tool and can be regenerated at any time. The individual schedule files are the source of truth.

## Benefits of New Architecture

### ✅ Separation of Concerns
- **Pre-scrape configs** → `schedules/`
- **Post-scrape results** → `output/`

### ✅ Human-Friendly Filenames
- Old: `output/kroger/blue_bunny/schedule_config.json`
- New: `schedules/kroger__blue_bunny__ice_cream.json`

### ✅ Single Source of Truth
- One directory to backup/restore
- Easy to see all schedules at once
- Git-friendly (clear diffs)

### ✅ Better Conflict Detection
- All schedules in one place
- No need to glob across output/ directory
- Faster schedule loading

### ✅ Easier Management
- Add/edit/delete schedules by filename
- No nested directory navigation
- Clear naming convention

## Migration

### Running the Migration

To migrate from the old distributed format to the new centralized format:

```bash
python3 tools/migrate_schedules.py
```

This will:
1. Scan `output/<retailer>/<client>/schedule_config.json` files
2. Normalize the schema (24-hour times, lowercase days)
3. Create individual schedule files in `schedules/`
4. Generate `schedules/master_schedule.json` index
5. **Keep legacy files** for backwards compatibility

### Backwards Compatibility

The scheduler daemon reads schedules in this order:

1. **New location**: `schedules/*.json` (preferred)
2. **Legacy location**: `output/<retailer>/<client>/schedule_config.json` (fallback)

This allows gradual migration without breaking existing schedules.

### Cleaning Up Legacy Files

After verifying the migration worked, you can safely delete the old schedule files:

```bash
find output -name "schedule_config.json" -delete
```

## GUI Integration

The GUI (`keyword_input.py`) will be updated to:
- Save new schedules to `schedules/` directory
- Read from `schedules/` for conflict detection
- Display schedules from the master index

## Daemon Behavior

The `scheduler_daemon.py`:
- Scans `schedules/` directory first
- Falls back to legacy `output/` locations
- Logs which files it finds and loads
- Continues to work with both formats during transition

## File Naming Convention

Schedule filenames follow this pattern:

```
<retailer>__<client>__<keyword_slug>.json
```

Examples:
- `kroger__blue_bunny__ice_cream.json`
- `walmart__bandaid__first_aid.json`
- `instacart__stonyfield__yogurt.json`

If multiple schedules exist for the same retailer/client/keyword, a hash suffix is added:
- `kroger__blue_bunny__ice_cream__7d181867.json`

## Shared Library

### schedules/schedules_lib.py

All components (daemon, GUI, CLI tools) now use a shared library for consistent schedule handling.

**Key Features:**
- `Schedule` dataclass with validation
- `scan_schedules()` - Load from both new and legacy locations
- `build_master_index()` - Generate master_schedule.json
- `detect_conflicts()` - Find scheduling conflicts (5-minute window)
- `now_in_tz()` - Timezone-aware time handling
- Normalized day/time parsing

**Usage Example:**
```python
from schedules.schedules_lib import scan_schedules, detect_conflicts
from pathlib import Path

schedules = scan_schedules(Path("/path/to/scraper"))
conflicts = detect_conflicts(schedules, window_minutes=5)
```

## Tools

### Migration Tool: tools/migrate_schedules.py

One-time migration script to convert legacy schedules to new format.

**What it does:**
- Scans `output/<retailer>/<client>/schedule_config.json`
- Normalizes times to 24-hour format
- Normalizes days to lowercase
- Creates descriptive filenames
- Generates master index

**Run:**
```bash
python3 tools/migrate_schedules.py
```

### Validation Tool: tools/rebuild_master_schedule.py

CI-friendly validation and index rebuilder.

**What it does:**
- Validates all schedules
- Detects conflicts
- Rebuilds master_schedule.json
- Returns exit code 1 if conflicts found

**Run:**
```bash
python3 tools/rebuild_master_schedule.py
```

**Example Output:**
```
✅ Found 4 valid schedules:
   ✓ [NEW] kroger/bandaid - 0 keywords, 7 days, 1 times
   ✓ [NEW] kroger/blue bunny - 0 keywords, 5 days, 5 times
🔍 Checking for scheduling conflicts...
   ✓ No conflicts detected
📝 Building master index...
   ✓ Wrote schedules/master_schedule.json
```

## Daemon Integration

The `scheduler_daemon.py` now:

1. **Uses shared library** - Imports `schedules_lib.py`
2. **Reads new location first** - `schedules/*.json` preferred
3. **Falls back to legacy** - `output/*/*/schedule_config.json` still works
4. **Derives output paths** - Uses `schedule.output_dir` from library
5. **Logs with context** - Includes `[retailer]` in all log messages
6. **Supports timezones** - Uses `now_in_tz()` for schedule matching
7. **Validates on load** - Invalid schedules are skipped with warnings

**Example Logs:**
```
[2025-10-16 13:32:45] tick: monday 13:32 | 4 schedule(s)
→ DUE: [kroger] blue bunny @ 13:32 (schedules/kroger__blue_bunny__default.json)
SCRAPE_LAUNCHED_ASYNC: [kroger] blue bunny
```

## Migration Results

```
✅ Migrated 4 schedules from output/ to schedules/
✅ Deleted legacy files after verification
✅ No conflicts detected
✅ Master index generated
```

## Benefits Achieved

### 1. Separation of Concerns
- **Config**: `schedules/` directory
- **Results**: `output/` directory

### 2. Single Source of Truth
- One directory to backup: `schedules/`
- One file for overview: `master_schedule.json`
- Git-friendly diffs

### 3. Validation & Safety
- Schema validation on load
- Conflict detection before save
- Timezone support prevents DST issues

### 4. Developer Experience
- Shared library = consistent behavior
- Descriptive filenames = easy to find
- CI-friendly tools = automated validation

### 5. Maintainability
- One place to fix bugs
- One place to add features
- Clear upgrade path

## Future Enhancements

Potential improvements to the schedule system:

1. **Schedule Templates** - Reusable schedule patterns
2. **Schedule Groups** - Bulk enable/disable related schedules
3. **Schedule History** - Track changes over time
4. **Web UI** - Browser-based schedule management
5. **Multi-timezone Dashboard** - View schedules across timezones
6. **Schedule Import/Export** - Share schedules between environments
