"""Products command group — search, detail, browse."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ..core import client
from ..core.exceptions import WalmartError
from ..utils.helpers import handle_errors
from ..utils.output import print_json, json_success

console = Console()


@click.group("products")
def products_group():
    """Search, browse, and inspect Walmart products."""


@products_group.command("search")
@click.argument("query")
@click.option("--page", default=1, show_default=True, help="Results page number (1-based).")
@click.option("--limit", default=20, show_default=True, help="Max items to display (up to 60 per page).")
@click.option("--no-sponsored", is_flag=True, help="Exclude sponsored products.")
@click.option("--json", "json_mode", is_flag=True, help="Output raw JSON.")
@click.pass_context
def search_cmd(ctx, query, page, limit, no_sponsored, json_mode):
    """Search for products by QUERY.

    Examples:

    \b
      cli-web-walmart products search coffee
      cli-web-walmart products search "dark roast" --limit 10
      cli-web-walmart products search espresso --page 2 --json
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        results = client.search(query, page=page)
        items = results.items
        if no_sponsored:
            items = [i for i in items if not i.is_sponsored]
        items = items[:limit]

        if json_mode:
            data = results.to_dict()
            data["items"] = [i.to_dict() for i in items]
            data["item_count"] = len(items)  # update after --limit slicing
            data["has_more"] = results.total_count > (page - 1) * len(results.items) + len(items)
            print(json_success(data))
            return

        console.print(
            f"[bold]Walmart Search:[/bold] [cyan]{query!r}[/cyan]  "
            f"[dim]({results.total_count:,} total, page {page})[/dim]"
        )
        if not items:
            console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold blue")
        table.add_column("ID", style="dim", no_wrap=True, width=12)
        table.add_column("Name", min_width=35)
        table.add_column("Brand", min_width=12)
        table.add_column("Price", justify="right", width=10)
        table.add_column("Rating", justify="right", width=8)
        table.add_column("Reviews", justify="right", width=8)
        table.add_column("Avail", width=9)

        for item in items:
            sponsored = " [dim][S][/dim]" if item.is_sponsored else ""
            table.add_row(
                item.item_id,
                item.name[:55] + ("…" if len(item.name) > 55 else "") + sponsored,
                item.brand[:15] if item.brand else "—",
                item.price.line_price or "—",
                str(item.rating) if item.rating is not None else "—",
                f"{item.num_reviews:,}" if item.num_reviews else "—",
                item.availability[:8] if item.availability else "—",
            )

        console.print(table)
        console.print(
            f"[dim]Showing {len(items)} of {results.total_count:,} results. "
            f"Use --page N for more.[/dim]"
        )


@products_group.command("detail")
@click.argument("item_id")
@click.option("--json", "json_mode", is_flag=True, help="Output raw JSON.")
@click.pass_context
def detail_cmd(ctx, item_id, json_mode):
    """Get full product details for ITEM_ID.

    ITEM_ID is the Walmart usItemId (numeric), visible in search results.

    Examples:

    \b
      cli-web-walmart products detail 10534406
      cli-web-walmart products detail 3197101168 --json
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        product = client.detail(item_id)

        if json_mode:
            print(json_success(product.to_dict()))
            return

        console.print(f"\n[bold]{product.name}[/bold]")
        console.print(f"[dim]ID: {product.item_id}[/dim]")
        if product.brand:
            console.print(f"Brand: [cyan]{product.brand}[/cyan]")

        # Price block
        price_line = product.price.line_price or "Price not available"
        if product.price.was_price:
            console.print(f"Price: [bold green]{price_line}[/bold green]  "
                          f"[dim]was {product.price.was_price}[/dim]  "
                          f"[yellow]Save {product.price.savings}[/yellow]")
        else:
            console.print(f"Price: [bold green]{price_line}[/bold green]", end="")
            if product.price.unit_price:
                console.print(f"  [dim]({product.price.unit_price})[/dim]")
            else:
                console.print()

        if product.rating is not None:
            stars = "★" * int(product.rating) + "☆" * (5 - int(product.rating))
            console.print(f"Rating: {stars} {product.rating}/5 "
                          f"({product.num_reviews:,} reviews)" if product.num_reviews
                          else f"Rating: {product.rating}/5")

        console.print(f"Seller: {product.seller}")

        if product.short_description:
            console.print(f"\n[bold]Description:[/bold]")
            console.print(product.short_description[:600])

        if product.specifications:
            console.print(f"\n[bold]Specifications:[/bold]")
            spec_table = Table(show_header=False, box=None, padding=(0, 2))
            spec_table.add_column("Spec", style="dim", width=22)
            spec_table.add_column("Value")
            for spec in product.specifications[:15]:
                spec_table.add_row(spec.get("name", ""), spec.get("value", ""))
            console.print(spec_table)

        url = product.url if product.url.startswith("http") else f"https://www.walmart.com{product.url}"
        console.print(f"\n[dim]{url}[/dim]")


@products_group.command("browse")
@click.argument("category")
@click.option("--page", default=1, show_default=True, help="Results page number.")
@click.option("--limit", default=20, show_default=True, help="Max items to display.")
@click.option("--json", "json_mode", is_flag=True, help="Output raw JSON.")
@click.pass_context
def browse_cmd(ctx, category, page, limit, json_mode):
    """Browse a Walmart category by its URL path.

    CATEGORY is the path after walmart.com/browse/ in the URL.

    Examples:

    \b
      cli-web-walmart products browse food/coffee/976759_976787_1001080
      cli-web-walmart products browse electronics --page 2
    """
    json_mode = json_mode or (ctx.obj or {}).get("json")
    with handle_errors(json_mode):
        results = client.browse(category, page=page)
        items = results.items[:limit]

        if json_mode:
            data = results.to_dict()
            data["items"] = [i.to_dict() for i in items]
            data["item_count"] = len(items)  # update after --limit slicing
            data["has_more"] = results.total_count > (page - 1) * len(results.items) + len(items)
            print(json_success(data))
            return

        console.print(
            f"[bold]Category:[/bold] [cyan]{category}[/cyan]  "
            f"[dim]({results.total_count:,} products, page {page})[/dim]"
        )
        if not items:
            console.print("[yellow]No products found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold blue")
        table.add_column("ID", style="dim", no_wrap=True, width=12)
        table.add_column("Name", min_width=35)
        table.add_column("Brand", min_width=12)
        table.add_column("Price", justify="right", width=10)
        table.add_column("Rating", justify="right", width=8)

        for item in items:
            table.add_row(
                item.item_id,
                item.name[:55] + ("…" if len(item.name) > 55 else ""),
                item.brand[:15] if item.brand else "—",
                item.price.line_price or "—",
                str(item.rating) if item.rating is not None else "—",
            )

        console.print(table)
