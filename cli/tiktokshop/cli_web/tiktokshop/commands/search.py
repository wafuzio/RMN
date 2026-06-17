"""Search command group for cli-web-tiktokshop."""
from __future__ import annotations

import json

import click

from ..core.client import TiktokshopClient
from ..utils.helpers import handle_errors
from ..utils.output import print_table, print_json_output


@click.group("search")
def search():
    """Search TikTok Shop products."""


@search.command("query")
@click.argument("query")
@click.option(
    "--sort",
    type=click.Choice(["best", "price-asc", "price-desc", "newest", "best-sellers"]),
    default="best",
    show_default=True,
    help="Sort order for results.",
)
@click.option(
    "--price-range",
    type=click.Choice(["under-30", "30-40", "40-100", "over-100"]),
    default=None,
    help="Filter by price range.",
)
@click.option("--limit", default=30, show_default=True, help="Max products to return.")
@click.option("--page", default=1, show_default=True, help="Page number (30 results per page).")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def query(ctx, query, sort, price_range, limit, page, use_json):
    """Search for products by keyword.

    Examples:\n
      cli-web-tiktokshop search query proactiv\n
      cli-web-tiktokshop search query "skincare" --sort price-asc --limit 60\n
      cli-web-tiktokshop search query moisturizer --price-range under-30 --json
    """
    json_mode = use_json or ctx.obj.get("json", False)
    with handle_errors(json_mode):
        with TiktokshopClient() as client:
            result = client.search(query, sort=sort, limit=limit, page=page, price_range=price_range)
        if json_mode:
            print_json_output(result.to_dict())
        else:
            _print_products_table(result.products, result.query)
            if result.has_more:
                click.echo(f"\n  Showing {len(result.products)} results. Use --page {page+1} for more.")


@search.command("suggest")
@click.argument("query")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def suggest(ctx, query, use_json):
    """Get search suggestions for a keyword.

    Examples:\n
      cli-web-tiktokshop search suggest proactiv\n
      cli-web-tiktokshop search suggest skin --json
    """
    json_mode = use_json or ctx.obj.get("json", False)
    with handle_errors(json_mode):
        with TiktokshopClient() as client:
            suggestions = client.suggest(query)
        if json_mode:
            print_json_output({"query": query, "suggestions": suggestions})
        else:
            click.echo(f"Search suggestions for '{query}':")
            for s in suggestions[:20]:
                click.echo(f"  {s}")


def _print_products_table(products, query):
    """Print products as a human-readable table."""
    if not products:
        click.echo(f"No results found for '{query}'.")
        return

    click.echo(f"\nResults for '{query}' ({len(products)} products):\n")

    for i, p in enumerate(products, 1):
        price_str = f"{p.price_prefix} ${p.price}" if p.price_prefix else f"${p.price}"
        rating_str = f"★{p.rating:.1f}" if p.rating else "  —  "
        sold_str = _format_sold(p.sold_count)
        click.echo(f"  {i:>3}. {p.title[:60]:<60}")
        click.echo(f"       {price_str:<14} {rating_str} ({p.review_count} reviews)  {sold_str} sold")
        click.echo(f"       {p.shop_name}")
        if i < len(products):
            click.echo()


def _format_sold(count: int) -> str:
    if count >= 1_000_000:
        return f"{count/1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count/1_000:.1f}K"
    return str(count)
