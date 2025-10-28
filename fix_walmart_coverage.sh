#!/bin/bash
# Fix Walmart image_path coverage
# Run this script to get coverage from 85% to 95%+

set -e

echo "=============================================="
echo "Walmart Image Path Coverage Fix"
echo "=============================================="
echo ""

# Step 1: Rebuild runs from orphan images
echo "Step 1: Rebuilding runs from orphan images..."
python3 tools/batch_rebuild_walmart_runs_from_images.py --write --backup
echo "✅ Rebuild complete"
echo ""

# Step 2: Re-run doctor to check coverage
echo "Step 2: Re-running readiness doctor..."
python3 tools/walmart_readiness_doctor.py
echo ""

echo "=============================================="
echo "Fix complete! Check doctor output above."
echo "=============================================="
