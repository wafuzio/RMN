"""Capture command group — full-page ad intelligence capture."""
from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..core.capture import run_capture
from ..core.runs import RunStore, make_run_id
from ..utils.helpers import handle_errors
from ..utils.output import json_success, print_json

console = Console()


@click.group("capture")
def capture_group():
    """Full-page ad intelligence capture (organic items + all ad types + assets)."""


# ── capture search ─────────────────────────────────────────────────────────────

@capture_group.command("search")
@click.argument("query")
@click.option("--page", default=1, show_default=True, help="Results page number.")
@click.option("--output", "-o", default="./captures", show_default=True,
              help="Output directory for capture assets.")
@click.option("--no-videos", is_flag=True, help="Skip video download.")
@click.option("--no-images", is_flag=True, help="Skip creative image download.")
@click.option("--no-screenshots", is_flag=True, help="Skip banner screenshots.")
@click.option("--scrolls", default=3, show_default=True,
              help="Number of scroll passes (more = more lazy-loaded content).")
@click.option("--run-id", default=None, help="Override auto-generated run ID.")
@click.option("--json", "json_mode", is_flag=True, help="Output JSON summary.")
@click.pass_context
def capture_search(ctx, query, page, output, no_videos, no_images,
                   no_screenshots, scrolls, run_id, json_mode):
    """Capture full ad intelligence for a QUERY search page.

    Downloads all ads, banners, videos, and screenshots found on the page.

    \b
    Examples:
      cli-web-walmart capture search coffee
      cli-web-walmart capture search "dark roast" --output ./my-captures
      cli-web-walmart capture search coffee --no-videos --json
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")

    with handle_errors(json_mode):
        from urllib.parse import quote_plus
        from ..core.client import BASE_URL

        url = f"{BASE_URL}/search?q={quote_plus(query)}&page={page}"

        if not json_mode:
            console.print(
                f"\n[bold cyan]📡 Capturing:[/bold cyan] [white]{query!r}[/white] "
                f"[dim](page {page})[/dim]"
            )
            console.print(f"[dim]Output → {Path(output).resolve() / (run_id or '...')}[/dim]\n")

        store = RunStore()
        result = run_capture(
            url=url,
            query=query,
            page=page,
            output_dir=Path(output),
            download_videos=not no_videos,
            download_images=not no_images,
            screenshot_banners=not no_screenshots,
            scroll_passes=scrolls,
            run_id=run_id,
            store=store,
        )

        if json_mode:
            print(json_success(result.summary()))
            return

        _print_capture_summary(result)


# ── capture url ───────────────────────────────────────────────────────────────

@capture_group.command("url")
@click.argument("target_url")
@click.option("--label", default="", help="Human label for this capture (used as query name).")
@click.option("--output", "-o", default="./captures", show_default=True)
@click.option("--no-videos", is_flag=True)
@click.option("--no-images", is_flag=True)
@click.option("--no-screenshots", is_flag=True)
@click.option("--scrolls", default=3, show_default=True)
@click.option("--run-id", default=None)
@click.option("--json", "json_mode", is_flag=True)
@click.pass_context
def capture_url(ctx, target_url, label, output, no_videos, no_images,
                no_screenshots, scrolls, run_id, json_mode):
    """Capture any Walmart page URL directly.

    \b
    Examples:
      cli-web-walmart capture url "https://www.walmart.com/browse/food/coffee/..."
      cli-web-walmart capture url "https://www.walmart.com/ip/Some-Product/123456"
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")
    query = label or target_url

    with handle_errors(json_mode):
        if not json_mode:
            console.print(f"\n[bold cyan]📡 Capturing URL:[/bold cyan] [dim]{target_url}[/dim]\n")

        store = RunStore()
        result = run_capture(
            url=target_url,
            query=query,
            output_dir=Path(output),
            download_videos=not no_videos,
            download_images=not no_images,
            screenshot_banners=not no_screenshots,
            scroll_passes=scrolls,
            run_id=run_id,
            store=store,
        )

        if json_mode:
            print(json_success(result.summary()))
            return

        _print_capture_summary(result)


# ── capture diff ──────────────────────────────────────────────────────────────

