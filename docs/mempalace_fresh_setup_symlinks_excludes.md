# Fresh MemPalace Setup (Symlinks + Excludes)

This guide sets up a clean MemPalace workflow that:
- uses stable symlink paths,
- skips large/noisy file types and folders,
- mines from a filtered stage directory,
- keeps your source repo untouched.

## 1) Define stable paths

```bash
PAL_BASE="$HOME/.mempalace"
PALACE="$PAL_BASE/palace_fresh"
LINKS="$PAL_BASE/links"
SRC_REAL="$HOME/Documents/Amazon_Scrape"
SRC_LINK="$LINKS/amazon_scrape"
STAGE="$PAL_BASE/stage/amazon_scrape"
EX="$HOME/mempalace_excludes.txt"
```

## 2) Create symlinked source path

```bash
mkdir -p "$LINKS" "$PAL_BASE/stage"
ln -sfn "$SRC_REAL" "$SRC_LINK"
```

Why: the symlink path (`$SRC_LINK`) stays stable even if your real project location changes.

## 3) Create/update excludes

Use one pattern per line. This file is consumed by `rsync --exclude-from`.

```bash
cat > "$EX" <<'EOF'
# VCS / deps / build
.git/
node_modules/
.venv/
venv/
dist/
build/
coverage/
.cache/
__pycache__/
.pytest_cache/
.mypy_cache/
.next/

# Heavy profiles / browser state
profiles/
playwright_profile/

# Generated run artifacts
--output-dir/
runs/
run_results_*
search_results_*
*_test_output_*
Trace-*.json

# Logs and db files
*.log
*.sqlite
*.sqlite3
*.db

# Archives
*.zip
*.tar
*.gz
*.7z

# Media/binary-heavy
*.mp4
*.mov
*.avi
*.mkv
*.webm
*.png
*.jpg
*.jpeg
*.gif
*.webp

# Optional: folders known to be already indexed
# tools/
# tests/
# PerimeterX-Solver/
# cache/
EOF
```

## 4) Build filtered stage from symlink source

```bash
mkdir -p "$STAGE"
rsync -a --delete --prune-empty-dirs --exclude-from="$EX" "$SRC_LINK"/ "$STAGE"/
find "$STAGE" -type f | wc -l
```

## 5) Initialize + mine a fresh palace

```bash
mempalace init --yes "$STAGE"
mempalace --palace "$PALACE" mine "$STAGE" 2>&1 | tee /tmp/mempalace-mine-fresh.log
```

## 6) Live monitoring commands

```bash
# Check miner process
ps aux | rg -i "mempalace( |$).*mine|python.*mempalace.*mine" | rg -v rg

# Watch mine log
tail -f /tmp/mempalace-mine-fresh.log

# Watch DB growth
watch -n 5 "stat -f '%Sm %z %N' $PALACE/chroma.sqlite3"
```

If `watch` is unavailable on your mac, use:

```bash
while true; do stat -f '%Sm %z %N' "$PALACE/chroma.sqlite3"; sleep 5; done
```

## 7) Re-run safely later

When source files change:

```bash
rsync -a --delete --prune-empty-dirs --exclude-from="$EX" "$SRC_LINK"/ "$STAGE"/
mempalace --palace "$PALACE" mine "$STAGE" 2>&1 | tee /tmp/mempalace-mine-fresh.log
```

This keeps accumulating in the same palace (`$PALACE`) instead of starting over.

## 8) Optional: switch to a brand-new palace instantly

```bash
NEW_PALACE="$PAL_BASE/palace_$(date +%Y%m%d_%H%M%S)"
mempalace --palace "$NEW_PALACE" mine "$STAGE"
```

Use this when you want a truly clean index without touching previous palaces.
