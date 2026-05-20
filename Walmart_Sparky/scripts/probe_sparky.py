#!/usr/bin/env python3
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import Page
from walmart_search_and_capture import (
    DebugConfig,
    PROFILE_ENV,
    StepLogger,
    _apply_debug_config,
    _get_proxy_config,
    _launch,
    build_run_id,
    safe_filename,
    step,
)
import walmart_search_and_capture as walmart_mod

DEFAULT_QUERIES = [
    "show me Garanimals toddler shirts",
    "show me Wonder Nation toddler shirts",
    "cheap kids clothes",
    "best toddler clothes at Walmart",
    "what's the difference between Garanimals and Wonder Nation",
    "what is the best toddler clothing brand at Walmart",
    "show me Cat & Jack toddler shirts",
    "is Cat & Jack sold at Walmart",
    "durable toddler clothes at Walmart",
    "cute toddler outfits under $20",
    "mix and match toddler clothes",
    "school clothes for 4 year old under $30",
]

DEFAULT_SELECTORS = {
    "open_button": [
        '[aria-label*="Sparky" i]',
        '[data-testid*="sparky" i]',
        'button:has-text("Sparky")',
        'button:has-text("Ask Sparky")',
        'button:has-text("Ask Walmart")',
        'a:has-text("Sparky")',
        'text="Sparky"',
    ],
    "chat_input": [
        'textarea[placeholder*="Ask" i]',
        'textarea',
        '[contenteditable="true"]',
        'input[placeholder*="Ask" i]',
        'input[type="text"]',
    ],
    "send_button": [
        'button[aria-label*="Send" i]',
        'button:has-text("Send")',
        'button[type="submit"]',
    ],
    "response_container": [
        '[data-testid*="sparky" i]',
        '[aria-label*="Sparky" i]',
        'main',
        'body',
    ],
    "product_cards": [
        '[data-testid*="product" i]',
        '[data-item-id]',
        'a[href*="/ip/"]',
        'div:has(a[href*="/ip/"])',
    ],
}

SPARKY_HINTS = (
    "sparky",
    "assistant",
    "chat",
    "conversation",
    "ask",
    "copilot",
    "llm",
    "ai",
)

BOT_SIGNAL_TEXT = (
    "robot or human",
    "press and hold",
    "verify you are human",
    "access denied",
    "blocked",
    "captcha",
    "unusual traffic",
    "automated access",
)

