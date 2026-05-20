"""Product detail commands for cli-web-kroger."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ..core.client import KrogerClient
from ..utils.helpers import handle_errors, print_json

console = Console()


@click.group()
def products():
    """Look up Kroger product details and recommendations."""


@products.command("get")
@click.argument("upc")
@click.option("--location-id", default=None, help="Override the default store location ID.")
@click.pass_context
def get(ctx, upc: str, location_id: str | None):
    """Get full product detail for a UPC/GTIN13."""
    ctx.ensure_object(dict)
    json_mode: bool = ctx.obj.get("json", False)

    with handle_errors(json_mode):
        client = KrogerClient(location_id=location_id or "70100070")

        if json_mode:
            product = client.get_product(upc, location_id=location_id)
        else:
            with console.status(f"[bold green]Fetching product {upc}…", spinner="dots"):
                product = client.get_product(upc, location_id=location_id)

        if json_mode:
            print_json({"success": True, "data": product})
            return

        # Extract display fields
        item = product.get("item", {})
        name = item.get("description", "—")
        brand = (item.get("brand") or {}).get("name", "—")
        size = item.get("customerFacingSize", "—")

        price_info = product.get("price", {})
        store_prices = price_info.get("storePrices", {})
        regular = store_prices.get("regular", {})
        price = regular.get("defaultDescription", "—")

        inventory = product.get("inventory", {})
        locations = inventory.get("locations", [])
        stock_level = locations[0].get("stockLevel", "—") if locations else "—"

        categories = item.get("categories", [])
        categories_str = ", ".join(c.get("name", "") for c in categories) if categories else "—"

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="bold cyan", no_wrap=True)
        table.add_column("Value")

        table.add_row("Name", name)
        table.add_row("Brand", brand)
        table.add_row("Size", size)
        table.add_row("Price", price)
        table.add_row("Stock Level", stock_level)
        table.add_row("Categories", categories_str)

        console.print(table)


@products.command("alternatives")
@click.argument("upc")
@click.option("--limit", default=10, show_default=True, type=click.IntRange(1, 50),
              help="Number of recommendations to return.")
@click.pass_context
def alternatives(ctx, upc: str, limit: int):
    """Get better-for-you recommendations for a UPC/GTIN13."""
    ctx.ensure_object(dict)
    json_mode: bool = ctx.obj.get("json", False)

    with handle_errors(json_mode):
        client = KrogerClient(location_id="70100070")

        if json_mode:
            recs = client.get_recommendations(upc, limit=limit)
        else:
            with console.status(f"[bold green]Fetching alternatives for {upc}…", spinner="dots"):
                recs = client.get_recommendations(upc, limit=limit)

        if json_mode:
            print_json({"success": True, "data": recs, "total": len(recs)})
            return

        if not recs:
            console.print("[yellow]No alternatives found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Rank", justify="right", style="dim", no_wrap=True)
        table.add_column("UPC", no_wrap=True)
        table.add_column("Brand")
        table.add_column("Description")

        for idx, item in enumerate(recs, start=1):
            rank = str(idx)
            item_upc = item.get("upc", "")
            brand = item.get("brandName", "")
            description = item.get("description", "")
            table.add_row(rank, item_upc, brand, description)

        console.print(table)
        console.print(f"\n[dim]{len(recs)} alternative(s) returned[/dim]")
