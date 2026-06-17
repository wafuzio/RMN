"""cli-web-kroger — CLI entry point."""
from __future__ import annotations

import sys

# ── Windows UTF-8 fix ──────────────────────────────────────────────────────────
for _stream in (sys.stdout, sys.stderr):
    if _stream.encoding and _stream.encoding.lower() not in ("utf-8", "utf8"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

import shlex

import click

from .commands.coupons import coupons
from .commands.products import products
from .commands.reviews import reviews
from .commands.search import search
from .utils.repl_skin import ReplSkin

_skin = ReplSkin(app="kroger", version="0.1.0")


# ── Main CLI group ─────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, help="Output as JSON.")
@click.version_option("0.1.0", prog_name="cli-web-kroger")
@click.pass_context
def cli(ctx, json_mode):
    """cli-web-kroger — Agent-native CLI for Kroger product catalog.

    Run without arguments to enter interactive REPL mode.
    Append --json to any command for machine-readable output.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode

    if ctx.invoked_subcommand is None:
        _run_repl(ctx)


cli.add_command(search)
cli.add_command(products)
cli.add_command(reviews)
cli.add_command(coupons)


# ── REPL ───────────────────────────────────────────────────────────────────────


def _print_repl_help() -> None:
    _skin.info("Available commands:")
    print()
    print("  search products <query> [OPTIONS]   Search product catalog")
    print("    --limit N           Results per page (default: 30, max: 50)")
    print("    --offset N          Pagination offset (default: 0)")
    print("    --fulfillment TYPE  PICKUP | DELIVERY | IN_STORE")
    print("    --location-id TEXT  Override default store location")
    print()
    print("  search capture <query> [OPTIONS]    Capture fully-rendered search page HTML")
    print("    --output-dir PATH   Save dir (default: ./runs/<run_id>/)")
    print("    --no-screenshot     Skip full-page PNG screenshot")
    print("    --scroll-pause N    ms to wait after each scroll (default: 2000)")
    print()
    print("  products get <upc>                  Get product details by UPC/GTIN13")
    print("    --location-id TEXT  Override default store location")
    print()
    print("  products alternatives <upc>         Better-for-you alternatives")
    print("    --limit N           Number of suggestions (default: 10)")
    print()
    print("  reviews list <upc>                  List product reviews")
    print("    --limit N           Reviews per page (default: 16, max: 50)")
    print("    --offset N          Pagination offset (default: 0)")
    print()
    print("  coupons list <upc>                  List digital coupons for product")
    print()
    print("  help                                Show this help")
    print("  exit / quit / Ctrl-D                Exit REPL")
    print()


def _run_repl(ctx: click.Context) -> None:
    _skin.print_banner()
    _print_repl_help()

    pt_session = _skin.create_prompt_session()

    while True:
        try:
            line = _skin.get_input(pt_session)
        except (EOFError, KeyboardInterrupt):
            _skin.print_goodbye()
            break

        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            _skin.print_goodbye()
            break
        if line.lower() in ("help", "?", "h"):
            _print_repl_help()
            continue

        try:
            args = shlex.split(line)
        except ValueError as exc:
            _skin.error(f"Parse error: {exc}")
            continue

        # Preserve --json flag from context
        if ctx.obj.get("json"):
            args = ["--json"] + args

        try:
            cli.main(args=args, standalone_mode=False)
        except SystemExit:
            pass
        except Exception as exc:
            if ctx.obj.get("json"):
                from .utils.helpers import print_json
                print_json({"error": True, "code": "UNKNOWN_ERROR", "message": str(exc)})
            else:
                _skin.error(str(exc))


def main():
    cli()


if __name__ == "__main__":
    main()
