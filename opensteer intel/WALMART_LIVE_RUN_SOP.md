---
title: Walmart Warm-Session Live Run SOP
updated: 2026-04-12
owner: scraping-dev
---

# Walmart Warm-Session Live Run SOP

This SOP is for the first real blocked-run validation of warm-session recovery in `walmart_search_and_capture.py`.

## Goal

Validate whether OpenSteer warm-session cookie injection can resume Walmart scraping after a hard block.

Required test keyword for this SOP:
- `community coffee`

Primary decision signal:
- `cookie_suspicious` log event in `walmart_search_and_capture.py` (line may drift as code changes)
- Specifically whether `ak_bmsc` survives injection without being flagged

## 1) Preflight

- Use a dedicated, burnable profile (not production):
  - `WALMART_PROFILE_DIR=/path/to/walmart_test_profile`
- Ensure warm recovery is enabled:
  - `ENABLE_OPENSTEER_WARM_RECOVERY=1`
- Run headed and interactive:
  - do **not** use `--headless`
  - desktop interaction available for prompt/browser steps
- Ensure OpenSteer CLI works in the same shell:
  - `opensteer --help`

## 1.5) Existing Profile Cookie Renewal (Deterministic)

Use this exactly when classifier says `PROFILE_POISONED`.

1. Reuse the existing dedicated test profile and export it:

```bash
export WALMART_PROFILE_DIR=/path/to/your/existing_walmart_test_profile
```

2. Open Chrome on that exact existing profile:

```bash
open -na "Google Chrome" --args \
  --user-data-dir="$WALMART_PROFILE_DIR" \
  --profile-directory="Default" \
  "https://www.walmart.com"
```

3. Operator actions in that browser (required):
- log in manually
- run search for `community coffee`
- open at least 1 product page
- return to search results

4. End bootstrap phase:
- close all Chrome windows for that launched profile

5. Completion check (must pass before next step):

```bash
ls -lh "$WALMART_PROFILE_DIR"/Default/Cookies "$WALMART_PROFILE_DIR"/Default/Network\ Persistent\ State
```

Expected: both files exist and are non-empty.

6. Handoff to validation run:
- proceed directly to Run B with the same exported `WALMART_PROFILE_DIR`

7. Escalation rule:
- if 2 consecutive cookie-renewal attempts still classify as `PROFILE_POISONED`, then switch to a fresh profile bootstrap once

## 2) Required Validation Sequence (No Prompting)

This validation is only complete if both runs below are executed:
- Run A: baseline live behavior (no forced `_on_blocked` patch)
- Run B: forced warm-session path (one-shot `_on_blocked` test patch)

If Run B is skipped, the warm-session integration is unvalidated.

## 3) Run A — Baseline Command

```bash
python3 walmart_search_and_capture.py "community coffee" --output-dir runs/walmart_live_test
```

Run A purpose:
- capture normal behavior and current bail mode
- confirm environment, profile, and reporting are healthy

## 4) Run B — Forced Warm-Session Path (Mandatory)

Use one deterministic method:
- Preferred: set `WALMART_FORCE_BLOCK_ONCE_FOR_TEST=1` for one run
- Alternative: known-burned test IP/profile

Preferred one-shot flag (no source edits):

```bash
WALMART_FORCE_BLOCK_ONCE_FOR_TEST=1 \
python3 walmart_search_and_capture.py "community coffee" --output-dir runs/walmart_live_test
```

Flag behavior:
- forces `_on_blocked(...)` to return `True` exactly once, then auto-disarms
- does not require modifying source between runs
- in forced mode, relogin prompt is skipped so the run validates warm-session path only

Run B command:

```bash
WALMART_FORCE_BLOCK_ONCE_FOR_TEST=1 python3 walmart_search_and_capture.py "community coffee" --output-dir runs/walmart_live_test
```

## 5) Mandatory Verification Commands (Run B)

Use these on the Run B steps log to verify the intended path actually executed:

```bash
rg -n "hard_block|warm_session_|opensteer_warm_session_done|cookie_suspicious|hard_block_after_warm|hard_block_warm_failed" runs/walmart_live_test/**/*.jsonl
```

Minimum required evidence for a valid Run B:
- at least one `hard_block` event at a warm-recovery hook
- at least one `warm_session_` event (or explicit warm-session failure event)
- presence/absence outcome for `cookie_suspicious` documented in notes
- no `login_relogin` path should be used in forced mode (`login_relogin_skipped` is expected)

If these are missing, Run B did not execute as intended.

## 6) Mandatory Post-Run Cleanup Check

```bash
git diff -- walmart_search_and_capture.py
rg -n "WALMART_FORCE_BLOCK_ONCE_FOR_TEST" walmart_search_and_capture.py
```

