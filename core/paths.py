# core/paths.py
from __future__ import annotations
import os

def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def logs_dir_for(base: str, retailer: str) -> str:
    d = os.path.join(base, "logs", retailer)
    ensure_dir(d); ensure_dir(os.path.join(d, "locks"))
    return d

def output_dir_for(base: str, retailer: str, client: str) -> str:
    d = os.path.join(base, "output", retailer, client)
    ensure_dir(d)
    ensure_dir(os.path.join(d, "runs"))
    for leaf in ("TOA", "Skyscraper", "Carousel"):
        ensure_dir(os.path.join(d, leaf))
    return d
