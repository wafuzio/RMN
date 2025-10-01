import os, sys, traceback, runpy, subprocess

# Boot logger so we can see exactly what Finder launched
LOG_DIR = os.path.join(os.path.expanduser('~/Documents/Amazon_Scrape'), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
BOOT_LOG = os.path.join(LOG_DIR, 'app_launcher_boot.log')

def _bootlog(msg: str):
    try:
        with open(BOOT_LOG, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except Exception:
        pass

def find_source_root():
    """Resolve the live source directory to run."""
    home = os.environ.get("SCRAPER_HOME")
    if home and os.path.isdir(home):
        return home
    default = os.path.expanduser("~/Documents/Amazon_Scrape")
    if os.path.isdir(default):
        return default
    # Fallback: derive from bundle path
    current_file = os.path.abspath(__file__)
    app_bundle_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))  # .../.app/Contents/MacOS/launcher.py
    return os.path.dirname(app_bundle_dir)

def load_env_file(src_root: str):
    """Load config/launcher.env if present (SCRAPER_HOME, PYTHON_EXEC, etc.)."""
    env_path = os.path.join(src_root, "config", "launcher.env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def pick_python(src_root: str) -> str:
    """Choose the venv python if available, else respect PYTHON_EXEC, else env python3."""
    venv_py = os.path.join(src_root, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        return venv_py
    return os.environ.get("PYTHON_EXEC") or "/usr/bin/env python3"

def run_in_process(entry: str, src_root: str):
    """
    Run the live script inside the app’s embedded interpreter (single Dock icon).
    Apply guards so Tk/Cocoa doesn't create a native menubar/console early.
    """
    # Guards for embedded Tk/Cocoa
    os.environ["RAM_NO_NATIVE_MENUBAR"] = "1"  # your GUI should detect this and avoid root.config(menu=...)
    os.environ["TK_CONSOLE"] = "0"            # block Tk console window
    os.environ["TK_NO_CONSOLE"] = "1"
    os.environ.setdefault("SCRAPER_HOME", src_root)

    _bootlog("run_in_process: set RAM_NO_NATIVE_MENUBAR=1, TK_CONSOLE=0, TK_NO_CONSOLE=1")
    sys.path.insert(0, src_root)
    os.chdir(src_root)
    _bootlog(f"cwd(after)={os.getcwd()}")
    _bootlog(f"Executing in-process: {entry}")
    runpy.run_path(entry, run_name="__main__")

def run_spawn(entry: str, src_root: str):
    """Spawn the venv python as a fallback (will show a second Dock icon)."""
    py = pick_python(src_root)
    _bootlog(f"run_spawn: {py} {entry} (cwd={src_root})")
    subprocess.Popen([py, entry], cwd=src_root)

def main():
    src_root = find_source_root()
    load_env_file(src_root)
    os.environ.setdefault("SCRAPER_HOME", src_root)
    entry = os.path.join(src_root, "keyword_input.py")

    _bootlog("=== LAUNCHER START ===")
    _bootlog(f"PID={os.getpid()} exe={sys.executable}")
    _bootlog(f"cwd(before)={os.getcwd()}")
    _bootlog(f"src_root={src_root}")
    _bootlog(f"entry={entry}")
    _bootlog(f"PYTHON_EXEC={os.environ.get('PYTHON_EXEC')}")
    _bootlog("Attempting run_in_process...")

    if not os.path.exists(entry):
        _bootlog("ERROR: keyword_input.py not found")
        print(f"[LAUNCHER] keyword_input.py not found: {entry}", file=sys.stderr)
        input("\nPress Enter to exit…")
        return

    try:
        run_in_process(entry, src_root)
    except Exception:
        _bootlog("run_in_process failed; falling back to spawn")
        traceback.print_exc()
        try:
            run_spawn(entry, src_root)
        except Exception:
            _bootlog("run_spawn also failed")
            traceback.print_exc()
            input("\nPress Enter to exit…")

if __name__ == "__main__":
    main()