#!/bin/bash
# Wrapper script for launching the Retail Ad Monitor application

# Setup logging
LOG_DIR="${SCRAPER_HOME:-$HOME/Documents/Amazon_Scrape}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/app_launcher.log"
echo "=== WRAPPER START $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" >> "$LOG_FILE"

# Resolve project directory (prefer SCRAPER_HOME)
if [ -n "${SCRAPER_HOME:-}" ] && [ -d "$SCRAPER_HOME" ]; then
  PROJECT_DIR="$SCRAPER_HOME"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  APP_BUNDLE_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
  PROJECT_DIR="$(dirname "$APP_BUNDLE_DIR")"
fi
export PROJECT_DIR
cd "$PROJECT_DIR"

echo "PROJECT_DIR: $PROJECT_DIR" >> "$LOG_FILE"
echo "Current directory: $(pwd)" >> "$LOG_FILE"

# Choose interpreter (allow venv)
PYTHON_EXEC="${PYTHON_EXEC:-python3}"
echo "Using Python: $PYTHON_EXEC" >> "$LOG_FILE"

echo "Launching Python application..." >> "$LOG_FILE"
"$PYTHON_EXEC" - <<'PY'
import os, sys, traceback
import tkinter as tk

scraper_home = os.environ.get('SCRAPER_HOME') or os.path.expanduser('~/Documents/Amazon_Scrape')
log_dir = os.path.join(scraper_home, 'logs'); os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'wrapper_python.log')

proj = os.environ.get('PROJECT_DIR') or os.getcwd()
sys.path.insert(0, proj)
os.chdir(proj)

with open(log_file,'a',encoding='utf-8') as f:
    f.write(f'\n=== WRAPPER PY START ===\nproj={proj}\nexe={sys.executable}\n')

try:
    import keyword_input
    root = tk.Tk()
    app = keyword_input.KeywordInputApp(root)
    root.mainloop()
except Exception as e:
    with open(log_file,'a',encoding='utf-8') as f:
        f.write(f'Error: {e}\n'); traceback.print_exc(file=f)
    raise
PY
