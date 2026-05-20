#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


BLOCK_BAIL_REASONS = {
    "px_locked",
    "hard_block",
    "hard_block_after_warm",
    "hard_block_warm_failed",
    "hard_block_non_interactive",
}


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
    return rows


def _find_latest_run_dir(runs_root: Path) -> Path:
    candidates: List[Path] = []
    for child in runs_root.iterdir():
        if not child.is_dir():
            continue
        if (child / "run_report.json").exists():
            candidates.append(child)
    if not candidates:
        raise FileNotFoundError(f"No run directories with run_report.json under {runs_root}")
    return sorted(candidates, key=lambda p: p.name)[-1]


def _contains_ak_bmsc(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(v).lower() == "ak_bmsc" for v in value)
    return False


def classify_run(report: Dict[str, Any], steps: List[Dict[str, Any]], expect_forced: bool) -> Dict[str, Any]:
    bail_reason = report.get("bail_reason")
    outcome = report.get("outcome")

    cookies = report.get("cookies") or {}
    post_count = int(cookies.get("post_count") or 0)
    report_suspicious = cookies.get("suspicious") or []

    hard_block_hook = False
    warm_evidence = False
    warm_error = False
    hard_block_after_warm = False
    step_ak_bmsc = False

    for row in steps:
        event = row.get("event")
        if event == "hard_block" and row.get("where") in {"initial_home", "after_submit"}:
            hard_block_hook = True
        if isinstance(event, str) and (event.startswith("warm_session_") or event == "opensteer_warm_session_done"):
            warm_evidence = True
        if event in {"warm_session_error", "warm_session_cookie_error", "warm_session_storage_error", "warm_session_invalid"}:
            warm_error = True
        if event == "hard_block_after_warm":
            hard_block_after_warm = True
        if event == "cookie_suspicious" and _contains_ak_bmsc(row.get("names") or []):
            step_ak_bmsc = True

    report_ak_bmsc = _contains_ak_bmsc(report_suspicious)
    ak_bmsc_suspicious = step_ak_bmsc or report_ak_bmsc

    if expect_forced and (not hard_block_hook or not warm_evidence):
        classification = "INVALID_TEST"
        next_action = "Rerun forced path with WALMART_FORCE_BLOCK_ONCE_FOR_TEST=1; treat this run as non-evidence."
    elif bail_reason == "hard_block_warm_failed" or warm_error:
        classification = "WARM_PATH_FAILED"
        next_action = "Fix warm-session error class first, then rerun forced path."
    elif hard_block_after_warm or ak_bmsc_suspicious:
        classification = "COOKIE_REJECTED"
        next_action = "Switch next run to profile file-copy fallback; stop injection tuning for this profile."
    elif post_count == 0 and bail_reason in BLOCK_BAIL_REASONS:
        classification = "PROFILE_POISONED"
        next_action = "Renew cookies on the existing test profile first (manual Walmart login+browse), then rerun forced path; only switch to fresh profile after 2 failed renewal attempts."
    elif warm_evidence and outcome == "success" and not hard_block_after_warm and not ak_bmsc_suspicious:
        classification = "WARM_PATH_SUCCESS"
        next_action = "Run one more forced confirmation; if 2 consecutive successes, move to non-forced validation."
    else:
        classification = "BASELINE_OR_OTHER"
        next_action = "Run forced-path validation next to produce warm-session evidence."

    return {
        "classification": classification,
        "next_action": next_action,
        "signals": {
            "expect_forced": expect_forced,
            "outcome": outcome,
            "bail_reason": bail_reason,
            "post_count": post_count,
            "hard_block_hook": hard_block_hook,
            "warm_evidence": warm_evidence,
            "warm_error": warm_error,
            "hard_block_after_warm": hard_block_after_warm,
            "ak_bmsc_suspicious": ak_bmsc_suspicious,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify latest Walmart run and output required next action.")
    parser.add_argument("--runs-root", default="runs/walmart_live_test", help="Root folder containing timestamped run dirs")
    parser.add_argument("--run-id", default=None, help="Optional specific run directory name (timestamp)")
    parser.add_argument("--expect-forced", action="store_true", help="Set when classifying a forced-path run")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    runs_root = Path(args.runs_root)
    if not runs_root.exists():
        raise FileNotFoundError(f"Runs root not found: {runs_root}")

    run_dir = runs_root / args.run_id if args.run_id else _find_latest_run_dir(runs_root)
    report_path = run_dir / "run_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"run_report.json not found in {run_dir}")

    report = _read_json(report_path)

    steps_path: Optional[Path] = None
    artifacts = report.get("artifacts") or {}
    step_log_path = artifacts.get("steps_log")
    if step_log_path:
        p = Path(step_log_path)
        if p.exists():
            steps_path = p

    if steps_path is None:
        matches = sorted(run_dir.glob("*.jsonl"))
        if not matches:
            raise FileNotFoundError(f"No steps jsonl found in {run_dir}")
        steps_path = matches[0]

    steps = _read_jsonl(steps_path)
    result = classify_run(report, steps, args.expect_forced)

    output = {
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "steps_log": str(steps_path),
        **result,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"run_id: {output['run_id']}")
        print(f"classification: {output['classification']}")
        print(f"next_action: {output['next_action']}")
        print("signals:")
        for k, v in output["signals"].items():
            print(f"  - {k}: {v}")
        print(f"steps_log: {output['steps_log']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
