# Archive: Current State (2025-11-16 21:53)

## Purpose
This archive preserves the current codebase state before restoring the working GUI from `restored-oct-27-working` branch.

## Key Improvements in This Version

### Amazon Integration (Major Addition)
- **amazon_search_and_capture.py**: Full Amazon scraper implementation with:
  - Comprehensive ad type detection (SBV, Carousel, Themed Collections, Display, Sponsored Products)
  - Brand extraction and logo matching
  - CDP-based full-page screenshots
  - Debug logging with `capture_debug_amazon_*.log`
  - Salvage logic for partial failures
  - Browser lock management

- **retailers/amazon/adapter.py**: GUI adapter for Amazon integration

### Enhanced Scrapers
- **kroger_search_and_capture.py**: Added debug logging (`capture_debug_kroger_*.log`)
- **instacart_search_and_capture.py**: Added debug logging (`capture_debug_instacart_*.log`)

### Core Infrastructure
- **browser_lock.py**: Per-retailer browser locking system
- **core/**: Enhanced path management and brand utilities
- **brand_logo_database.py**: Brand logo matching system

### GUI Enhancements (Current Issues)
- **keyword_input.py**: Added detailed retry logging but regressed to:
  - `max_retries = 3` (was 1 in working version)
  - Missing scheduler management buttons
  - Missing window state persistence
  - Removed brand review automation

## Known Issues in This Version
1. GUI retry logic reverted to 3 attempts instead of 1
2. Missing "📋 View Logs" and "🔄 Restart" scheduler buttons
3. Amazon salvage logic needs refinement for `tracing.stop()` errors
4. Walmart adapter throws `NotImplementedError`

## Files Archived
- All retailer adapters and scrapers
- Current GUI implementation
- Core utilities and infrastructure
- Git state (log, status, diff)

## Next Steps
1. Restore working GUI from `restored-oct-27-working`
2. Carefully integrate Amazon adapter
3. Preserve single-shot retry logic (`max_retries = 1`)
4. Restore missing scheduler management features
