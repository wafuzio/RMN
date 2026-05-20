"""cli-web-walmart — CLI entry point."""
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

from .commands.capture import capture_group
from .commands.products import products_group
from .commands.schedule import schedule_group
from .core import client as _client
from .utils.repl_skin import ReplSkin

_skin = ReplSkin(app="walmart", version="0.1.0")


# ── Main CLI group ─────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, help="Output as JSON.")
@click.version_option("0.1.0", prog_name="cli-web-walmart")
@click.pass_context
def cli(ctx, json_mode):
    """cli-web-walmart — Search and browse Walmart products.

    Run without arguments to enter interactive REPL mode.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode

    if ctx.invoked_subcommand is None:
        _run_repl(ctx)


cli.add_command(products_group)
cli.add_command(capture_group)
cli.add_command(schedule_group)


# ── REPL ───────────────────────────────────────────────────────────────────────


def _print_repl_help() -> None:
    _skin.info("Available commands:")
    print()
    print("  products search <query>               Search products by keyword")
    print("    --page N                            Results page (default: 1)")
    print("    --limit N                           Max items to show (default: 20)")
    print("    --no-sponsored                      Exclude sponsored products")
    print("    --json                              Output JSON")
    print()
    print("  products detail <item-id>             Full product details")
    print("    --json                              Output JSON")
    print()
    print("  products browse <category>            Browse a category URL path")
    print("    --page N                            Results page (default: 1)")
    print("    --limit N                           Max items to show (default: 20)")
    print("    --json                              Output JSON")
    print()
    print("  capture search <query>                Full ad intelligence capture for search")
    print("    --page N                            Results page (default: 1)")
    print("    --output DIR                        Output directory (default: ./captures)")
    print("    --no-videos                         Skip video download")
    print("    --no-images                         Skip creative image download")
    print("    --no-screenshots                    Skip banner screenshots")
    print("    --scrolls N                         Scroll passes (default: 3)")
    print("    --json                              Output JSON summary")
    print()
    print("  capture url <url>                     Capture any Walmart page URL")
    print("  capture diff <run_a> <run_b>          Compare two capture runs (ad delta)")
    print("  capture runs                          List past captures")
    print()
    print("  schedule add <query> --every INTERVAL Add recurring capture schedule")
    print("    --every 15m|1h|6h|12h|1d            Capture interval")
    print("    --output DIR                        Output directory")
    print("  schedule list                         List all schedules")
    print("  schedule remove <id>                  Remove a schedule")
    print("  schedule run                          Execute all due schedules")
    print("    --cooldown N                        Seconds between captures (default: 90)")
    print()
    print("  help                                  Show this help")
    print("  exit / quit / Ctrl-D                  Exit REPL")
    print()
    print("Examples:")
    print("  products search coffee")
    print("  products search \"dark roast\" --limit 10")
    print("  products detail 10534406")
    print("  products browse food/coffee/976759_976787_1001080")
    print("  capture search coffee --scrolls 5")
    print("  capture search coffee --no-videos --json")
    print("  schedule add coffee --every 6h")
    print("  schedule run")
    print()


def _run_repl(ctx: click.Context) -> None:
    _skin.print_banner()
    _print_repl_help()

    pt_session = _skin.create_prompt_session()

    while True:
        try:
            line = _skin.get_input(pt_session)
        except (EOFError, KeyboardInterrupt):
            _client.close_context()
            _skin.print_goodbye()
            break

        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            _client.close_context()
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
            _skin.error(str(exc))


def main():
    try:
        cli()
    finally:
        _client.close_context()


if __name__ == "__main__":
    main()
