"""Structured JSON output helpers for cli-web-tiktokshop."""
from __future__ import annotations

import json


def json_success(data, **extra) -> str:
    """Format a successful result as JSON string."""
    payload = {"success": True, "data": data}
    payload.update(extra)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def json_error(code: str, message: str, **extra) -> str:
    """Format an error result as JSON string."""
    payload = {"error": True, "code": code, "message": message}
    payload.update(extra)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def print_json_output(data) -> None:
    """Print data as formatted JSON — used by --json commands."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def print_table(items, headers=None) -> None:
    """Print a list of dicts as a simple text table."""
    if not items:
        print("(no results)")
        return
    if not headers and items:
        headers = list(items[0].keys())
    widths = {h: max(len(str(h)), max(len(str(row.get(h, ""))) for row in items)) for h in headers}
    header_row = "  ".join(str(h).ljust(widths[h]) for h in headers)
    sep = "  ".join("-" * widths[h] for h in headers)
    print(header_row)
    print(sep)
    for row in items:
        print("  ".join(str(row.get(h, "")).ljust(widths[h]) for h in headers))
