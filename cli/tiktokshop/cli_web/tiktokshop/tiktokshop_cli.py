"""cli-web-tiktokshop — CLI entry point."""
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

from .commands.search import search
from .utils.repl_skin import ReplSkin

_skin = ReplSkin(app="tiktokshop", version="0.1.0")
_skin.display_name = "TikTok Shop"


# ── Main CLI group ─────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, help="Output as JSON.")
@click.version_option("0.1.0", prog_name="cli-web-tiktokshop")
@click.pass_context
def cli(ctx, json_mode):
    """cli-web-tiktokshop — Search TikTok Shop products from the command line.

    Run without arguments to enter interactive REPL mode.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode

    if ctx.invoked_subcommand is None:
        _run_repl(ctx)


# ── Register commands ─────────────────────────────────────────────────────────
cli.add_command(search)


# ── REPL ───────────────────────────────────────────────────────────────────────


def _print_repl_help() -> None:
    _skin.info("Available commands:")
    print()
    print("  search query <keyword>                Search for products")
    print("    --sort [best|price-asc|price-desc|newest|best-sellers]")
    print("    --price-range [under-30|30-40|40-100|over-100]")
    print("    --limit N                           Max results (default 30)")
    print("    --page N                            Page number (default 1)")
    print("    --json                              Output as JSON")
    print()
    print("  search suggest <keyword>              Get search suggestions")
    print("    --json                              Output as JSON")
    print()
    print("  help                                  Show this help")
    print("  exit / quit / Ctrl-D                  Exit REPL")
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
            _skin.error(str(exc))


def main():
    cli()


if __name__ == "__main__":
    main()
