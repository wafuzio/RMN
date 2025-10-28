# Quick Fix: Walmart Builder.io Readiness

## Issues Found

✅ **API Error Fixed** - Doctor script now correctly parses `/api/retailers` response
⚠️ **Data Coverage: 85%** - Need 95%+ (57 ads missing image_path)

---

## Fix Commands

### Option 1: Automated (Recommended)

```bash
./fix_walmart_coverage.sh
```

This script runs all three steps automatically.

### Option 2: Manual Steps

**Step 1: Rebuild runs from orphan images**
```bash
python3 tools/batch_rebuild_walmart_runs_from_images.py --write --backup
```

**Step 2: Reconcile remaining ads**
```bash
python3 tools/reconcile_walmart_images_to_json.py --write --backup --min-score 6
```

**Step 3: Verify**
```bash
python3 tools/walmart_readiness_doctor.py
```

---

## Expected Results

After running the fix:
- ✅ Image path coverage: 95%+ (target met)
- ✅ API endpoints: All passing
- ✅ Taxonomy compliance: 100%

---

## Current Status Breakdown

**SBA (Sponsored Brand Ads):**
- Total: 177 ads
- With images: 165 (93%)
- Missing: 12 ads need image_path

**SBV (Sponsored Brand Video):**
- Total: 149 ads
- With images: 135 (91%)
- Missing: 14 ads need image_path
- Note: 5 filename pattern mismatches

**Tile_Takeover:**
- Total: 55 ads
- With images: 24 (44%)
- Missing: 31 ads need image_path

**Overall:**
- Total: 381 ads
- With image_path: 324 (85%)
- Missing: 57 ads (15%)

---

## What the Fix Does

### batch_rebuild_walmart_runs_from_images.py
- Scans all Walmart image files
- Creates/repairs run JSONs for orphan images
- Links images to ads via canonical schema
- Creates backups before modifying

### reconcile_walmart_images_to_json.py
- Matches ads to images by:
  - Date token (D2025-10-27_T14-32.15)
  - Ad type (SBA, SBV, Tile_Takeover)
  - Brand/client/keyword
- Uses fuzzy matching (min-score 6)
- Updates ad.image_path field
- Creates backups before modifying

---

## Troubleshooting

### "No changes made"
- Images may already be linked
- Check if image files exist: `ls output/walmart/*/SBA/`

### "Still below 95% after fix"
- Run audit to see specific issues:
  ```bash
  python3 tools/audit_adtype_mapping.py | grep walmart
  ```
- Check for orphaned JSON entries (ads without images)
- May need to re-run scraper for missing images

### "API still failing"
- Restart servers:
  ```bash
  ./restart_servers.sh
  ```
- Verify Flask is running:
  ```bash
  curl http://localhost:5006/health
  ```

---

## Next Steps After Fix

1. **Verify coverage:**
   ```bash
   python3 tools/walmart_readiness_doctor.py
   ```
   Expected: ✅ ALL CHECKS PASSED

2. **Test API:**
   ```bash
   curl "http://localhost:5006/api/ads/cards?retailer=walmart&client=<client>&page_size=5" | jq
   ```

3. **Test in Builder.io:**
   - Open Builder.io
   - Fetch ads from ngrok URL
   - Verify all cards render with images

---

**Created:** 2025-10-27
**Status:** Ready to run
