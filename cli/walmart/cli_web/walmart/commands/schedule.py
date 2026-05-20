"""Schedule command group — recurring ad capture scheduling."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..core.runs import RunStore, ScheduleRecord, _human_interval, _iso_from_ts
from ..utils.helpers import handle_errors
from ..utils.output import json_success

console = Console()

_INTERVAL_SHORTCUTS = {
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "daily": 86400,
    "hourly": 3600,
}


def _parse_interval(value: str) -> int:
    """Parse interval string to seconds. Accepts: 30m, 1h, 2h, 1d, or raw seconds."""
    v = value.strip().lower()
    if v in _INTERVAL_SHORTCUTS:
        return _INTERVAL_SHORTCUTS[v]
    # Try numeric suffixes
    import re
    m = re.match(r"^(\d+)(s|m|h|d)?$", v)
    if m:
        n, unit = int(m.group(1)), (m.group(2) or "s")
        return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    raise click.BadParameter(
        f"Invalid interval {value!r}. Use: 15m, 1h, 6h, 1d, or raw seconds."
    )


@click.group("schedule")
def schedule_group():
    """Manage recurring ad capture schedules."""


@schedule_group.command("add")
@click.argument("query")
@click.option("--every", required=True, metavar="INTERVAL",
              help="Capture interval: 15m, 1h, 6h, 1d, etc.")
@click.option("--output", "-o", default="./captures", show_default=True,
              help="Output directory for capture assets.")
@click.option("--id", "schedule_id", default=None,
              help="Override auto-generated schedule ID.")
@click.option("--json", "json_mode", is_flag=True)
@click.pass_context
def schedule_add(ctx, query, every, output, schedule_id, json_mode):
    """Add a recurring capture schedule for QUERY.

    \b
    Examples:
      cli-web-walmart schedule add coffee --every 1h
      cli-web-walmart schedule add "dark roast" --every 6h --output ./my-captures
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        interval_sec = _parse_interval(every)
        sid = schedule_id or f"sched_{query[:12].replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        next_run = _iso_from_ts(__import__("time").time())  # run immediately on first `run`

        sched = ScheduleRecord(
            schedule_id=sid,
            query=query,
            interval_sec=interval_sec,
            output_dir=str(Path(output).resolve()),
            next_run=next_run,
        )
        RunStore().save_schedule(sched)

        if json_mode:
            print(json_success(sched.to_dict()))
            return

        console.print(
            f"[bold green]✓ Schedule added[/bold green]  [dim]{sid}[/dim]\n"
            f"  Query:    [cyan]{query}[/cyan]\n"
            f"  Interval: every {_human_interval(interval_sec)}\n"
            f"  Output:   {Path(output).resolve()}\n"
            f"\nRun [bold]cli-web-walmart schedule run[/bold] to execute due captures."
        )


@schedule_group.command("list")
@click.option("--json", "json_mode", is_flag=True)
@click.pass_context
def schedule_list(ctx, json_mode):
    """List all schedules."""
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        scheds = RunStore().list_schedules()

        if json_mode:
            print(json_success({"schedules": [s.to_dict() for s in scheds]}))
            return

        if not scheds:
            console.print("[yellow]No schedules configured.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold blue")
        table.add_column("ID", min_width=20)
        table.add_column("Query", min_width=15)
        table.add_column("Every", width=8)
        table.add_column("Next Run", width=20)
        table.add_column("Last Run", width=20)
        table.add_column("On", width=4)

        for s in scheds:
            table.add_row(
                s.schedule_id[:24],
                s.query[:18],
                _human_interval(s.interval_sec),
                s.next_run[:19].replace("T", " ") if s.next_run else "—",
                s.last_run[:19].replace("T", " ") if s.last_run else "never",
                "[green]✓[/green]" if s.enabled else "[red]✗[/red]",
            )
        console.print(table)


@schedule_group.command("remove")
@click.argument("schedule_id")
@click.option("--json", "json_mode", is_flag=True)
@click.pass_context
def schedule_remove(ctx, schedule_id, json_mode):
    """Remove a schedule by ID."""
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        ok = RunStore().delete_schedule(schedule_id)
        if json_mode:
            print(json_success({"deleted": ok, "schedule_id": schedule_id}))
            return
        if ok:
            console.print(f"[green]✓ Removed schedule {schedule_id}[/green]")
        else:
            console.print(f"[yellow]Schedule not found: {schedule_id}[/yellow]")


@schedule_group.command("run")
@click.option("--dry-run", is_flag=True, help="Show what would run without executing.")
@click.option("--no-videos", is_flag=True)
@click.option("--no-images", is_flag=True)
@click.option("--no-screenshots", is_flag=True)
@click.option("--cooldown", default=90, show_default=True, metavar="SECONDS",
              help="Seconds to wait between captures (prevents velocity-based bot detection).")
@click.option("--json", "json_mode", is_flag=True)
@click.pass_context
def schedule_run(ctx, dry_run, no_videos, no_images, no_screenshots, cooldown, json_mode):
    """Execute all capture schedules that are currently due.

    Run this via cron or manually. Exits after processing all due schedules.

    Walmart's bot detection scores cumulative risk per session — running captures
    back-to-back triggers challenges after 3-4 queries. The --cooldown gap (default
    90s) keeps the session risk score low across multi-schedule runs.

    \b
    Cron example (every 15 minutes):
      */15 * * * * cli-web-walmart schedule run --no-screenshots
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        from urllib.parse import quote_plus
        from ..core.capture import run_capture
        from ..core.client import BASE_URL

        store = RunStore()
        due = store.get_due_schedules()

        if not due:
            if json_mode:
                print(json_success({"ran": 0, "message": "No schedules due"}))
            else:
                console.print("[dim]No schedules due.[/dim]")
            return

        results = []
        for i, sched in enumerate(due):
            # Cooldown between captures (not before the first one)
            if i > 0 and not dry_run and cooldown > 0:
                if not json_mode:
                    console.print(
                        f"\n[dim]⏳ Cooldown {cooldown}s before next capture "
                        f"(use --cooldown 0 to skip)...[/dim]"
                    )
                import time as _time
                _time.sleep(cooldown)

            if dry_run:
                if not json_mode:
                    console.print(f"[dim][dry-run] Would capture: {sched.query!r}[/dim]")
                results.append({"schedule_id": sched.schedule_id, "query": sched.query,
                                 "dry_run": True})
                continue

            if not json_mode:
                console.print(f"\n[cyan]▶ Running:[/cyan] {sched.query!r}")

            url = f"{BASE_URL}/search?q={quote_plus(sched.query)}&page=1"
            try:
                result = run_capture(
                    url=url,
                    query=sched.query,
                    output_dir=Path(sched.output_dir),
                    download_videos=not no_videos,
                    download_images=not no_images,
                    screenshot_banners=not no_screenshots,
                    store=store,
                )
                store.update_schedule_after_run(sched.schedule_id)
                results.append(result.summary())

                if not json_mode:
                    s = result.summary()
                    console.print(
                        f"  [green]✓[/green] {s['organic_item_count']} items, "
                        f"{s['ad_count']} ads, {s['banner_count']} banners  "
                        f"[dim]{result.run_id}[/dim]"
                    )
            except Exception as e:
                results.append({
                    "schedule_id": sched.schedule_id,
                    "query": sched.query,
                    "error": str(e),
                })
                if not json_mode:
                    console.print(f"  [red]✗ Error: {e}[/red]")

        if json_mode:
            print(json_success({"ran": len(due), "results": results}))
