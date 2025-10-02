"""
Bootstrap script to ensure Playwright browsers are installed to a user-writable location.
This avoids issues with app bundles and system Python installations.
"""
import os
import sys
import subprocess
import pathlib

# Where Playwright should put browsers (outside the app bundle, user-writable)
DEFAULT_PW_PATH = os.path.expanduser("~/Library/Application Support/RMN/playwright-browsers")


def _chromium_binary_exists(pw_path: str) -> bool:
    """Quick heuristic: look for Chromium.app inside any downloaded build"""
    root = pathlib.Path(pw_path)
    if not root.exists():
        return False
    return any(p.name == "Chromium.app" for p in root.rglob("Chromium.app"))


def ensure_playwright_browsers() -> str:
    """
    Ensure Playwright Chromium is installed to a user-writable location.
    Returns the path where browsers are installed.
    """
    pw_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", DEFAULT_PW_PATH)
    os.makedirs(pw_path, exist_ok=True)
    
    # Make it visible to Playwright and subprocesses
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = pw_path
    
    if _chromium_binary_exists(pw_path):
        return pw_path
    
    # Install Chromium only (faster, we don't need webkit/firefox here)
    print(f"[bootstrap] Installing Playwright Chromium into: {pw_path}")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": pw_path},
            capture_output=False,
        )
    except subprocess.CalledProcessError as e:
        print("[bootstrap] Playwright install failed:", e)
        raise
    
    if not _chromium_binary_exists(pw_path):
        raise RuntimeError("Playwright Chromium install appears incomplete.")
    
    print("[bootstrap] Playwright Chromium ready.")
    return pw_path


if __name__ == "__main__":
    ensure_playwright_browsers()
