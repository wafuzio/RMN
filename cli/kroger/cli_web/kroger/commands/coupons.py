"""Digital coupon commands for cli-web-kroger."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ..core.client import KrogerClient
from ..utils.helpers import handle_errors, print_json

console = Console()


@click.group()
def coupons():
    """Browse Kroger digital coupons."""


@coupons.command("list")
@click.argument("upc")
@click.pass_context
def list_coupons(ctx, upc: str):
    """List digital coupons available for a product by UPC."""
    ctx.ensure_object(dict)
    json_mode: bool = ctx.obj.get("json", False)

    with handle_errors(json_mode):
        client = KrogerClient()

        if json_mode:
            coupon_list = client.get_coupons(upc)
        else:
            with console.status(f"[bold green]Fetching coupons for {upc}…", spinner="dots"):
                coupon_list = client.get_coupons(upc)

        if json_mode:
            print_json({
                "success": True,
                "data": coupon_list,
                "total": len(coupon_list),
            })
            return

        if not coupon_list:
            console.print(f"[yellow]No digital coupons available for {upc}[/yellow]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Offer ID", no_wrap=True)
        table.add_column("Description/Headline")
        table.add_column("Value", justify="right", no_wrap=True)
        table.add_column("Expires", no_wrap=True)

        for coupon in coupon_list:
            offer_id = str(coupon.get("offerId", "—") or "—")

            description = coupon.get("description") or coupon.get("headline") or "—"
            if len(description) > 50:
                description = description[:47] + "..."

            raw_value = coupon.get("value")
            if raw_value is not None:
                value = f"${raw_value}" if isinstance(raw_value, (int, float)) else str(raw_value)
            else:
                value = "—"

            raw_expiry = coupon.get("expirationDate", "")
            expires = raw_expiry[:10] if raw_expiry else "—"

            table.add_row(offer_id, description, value, expires)

        console.print(table)
        console.print(f"\n[dim]{len(coupon_list)} coupon(s) available[/dim]\n")
