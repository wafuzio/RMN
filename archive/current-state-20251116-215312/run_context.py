# core/run_context.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class RunContext:
    retailer: str            # "kroger", "walmart", ...
    client: str              # sanitized client folder name
    base_dir: str            # get_base_dir()
    output_dir: str          # .../output/<retailer>/<client>
    runs_dir: str            # .../runs
    logs_dir: str            # .../logs/<retailer>
    profile_dir: str | None  # resolved from env or default
    script_dir: str          # directory with screenshot scripts
