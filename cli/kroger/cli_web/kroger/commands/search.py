"""Search commands for cli-web-kroger."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ..core.client import KrogerClient
from ..utils.helpers import handle_errors, print_json

console = Console()


@click.group()
def search():
    """Search Kroger products."""


@search.command("products")
@click.argument("query")
@click.option("--limit", default=30, show_default=True, type=click.IntRange(1, 50),
              help="Number of results (max 50).")
@click.option("--offset", default=0, show_default=True, type=int,
              help="Pagination offset.")
@click.option("--fulfillment", type=click.Choice(["PICKUP", "DELIVERY", "IN_STORE"],
              case_sensitive=True), default=None,
              help="Filter by fulfillment method.")
@click.option("--location-id", default=None,
              help="Override the default store location ID.")
@click.pass_context
def products(ctx, query: str, limit: int, offset: int, fulfillment: str | None,
             location_id: str | None):
    """Search for products matching QUERY."""
    ctx.ensure_object(dict)
    json_mode: bool = ctx.obj.get("json", False)

    with handle_errors(json_mode):
        client = KrogerClient(location_id=location_id or "70100070")

        if json_mode:
            results = client.search_products(
                query,
                location_id=location_id,
                fulfillment=fulfillment,
                limit=limit,
                offset=offset,
            )
        else:
            with console.status(f"[bold green]Searching for '{query}'…", spinner="dots"):
                results = client.search_products(
                    query,
                    location_id=location_id,
                    fulfillment=fulfillment,
                    limit=limit,
                    offset=offset,
                )

        if json_mode:
            print_json({"success": True, "data": results, "total": len(results)})
            return

        if not results:
            console.print(f"[yellow]No products found for '{query}'.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Rank", justify="right", style="dim", no_wrap=True)
        table.add_column("UPC", no_wrap=True)
        table.add_column("Brand")
        table.add_column("Description")

        for item in results:
            rank = str(item.get("searchEngineRank", ""))
            upc = item.get("upc", "")
            brand = item.get("brandName", "")
            description = item.get("description", "")
            table.add_row(rank, upc, brand, description)

        console.print(table)
        console.print(f"\n[dim]{len(results)} result(s) returned[/dim]")


@search.command("capture")
@click.argument("query")
@click.option("--output-dir", default=None,
              help="Directory to save HTML + screenshot (default: ./runs/<run_id>/).")
@click.option("--no-screenshot", is_flag=True, default=False,
              help="Skip full-page screenshot (faster).")
@click.option("--scroll-pause", default=2000, show_default=True, type=int,
              help="Milliseconds to wait after each scroll burst (increase on slow connections).")
@click.pass_context
def capture(ctx, query: str, output_dir: str | None, no_screenshot: bool, scroll_pause: int):
    """Capture fully-rendered HTML of a search results page.

    Navigates to kroger.com/search, scrolls to trigger lazy-loaded carousels
    and sponsored tiles, dismisses the 'Improving your experience' modal, then
    saves the clean HTML and an optional full-page screenshot.

    Saved artifacts:\n
      runs/<run_id>/search_results_<query>_<run_id>.html\n
      runs/<run_id>/screenshot_<query>_<run_id>.png
    """
    ctx.ensure_object(dict)
    json_mode: bool = ctx.obj.get("json", False)

    with handle_errors(json_mode):
        client = KrogerClient()

        if not json_mode:
            console.print(
                f"[bold green]Capturing HTML for '{query}'…[/bold green] "
                f"[dim](scroll + lazy-load, this may take 20-40 s)[/dim]"
            )

        result = client.capture_search_html(
            query,
            output_dir=output_dir,
            scroll_pause_ms=scroll_pause,
            screenshot=not no_screenshot,
        )

        if json_mode:
            print_json({
                "success": True,
                "run_id": result["run_id"],
                "query": result["query"],
                "html_path": result["html_path"],
                "screenshot_path": result["screenshot_path"],
                "html_size": len(result["html"]),
            })
            return

        console.print(f"\n[bold green]✓ Capture complete[/bold green]  run_id=[cyan]{result['run_id']}[/cyan]")
        console.print(f"  [dim]HTML[/dim]        {result['html_path']}")
        if result["screenshot_path"]:
            console.print(f"  [dim]Screenshot[/dim]  {result['screenshot_path']}")
        console.print(f"  [dim]HTML size[/dim]   {len(result['html']):,} bytes")