@capture_group.command("diff")
@click.argument("run_a")
@click.argument("run_b")
@click.option("--json", "json_mode", is_flag=True)
@click.pass_context
def capture_diff(ctx, run_a, run_b, json_mode):
    """Compare two capture runs — show new and dropped ads.

    \b
    Example:
      cli-web-walmart capture diff 20260518_120000_coffee 20260518_130000_coffee
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        store = RunStore()
        delta = store.compute_delta(run_a, run_b)

        if json_mode:
            print(json_success(delta.to_dict()))
            return

        console.print(f"\n[bold]Ad Delta:[/bold] {run_a} → {run_b}")
        console.print(f"  [green]+{len(delta.new_ads)} new ads[/green]  "
                      f"[red]-{len(delta.dropped_ads)} dropped[/red]  "
                      f"[dim]{delta.unchanged} unchanged[/dim]\n")

        if delta.new_ads:
            console.print("[bold green]New ads:[/bold green]")
            for ad in delta.new_ads[:20]:
                console.print(f"  [{ad.get('ad_type', '?')}] "
                               f"{ad.get('item_id', '')} "
                               f"{ad.get('ad_uuid', '')[:12]}...")

        if delta.dropped_ads:
            console.print("\n[bold red]Dropped ads:[/bold red]")
            for ad in delta.dropped_ads[:20]:
                console.print(f"  [{ad.get('ad_type', '?')}] "
                               f"{ad.get('item_id', '')} "
                               f"{ad.get('ad_uuid', '')[:12]}...")


# ── capture runs ──────────────────────────────────────────────────────────────

@capture_group.command("runs")
@click.option("--query", default=None, help="Filter by query substring.")
@click.option("--limit", default=20, show_default=True)
@click.option("--json", "json_mode", is_flag=True)
@click.pass_context
def capture_runs(ctx, query, limit, json_mode):
    """List past capture runs."""
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        store = RunStore()
        runs = store.list_runs(query=query, limit=limit)

        if json_mode:
            print(json_success({"runs": [r.to_dict() for r in runs]}))
            return

        if not runs:
            console.print("[yellow]No runs found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Run ID", min_width=28)
        table.add_column("Query", min_width=15)
        table.add_column("Timestamp", width=22)
        table.add_column("Items", justify="right", width=7)
        table.add_column("Ads", justify="right", width=6)
        table.add_column("Banners", justify="right", width=8)
        table.add_column("Status", width=9)

        for run in runs:
            table.add_row(
                run.run_id,
                run.query[:20],
                run.timestamp[:19].replace("T", " "),
                str(run.item_count),
                str(run.ad_count),
                str(run.banner_count),
                f"[green]{run.status}[/green]" if run.status == "complete"
                else f"[red]{run.status}[/red]",
            )
        console.print(table)


# ── Rich output helper ────────────────────────────────────────────────────────

def _print_capture_summary(result) -> None:
    s = result.summary()

    console.print(f"[bold green]✓ Capture complete[/bold green]  "
                  f"[dim]run_id: {s['run_id']}[/dim]")
    console.print(f"[dim]Saved to: {result.output_dir}[/dim]\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Organic items", str(s["organic_item_count"]))
    table.add_row("In-grid sponsored", str(s["sponsored_item_count"]))
    table.add_row("Shelf/AdV3 ads", str(s["sponsored_ad_count"]))
    table.add_row("Display/DSP banners", str(s["banner_ad_count"]))
    table.add_row("Video URLs found", str(s["video_url_count"]))
    table.add_row("VAST chains resolved", str(s["vast_chain_count"]))
    console.print(table)

    if s["errors"]:
        console.print(f"\n[yellow]⚠ {len(s['errors'])} error(s):[/yellow]")
        for err in s["errors"][:5]:
            console.print(f"  [dim]{err}[/dim]")

    console.print("\n[dim]Files written:[/dim]")
    for fname in ("session.json", "organic.json", "sponsored.json",
                  "banners.json", "videos.json", "raw_interceptor.json"):
        console.print(f"  [dim]{result.output_dir}/{fname}[/dim]")
    console.print(f"  [dim]{result.output_dir}/assets/[/dim]")
