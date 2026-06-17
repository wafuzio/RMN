"""Product review commands for cli-web-kroger."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ..core.client import KrogerClient
from ..utils.helpers import handle_errors, print_json

console = Console()


@click.group()
def reviews():
    """Browse Kroger product reviews and ratings."""


@reviews.command("list")
@click.argument("upc")
@click.option(
    "--limit",
    default=16,
    show_default=True,
    type=click.IntRange(1, 50),
    help="Number of reviews to return (max 50).",
)
@click.option(
    "--offset",
    default=0,
    show_default=True,
    type=int,
    help="Offset for pagination.",
)
@click.pass_context
def list_reviews(ctx, upc: str, limit: int, offset: int):
    """List reviews for a product by UPC."""
    ctx.ensure_object(dict)
    json_mode: bool = ctx.obj.get("json", False)

    with handle_errors(json_mode):
        client = KrogerClient()

        if json_mode:
            data = client.get_reviews(upc, limit=limit, offset=offset)
        else:
            with console.status(f"[bold green]Fetching reviews for {upc}…", spinner="dots"):
                data = client.get_reviews(upc, limit=limit, offset=offset)

        product_summary = data.get("product", {})
        review_list = data.get("reviews", [])

        if json_mode:
            print_json({
                "success": True,
                "data": {
                    "summary": product_summary,
                    "reviews": review_list,
                },
            })
            return

        # Header: rating summary
        avg = product_summary.get("averageRating", 0)
        total = product_summary.get("numberOfReviews", 0)
        console.print(
            f"\n[bold yellow]★ {avg:.2f} / 5.0[/bold yellow]"
            f" [dim]({total} reviews)[/dim]\n"
        )

        if not review_list:
            console.print("[yellow]No reviews found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Rating", justify="center", no_wrap=True)
        table.add_column("Author", no_wrap=True)
        table.add_column("Date", no_wrap=True)
        table.add_column("Title")

        for review in review_list:
            rating = review.get("rating", "")
            stars = f"{'★' * int(rating)}{'☆' * (5 - int(rating))}" if rating else "—"
            author = review.get("authorNickname", "—")
            raw_date = review.get("submissionDate", "")
            date = raw_date[:10] if raw_date else "—"
            title = review.get("title", "—") or "—"
            if len(title) > 40:
                title = title[:37] + "..."
            table.add_row(stars, author, date, title)

        console.print(table)
        console.print(f"\n[dim]{len(review_list)} review(s) shown (offset {offset})[/dim]\n")