Required result before live run:
- no ad-hoc test patch in working diff
- forced-path testing should be done with env flag, not manual code edits

## 7) Log Sequence To Watch

1. Hard block trigger:
   - `hard_block` where `initial_home` or `after_submit`
2. Warm session lifecycle:
   - `opensteer_warm_session_done`
   - `warm_session_cookies_injected`
   - `warm_session_storage_injected` (optional)
3. Decision checkpoint:
   - `cookie_suspicious` event key (do not rely on fixed source line number)
   - check whether `ak_bmsc` is present/accepted vs flagged/dropped
4. Retry outcome:
   - success indicators: results become ready and capture continues
   - fail indicators: `hard_block_after_warm` or `hard_block_warm_failed`

## 8) Pass/Fail Criteria

Pass (keep cookie-injection path):
- Warm session completed
- Cookies injected without fatal errors
- `ak_bmsc` not flagged at `cookie_suspicious`
- Scraper resumes and captures artifacts

Fail (promote fallback):
- `ak_bmsc` flagged/dropped at `cookie_suspicious`
- Immediate re-block after warm injection
- Repeated `hard_block_after_warm`

## 9) Immediate Fallback Rule

If `ak_bmsc` is flagged at the checkpoint, stop iterating injection tuning and switch to profile file-copy fallback from `opensteer intel/INTEGRATION_PLAN.md`.

## 10) Required Artifacts Per Run

- `run_report.json`
- `run_report.md`
- steps log JSONL (path in `meta["steps_log"]`)
- trace zip (if generated)
- one-line verdict:
  - `ak_bmsc survived injection: yes|no`

## 11) Suggested Run Notes Template

```text
Run timestamp:
Keyword:
Profile used:
Run type: baseline | forced
Hard block point: initial_home | after_submit | none
Warm session completed: yes|no
ak_bmsc survived injection: yes|no
Outcome: success | hard_block_after_warm | hard_block_warm_failed | other
Fallback switched: yes|no
Artifacts path:
```

## 12) Feedback Loop Rules (Mandatory)

Logging alone is not sufficient. Every run must produce a next-run decision.

### 12.0 Automated Decision Command (Use Every Run)

Baseline/non-forced run:

```bash
python3 tools/walmart_next_run_decision.py --runs-root runs/walmart_live_test
```

Forced-path run:

```bash
python3 tools/walmart_next_run_decision.py --runs-root runs/walmart_live_test --expect-forced
```

The command prints:
- `classification`
- `next_action`
- key measured signals used for the decision

### 12.1 Measurable Signals To Record

- `run_report.json`:
  - `bail_reason`
  - `cookies.pre_count`
  - `cookies.post_count`
  - `cookies.suspicious` (if present)
- steps JSONL:
  - `hard_block` events (where/reason)
  - `warm_session_*` and `opensteer_warm_session_done`
  - `cookie_suspicious`

### 12.2 Run Classification

- `INVALID_TEST`:
  - forced run did not include `hard_block` at a warm-recovery hook, or
  - forced run has no `warm_session_*` evidence
- `WARM_PATH_FAILED`:
  - `bail_reason=hard_block_warm_failed` or `warm_session_error` present
- `COOKIE_REJECTED`:
  - `cookie_suspicious` includes `ak_bmsc` after warm injection, or
  - immediate `hard_block_after_warm`
- `PROFILE_POISONED`:
  - `cookies.post_count == 0` and bail due to PX/block behavior
- `WARM_PATH_SUCCESS`:
  - warm session completed, no `ak_bmsc` suspicion, capture flow resumed

### 12.3 Mandatory Next-Run Action Matrix

- If `INVALID_TEST`:
  - rerun forced test with `WALMART_FORCE_BLOCK_ONCE_FOR_TEST=1`
  - do not treat as integration result
- If `WARM_PATH_FAILED`:
  - fix the specific warm-session error class before another live run
  - rerun forced test after fix
- If `COOKIE_REJECTED`:
  - switch next run to file-copy fallback path (from `INTEGRATION_PLAN.md`)
  - stop iterating cookie-injection tuning for that profile
- If `PROFILE_POISONED`:
  - renew cookies on the existing test profile first (manual login+browse), then rerun forced path
  - switch to a fresh test profile only after 2 failed renewal attempts
- If `WARM_PATH_SUCCESS`:
  - run one more forced confirmation run
  - if 2 consecutive successes, move to non-forced live validation

### 12.4 Promotion Rule

- Do not call the integration production-ready until:
  - 2 consecutive forced runs are `WARM_PATH_SUCCESS`, and
  - 2 consecutive non-forced runs avoid `hard_block_warm_failed` and `hard_block_after_warm`