BOT_SIGNAL_URL_PARTS = (
    "/blocked",
    "px-captcha",
    "captcha",
    "perimeterx",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BotDetectionTriggered(RuntimeError):
    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        msg = reason if not detail else f"{reason}: {detail}"
        super().__init__(msg)


def load_json_if_exists(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_run_layout(base_dir: Path, run_id: str) -> Dict[str, Path]:
    run_dir = ensure_dir(base_dir / "runs" / run_id)
    return {
        "run_dir": run_dir,
        "screenshots": ensure_dir(run_dir / "screenshots"),
        "dom": ensure_dir(run_dir / "dom"),
        "network": ensure_dir(run_dir / "network"),
        "queries": ensure_dir(run_dir / "queries"),
    }


def candidate_paths() -> Tuple[Path, Path]:
    config_dir = Path(__file__).resolve().parent / "config"
    return config_dir / "probe_queries.json", config_dir / "selectors.json"


def load_probe_queries() -> List[str]:
    query_path, _ = candidate_paths()
    data = load_json_if_exists(query_path, DEFAULT_QUERIES)
    if isinstance(data, dict):
        data = data.get("queries", DEFAULT_QUERIES)
    if not isinstance(data, list):
        return list(DEFAULT_QUERIES)
    cleaned = [str(item).strip() for item in data if str(item).strip()]
    return cleaned or list(DEFAULT_QUERIES)


def load_selectors() -> Dict[str, List[str]]:
    _, selector_path = candidate_paths()
    data = load_json_if_exists(selector_path, DEFAULT_SELECTORS)
    if not isinstance(data, dict):
        return dict(DEFAULT_SELECTORS)
    merged: Dict[str, List[str]] = {}
    for key, default_values in DEFAULT_SELECTORS.items():
        raw = data.get(key, default_values)
        if isinstance(raw, list) and raw:
            merged[key] = [str(v) for v in raw if str(v).strip()]
        else:
            merged[key] = list(default_values)
    return merged


def first_visible(page: Page, selectors: List[str], timeout_ms: int = 2500):
    deadline = time.time() + max(timeout_ms, 0) / 1000.0
    for selector in selectors:
        locator = page.locator(selector).first
        while time.time() < deadline:
            try:
                if locator.is_visible():
                    return selector, locator
            except Exception:
                break
            page.wait_for_timeout(100)
    return None, None


def try_click_first(page: Page, selectors: List[str], sl: StepLogger, event: str) -> Optional[str]:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible():
                locator.click(timeout=2000)
                sl.log(event, selector=selector)
                page.wait_for_timeout(1200)
                return selector
        except Exception as e:
            sl.log(f"{event}_failed", selector=selector, error=str(e))
    return None


def open_sparky(page: Page, selectors: Dict[str, List[str]], sl: StepLogger) -> bool:
    page.wait_for_timeout(2500)
    clicked = try_click_first(page, selectors["open_button"], sl, "sparky_open_clicked")
    if clicked:
        return True

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for selector in selectors["open_button"]:
            locator = frame.locator(selector).first
            try:
                if locator.is_visible():
                    locator.click(timeout=2000)
                    sl.log("sparky_open_clicked_in_frame", selector=selector, frame_url=frame.url)
                    page.wait_for_timeout(1200)
                    return True
            except Exception as e:
                sl.log("sparky_open_frame_click_failed", selector=selector, frame_url=frame.url, error=str(e))
    return False


def get_input_target(page: Page, selectors: Dict[str, List[str]], sl: StepLogger):
    selector, locator = first_visible(page, selectors["chat_input"], timeout_ms=3500)
    if locator is not None:
        sl.log("sparky_input_found", selector=selector)
        return selector, locator, None
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for selector in selectors["chat_input"]:
            locator = frame.locator(selector).first
            try:
                if locator.is_visible():
                    sl.log("sparky_input_found_in_frame", selector=selector, frame_url=frame.url)
                    return selector, locator, frame
            except Exception:
                continue
    return None, None, None


def submit_query(page: Page, query: str, selectors: Dict[str, List[str]], sl: StepLogger) -> Dict[str, Any]:
    selector, locator, frame = get_input_target(page, selectors, sl)
    if locator is None:
        raise RuntimeError("Could not find a Sparky input field with current candidate selectors")

    scope = frame if frame is not None else page
    try:
        locator.click(timeout=2000)
    except Exception:
        pass

    try:
        locator.fill(query)
    except Exception:
        locator.click(timeout=2000)
        page.keyboard.press("Meta+A")
        page.keyboard.press("Control+A")
        page.keyboard.type(query, delay=random.randint(25, 75))

    sl.log("sparky_query_typed", selector=selector, query=query, in_frame=bool(frame))

    sent = False
    for send_selector in selectors["send_button"]:
        button = scope.locator(send_selector).first
        try:
            if button.is_visible():
                button.click(timeout=1500)
                sl.log("sparky_send_clicked", selector=send_selector)
                sent = True
                break
        except Exception as e:
            sl.log("sparky_send_click_failed", selector=send_selector, error=str(e))

    if not sent:
        locator.press("Enter")
        sl.log("sparky_send_enter")

    return {"input_selector": selector, "input_in_frame": bool(frame)}


def wait_for_response(page: Page, sl: StepLogger, timeout_ms: int = 25000) -> Dict[str, Any]:
    end = time.time() + timeout_ms / 1000.0
    last_len = -1
    stable_cycles = 0
    samples: List[int] = []
    while time.time() < end:
        try:
            body_text = page.locator("body").inner_text(timeout=1500)
        except Exception:
            body_text = ""
        cur_len = len(body_text.strip())
        samples.append(cur_len)
        if cur_len > 0 and cur_len == last_len:
            stable_cycles += 1
        else:
            stable_cycles = 0
            last_len = cur_len
        if cur_len > 0 and stable_cycles >= 4:
            sl.log("sparky_response_stable", text_length=cur_len, samples=samples[-8:])
            return {"stable": True, "text_length": cur_len, "samples": samples[-8:]}
        page.wait_for_timeout(750)
    sl.log("sparky_response_wait_timeout", text_length=last_len, samples=samples[-8:])
    return {"stable": False, "text_length": max(last_len, 0), "samples": samples[-8:]}


def extract_response_text(page: Page, selectors: Dict[str, List[str]]) -> Dict[str, Any]:
    for selector in selectors["response_container"]:
        try:
            locator = page.locator(selector).first
            if locator.is_visible():
                text = locator.inner_text(timeout=1000).strip()
                if text:
                    return {"selector": selector, "text": text}
        except Exception:
            continue
    try:
        return {"selector": "body", "text": page.locator("body").inner_text(timeout=1000).strip()}
    except Exception:
        return {"selector": None, "text": ""}


def extract_product_cards(page: Page, selectors: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    seen = set()
    for selector in selectors["product_cards"]:
        locator = page.locator(selector)
        try:
            count = min(locator.count(), 8)
        except Exception:
            count = 0
        for idx in range(count):
            item = locator.nth(idx)
            try:
                text = item.inner_text(timeout=500).strip()
            except Exception:
                text = ""
            try:
                href = item.get_attribute("href")
            except Exception:
                href = None
            key = (selector, href, text[:120])
            if key in seen:
                continue
            seen.add(key)
            if not text and not href:
                continue
            cards.append({
                "selector": selector,
                "index": idx,
                "text": text[:2000],
                "href": href,
            })
    return cards


def save_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_json(v) for v in value]
    return str(value)


def detect_bot_signal(page: Page) -> Optional[Dict[str, str]]:
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    for part in BOT_SIGNAL_URL_PARTS:
        if part in url:
            return {"reason": "blocked_url", "detail": url}

    try:
        title = (page.title() or "").strip()
    except Exception:
        title = ""
    title_lower = title.lower()
    for needle in BOT_SIGNAL_TEXT:
        if needle in title_lower:
            return {"reason": "blocked_title", "detail": title}

    try:
        body_text = page.locator("body").inner_text(timeout=1200).lower()
    except Exception:
        body_text = ""
    for needle in BOT_SIGNAL_TEXT:
        if needle in body_text:
            return {"reason": "blocked_body", "detail": needle}
    return None


def save_kill_switch_artifacts(page: Page, run_paths: Dict[str, Path], sl: StepLogger, signal: Dict[str, str], label: str) -> None:
    stem = f"kill_switch_{label}"
    screenshot_path = run_paths["screenshots"] / f"{stem}.png"
    dom_path = run_paths["dom"] / f"{stem}.html"
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as e:
        sl.log("kill_switch_screenshot_failed", error=str(e), label=label)
    try:
        save_text(dom_path, page.content())
    except Exception as e:
        sl.log("kill_switch_dom_save_failed", error=str(e), label=label)
    sl.log(
        "kill_switch_artifacts_saved",
        label=label,
        reason=signal.get("reason"),
        detail=signal.get("detail"),
        screenshot=str(screenshot_path),
        dom=str(dom_path),
    )


def enforce_kill_switch(page: Page, run_paths: Dict[str, Path], sl: StepLogger, label: str) -> None:
    signal = detect_bot_signal(page)
    if signal:
        save_kill_switch_artifacts(page, run_paths, sl, signal, label)
        sl.log("kill_switch_triggered", label=label, reason=signal.get("reason"), detail=signal.get("detail"))
        raise BotDetectionTriggered(signal.get("reason", "bot_detected"), signal.get("detail", ""))


def attach_probe_network(page: Page, sl: StepLogger, network_events: List[Dict[str, Any]]) -> None:
    def record(kind: str, payload: Dict[str, Any]) -> None:
        payload = {"kind": kind, "ts": time.time(), **sanitize_for_json(payload)}
        network_events.append(payload)
        if any(hint in str(payload.get("url", "")).lower() for hint in SPARKY_HINTS):
            sl.log("sparky_candidate_network", **payload)
        url = str(payload.get("url", "")).lower()
        if any(part in url for part in BOT_SIGNAL_URL_PARTS):
            sl.log("kill_switch_network_signal", kind=kind, url=payload.get("url"), status=payload.get("status"))

    def on_request(req) -> None:
        record("request", {
            "url": req.url,
            "method": req.method,
            "resource_type": req.resource_type,
            "is_navigation": req.is_navigation_request(),
        })

    def on_response(res) -> None:
        url = res.url
        entry: Dict[str, Any] = {
            "url": url,
            "status": res.status,
            "method": res.request.method,
            "resource_type": res.request.resource_type,
        }
        if any(hint in url.lower() for hint in SPARKY_HINTS):
            try:
                entry["body_preview"] = res.text()[:1500]
            except Exception:
                pass
        record("response", entry)

    page.on("request", on_request)
    page.on("response", on_response)
    sl.log("probe_network_attached")


def collect_query_artifacts(page: Page, run_paths: Dict[str, Path], query: str, query_index: int, response_meta: Dict[str, Any], selectors: Dict[str, List[str]], network_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    stem = f"q{query_index:02d}_{safe_filename(query)[:80]}"
    screenshot_path = run_paths["screenshots"] / f"{stem}.png"
    dom_path = run_paths["dom"] / f"{stem}.html"
    query_json_path = run_paths["queries"] / f"{stem}.json"

    page.screenshot(path=str(screenshot_path), full_page=True)
    save_text(dom_path, page.content())

    response = extract_response_text(page, selectors)
    product_cards = extract_product_cards(page, selectors)

    candidate_events = [
        event for event in network_events
        if any(hint in str(event.get("url", "")).lower() for hint in SPARKY_HINTS)
    ]

    artifact = {
        "query": query,
        "query_index": query_index,
        "timestamp": now_iso(),
        "response": {
            "editorial_selector": response.get("selector"),
            "editorial_text": response.get("text", "")[:12000],
            "response_complete": response_meta,
        },
        "products": product_cards,
        "artifacts": {
            "screenshot": str(screenshot_path),
            "dom": str(dom_path),
        },
        "network": {
            "candidate_event_count": len(candidate_events),
            "candidate_events": candidate_events[-25:],
        },
    }
    query_json_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    return artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 0 Sparky reconnaissance probe")
    parser.add_argument("--profile-dir", default=os.environ.get(PROFILE_ENV), help="Persistent Walmart Chrome profile")
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent), help="Base folder for Walmart_Sparky artifacts")
    parser.add_argument("--query-limit", type=int, default=12, help="Maximum number of probe queries to run")
    parser.add_argument("--manual-open-wait", type=int, default=15, help="Seconds to allow for Sparky UI to appear after Walmart homepage load")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.profile_dir:
        raise SystemExit(f"{PROFILE_ENV} or --profile-dir is required")

    base_dir = Path(args.base_dir).resolve()
    run_id = build_run_id()
    run_paths = create_run_layout(base_dir, run_id)
    sl = StepLogger(str(run_paths["run_dir"]), "sparky_probe")

    walmart_mod.CURRENT_SL = sl
    walmart_mod.RUN_ID = f"sparky-probe-{int(time.time() * 1000)}"
    _apply_debug_config(DebugConfig())

    queries = load_probe_queries()[: max(args.query_limit, 1)]
    selectors = load_selectors()
    probe_meta = {
        "run_id": run_id,
        "started_at": now_iso(),
        "profile_dir": args.profile_dir,
        "query_count": len(queries),
        "queries": queries,
        "selector_keys": list(selectors.keys()),
    }
    (run_paths["run_dir"] / "run_meta.json").write_text(json.dumps(probe_meta, indent=2), encoding="utf-8")

    browser = None
    ctx = None
    page = None
    network_events: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    kill_switch: Optional[Dict[str, str]] = None

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            with step(sl, "launch_context"):
                browser, ctx, page, _persistent = _launch(
                    p,
                    args.profile_dir,
                    headless=False,
                    proxy_config=_get_proxy_config(),
                    net_counters={"req_failed": 0, "resp_doc": 0, "route_errors": 0},
                )

            attach_probe_network(page, sl, network_events)

            with step(sl, "goto_walmart_home"):
                page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
            enforce_kill_switch(page, run_paths, sl, "after_homepage")

            opened = open_sparky(page, selectors, sl)
            if not opened:
                sl.log("sparky_open_not_found", manual_wait_seconds=args.manual_open_wait)
                page.wait_for_timeout(args.manual_open_wait * 1000)
                opened = open_sparky(page, selectors, sl)
            enforce_kill_switch(page, run_paths, sl, "after_sparky_open_attempt")

            if not opened:
                page.screenshot(path=str(run_paths["screenshots"] / "sparky_not_found.png"), full_page=True)
                save_text(run_paths["dom"] / "sparky_not_found.html", page.content())
                raise RuntimeError("Could not locate/open Sparky with current candidate selectors; inspect sparky_not_found artifacts")

            for idx, query in enumerate(queries, start=1):
                with step(sl, "probe_query", index=idx, query=query):
                    enforce_kill_switch(page, run_paths, sl, f"before_query_{idx:02d}")
                    submit_query(page, query, selectors, sl)
                    response_meta = wait_for_response(page, sl)
                    enforce_kill_switch(page, run_paths, sl, f"after_query_{idx:02d}")
                    artifact = collect_query_artifacts(page, run_paths, query, idx, response_meta, selectors, network_events)
                    results.append(artifact)
                    sl.log(
                        "probe_query_captured",
                        index=idx,
                        query=query,
                        editorial_chars=len(artifact["response"].get("editorial_text", "")),
                        product_count=len(artifact.get("products", [])),
                        candidate_network_events=artifact["network"]["candidate_event_count"],
                    )
                    page.wait_for_timeout(random.randint(3000, 6000))

            network_path = run_paths["network"] / "candidate_network_events.json"
            network_path.write_text(json.dumps(network_events, indent=2, ensure_ascii=False), encoding="utf-8")

            summary = {
                "run_id": run_id,
                "finished_at": now_iso(),
                "query_count": len(results),
                "queries_completed": len(results),
                "network_event_count": len(network_events),
                "kill_switch_triggered": False,
                "artifacts": {
                    "run_dir": str(run_paths["run_dir"]),
                    "network": str(network_path),
                },
            }
            (run_paths["run_dir"] / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            sl.log("probe_complete", **summary)
            return 0
    except BotDetectionTriggered as e:
        kill_switch = {"reason": e.reason, "detail": e.detail}
        network_path = run_paths["network"] / "candidate_network_events.json"
        network_path.write_text(json.dumps(network_events, indent=2, ensure_ascii=False), encoding="utf-8")

        summary = {
            "run_id": run_id,
            "finished_at": now_iso(),
            "query_count": len(queries),
            "queries_completed": len(results),
            "network_event_count": len(network_events),
            "kill_switch_triggered": True,
            "kill_switch": kill_switch,
            "artifacts": {
                "run_dir": str(run_paths["run_dir"]),
                "network": str(network_path),
            },
        }
        (run_paths["run_dir"] / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        sl.log("probe_aborted_by_kill_switch", **summary)
        return 2
    finally:
        try:
            if ctx:
                trace_path = run_paths["run_dir"] / "trace.zip"
                try:
                    ctx.tracing.stop(path=str(trace_path))
                    sl.log("trace_saved", path=str(trace_path))
                except Exception as e:
                    sl.log("trace_save_failed", error=str(e))
                ctx.close()
        except Exception as e:
            sl.log("context_close_failed", error=str(e))
        try:
            if browser:
                browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
