"""
rmn-mcp-server — Retail Media Network MCP server.

Single MCP endpoint covering all retailer CLIs in the monorepo.
New retailers are added by installing their CLI and adding a tool block below.

── Current retailers ────────────────────────────────────────────────────────
  walmart     cli-web-walmart   products, capture, schedule
  kroger      cli-web-kroger    search, products, coupons, reviews
  tiktokshop  cli-web-tiktokshop  search
  (albertsons — add when CLI is complete)
─────────────────────────────────────────────────────────────────────────────

── Quick start ──────────────────────────────────────────────────────────────
  # Terminal 1 — start server
  WALMART_MCP_TOKEN=your-secret python3.11 cli/mcp_server.py

  # Terminal 2 — expose via ngrok
  ngrok http 8765

  # Register in ALCHEMY
  Connection Label : RMN CLI
  URL              : https://<ngrok-id>.ngrok-free.app/sse
  Description      : Retail Media Network — Walmart, Kroger, TikTok Shop
                     product search, ad capture, and intelligence tools.
  Authentication   : Custom header  →  X-API-Key: <your-secret>
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

# ── Config ────────────────────────────────────────────────────────────────────

PORT  = int(os.environ.get("RMN_MCP_PORT", 8765))
TOKEN = os.environ.get("RMN_MCP_TOKEN", "")   # empty = no auth (dev only)

CLIS = {
    "walmart":    "cli-web-walmart",
    "kroger":     "cli-web-kroger",
    "tiktokshop": "cli-web-tiktokshop",
}

# Ensure Python's scripts dir is on PATH so CLI scripts installed by pip are
# found even when the server is launched without the full PATH configured.
import sysconfig as _sysconfig
_PY_BIN = _sysconfig.get_path("scripts")
if _PY_BIN and _PY_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _PY_BIN + os.pathsep + os.environ.get("PATH", "")
del _sysconfig

# ── Auth middleware ───────────────────────────────────────────────────────────

class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not TOKEN:
            return await call_next(request)
        provided = (
            request.headers.get("x-api-key") or
            request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        )
        if provided != TOKEN:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


# ── CLI runner ────────────────────────────────────────────────────────────────

def _run(retailer: str, args: list[str]) -> dict[str, Any]:
    cli = CLIS[retailer]
    cmd = [cli] + args + ["--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not result.stdout.strip():
        return {"error": True, "retailer": retailer, "message": result.stderr.strip() or "CLI error"}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": True, "retailer": retailer, "message": result.stdout.strip() or result.stderr.strip()}


# ── MCP server ────────────────────────────────────────────────────────────────

mcp = Server("rmn-cli")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [

        # ── WALMART ───────────────────────────────────────────────────────────

        Tool(
            name="walmart_products_search",
            description="Search Walmart products. Returns organic and sponsored listings with prices, ratings, and item IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query":        {"type": "string",  "description": "Search keyword(s)"},
                    "page":         {"type": "integer", "default": 1},
                    "limit":        {"type": "integer", "default": 20},
                    "no_sponsored": {"type": "boolean", "default": False},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="walmart_products_detail",
            description="Full product details for a Walmart item ID — price, description, reviews, specs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "Walmart item ID (e.g. 971362035)"},
                },
                "required": ["item_id"],
            },
        ),
        Tool(
            name="walmart_capture_search",
            description=(
                "Full ad intelligence capture for a Walmart search page. Scrolls to load lazy content, "
                "intercepts GraphQL, and captures organic items, sponsored ads, DSP banners, and video assets. "
                "Returns a run_id for delta comparisons."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query":          {"type": "string"},
                    "page":           {"type": "integer", "default": 1},
                    "output":         {"type": "string",  "default": "./captures"},
                    "scrolls":        {"type": "integer", "default": 3},
                    "no_videos":      {"type": "boolean", "default": False},
                    "no_images":      {"type": "boolean", "default": False},
                    "no_screenshots": {"type": "boolean", "default": False},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="walmart_capture_diff",
            description="Compare two Walmart capture runs — returns new ads, dropped ads, and unchanged count.",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_a": {"type": "string", "description": "Earlier run ID"},
                    "run_b": {"type": "string", "description": "Later run ID"},
                },
                "required": ["run_a", "run_b"],
            },
        ),
        Tool(
            name="walmart_capture_runs",
            description="List past Walmart capture runs, optionally filtered by query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="walmart_schedule_add",
            description="Add a recurring Walmart capture schedule.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query":  {"type": "string"},
                    "every":  {"type": "string", "description": "15m, 1h, 6h, 12h, 1d"},
                    "output": {"type": "string", "default": "./captures"},
                },
                "required": ["query", "every"],
            },
        ),
        Tool(
            name="walmart_schedule_list",
            description="List all Walmart capture schedules.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="walmart_schedule_remove",
            description="Remove a Walmart capture schedule by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "string"},
                },
                "required": ["schedule_id"],
            },
        ),
        Tool(
            name="walmart_schedule_run",
            description="Execute all due Walmart capture schedules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dry_run":        {"type": "boolean", "default": False},
                    "cooldown":       {"type": "integer", "default": 90},
                    "no_videos":      {"type": "boolean", "default": False},
                    "no_images":      {"type": "boolean", "default": False},
                    "no_screenshots": {"type": "boolean", "default": False},
                },
            },
        ),

        # ── KROGER ───────────────────────────────────────────────────────────

        Tool(
            name="kroger_search",
            description="Search Kroger products by keyword. Returns product listings with prices and availability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword(s)"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="kroger_products_detail",
            description="Full product details for a Kroger product ID — price, nutrition, availability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Kroger product ID"},
                },
                "required": ["product_id"],
            },
        ),
        Tool(
            name="kroger_coupons",
            description="Browse Kroger digital coupons, optionally filtered by keyword.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filter coupons by keyword"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="kroger_reviews",
            description="Browse Kroger product reviews and ratings for a product ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "limit":      {"type": "integer", "default": 10},
                },
                "required": ["product_id"],
            },
        ),

        # ── TIKTOK SHOP ───────────────────────────────────────────────────────

        Tool(
            name="tiktokshop_search",
            description="Search TikTok Shop products. Returns listings with prices, ratings, and seller info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword(s)"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        ),

        # ── Add new retailers below this line ─────────────────────────────────
        # Example when Albertsons is ready:
        #
        # Tool(
        #     name="albertsons_search",
        #     description="Search Albertsons products.",
        #     inputSchema={...},
        # ),

    ]


# ── Tool dispatch ─────────────────────────────────────────────────────────────

@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    result = _dispatch(name, arguments)
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:

    # ── Walmart ───────────────────────────────────────────────────────────────

    if name == "walmart_products_search":
        cmd = ["products", "search", args["query"]]
        if args.get("page",  1)  != 1:  cmd += ["--page",  str(args["page"])]
        if args.get("limit", 20) != 20: cmd += ["--limit", str(args["limit"])]
        if args.get("no_sponsored"):    cmd.append("--no-sponsored")
        return _run("walmart", cmd)

    if name == "walmart_products_detail":
        return _run("walmart", ["products", "detail", args["item_id"]])

    if name == "walmart_capture_search":
        cmd = ["capture", "search", args["query"]]
        if args.get("page",    1) != 1:  cmd += ["--page",    str(args["page"])]
        if args.get("scrolls", 3) != 3:  cmd += ["--scrolls", str(args["scrolls"])]
        if args.get("output", "./captures") != "./captures": cmd += ["--output", args["output"]]
        if args.get("no_videos"):      cmd.append("--no-videos")
        if args.get("no_images"):      cmd.append("--no-images")
        if args.get("no_screenshots"): cmd.append("--no-screenshots")
        return _run("walmart", cmd)

    if name == "walmart_capture_diff":
        return _run("walmart", ["capture", "diff", args["run_a"], args["run_b"]])

    if name == "walmart_capture_runs":
        cmd = ["capture", "runs"]
        if args.get("query"): cmd += ["--query", args["query"]]
        if args.get("limit", 20) != 20: cmd += ["--limit", str(args["limit"])]
        return _run("walmart", cmd)

    if name == "walmart_schedule_add":
        cmd = ["schedule", "add", args["query"], "--every", args["every"]]
        if args.get("output", "./captures") != "./captures": cmd += ["--output", args["output"]]
        return _run("walmart", cmd)

    if name == "walmart_schedule_list":
        return _run("walmart", ["schedule", "list"])

    if name == "walmart_schedule_remove":
        return _run("walmart", ["schedule", "remove", args["schedule_id"]])

    if name == "walmart_schedule_run":
        cmd = ["schedule", "run"]
        if args.get("dry_run"):  cmd.append("--dry-run")
        if args.get("cooldown", 90) != 90: cmd += ["--cooldown", str(args["cooldown"])]
        if args.get("no_videos"):      cmd.append("--no-videos")
        if args.get("no_images"):      cmd.append("--no-images")
        if args.get("no_screenshots"): cmd.append("--no-screenshots")
        return _run("walmart", cmd)

    # ── Kroger ────────────────────────────────────────────────────────────────

    if name == "kroger_search":
        cmd = ["search", args["query"]]
        if args.get("limit", 20) != 20: cmd += ["--limit", str(args["limit"])]
        return _run("kroger", cmd)

    if name == "kroger_products_detail":
        return _run("kroger", ["products", "detail", args["product_id"]])

    if name == "kroger_coupons":
        cmd = ["coupons"]
        if args.get("query"): cmd += ["--query", args["query"]]
        if args.get("limit", 20) != 20: cmd += ["--limit", str(args["limit"])]
        return _run("kroger", cmd)

    if name == "kroger_reviews":
        cmd = ["reviews", args["product_id"]]
        if args.get("limit", 10) != 10: cmd += ["--limit", str(args["limit"])]
        return _run("kroger", cmd)

    # ── TikTok Shop ───────────────────────────────────────────────────────────

    if name == "tiktokshop_search":
        cmd = ["search", args["query"]]
        if args.get("limit", 20) != 20: cmd += ["--limit", str(args["limit"])]
        return _run("tiktokshop", cmd)

    # ── Unknown ───────────────────────────────────────────────────────────────

    return {"error": True, "message": f"Unknown tool: {name}"}


# ── Starlette app ─────────────────────────────────────────────────────────────

sse_transport = SseServerTransport("/messages")


async def handle_sse(request: Request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp.run(streams[0], streams[1], mcp.create_initialization_options())


async def handle_health(request: Request):
    return JSONResponse({
        "status":    "ok",
        "server":    "rmn-cli",
        "retailers": list(CLIS.keys()),
    })


app = Starlette(
    routes=[
        Route("/health", handle_health),
        Route("/sse",    handle_sse),
        Mount("/messages", app=sse_transport.handle_post_message),
    ]
)
app.add_middleware(TokenAuthMiddleware)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    token_status = f"token={'set' if TOKEN else 'NOT SET — open access, dev only'}"
    print(f"RMN MCP server  |  port {PORT}  |  {token_status}")
    print(f"Retailers: {', '.join(CLIS.keys())}")
    print(f"SSE endpoint : http://localhost:{PORT}/sse")
    print(f"Health check : http://localhost:{PORT}/health")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
