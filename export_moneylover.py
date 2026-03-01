#!/usr/bin/env python
"""CLI orchestration for exporting Money Lover transactions."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moneylover_client import MoneyLoverClient, TokenExpiredError, extract_tokens, resolve_wallet_id


TOKEN_ENV_KEY = "MONEYLOVER_TOKEN"

console = Console()


def _parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Use YYYY-MM-DD or MM/DD/YYYY.")


def _resolve_token(args: argparse.Namespace) -> str:
    token_input = args.token or os.environ.get(TOKEN_ENV_KEY)
    token, _ = extract_tokens(token_input or "")

    if token:
        return token

    raise RuntimeError(
        f"No token provided. Use --token or {TOKEN_ENV_KEY}."
    )


def _render_wallets_table(wallets: list[dict[str, Any]]) -> None:
    table = Table(title="Money Lover Wallets")
    table.add_column("Wallet ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Type", style="magenta")
    for wallet in wallets:
        table.add_row(
            str(wallet.get("_id", "")),
            str(wallet.get("name", "")),
            str(wallet.get("type", "")),
        )
    console.print(table)


def _count_transactions(txn_data: Any) -> int:
    if isinstance(txn_data, dict):
        if isinstance(txn_data.get("transactions"), list):
            return len(txn_data["transactions"])
        if isinstance(txn_data.get("data"), list):
            return len(txn_data["data"])
    if isinstance(txn_data, list):
        return len(txn_data)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Money Lover transactions to JSON")
    parser.add_argument("--token", help="AuthJWT token, or full redirect URL containing access_token")
    parser.add_argument("--start-date", type=_parse_date, help="Start date (YYYY-MM-DD or MM/DD/YYYY)")
    parser.add_argument("--end-date", type=_parse_date, help="End date (YYYY-MM-DD or MM/DD/YYYY)")
    parser.add_argument("--wallet-name", help="Wallet name to filter transactions")
    parser.add_argument("--wallet-id", help="Wallet ID to filter transactions")
    parser.add_argument("--output", default="transactions.json", help="Output JSON file path")
    parser.add_argument("--list-wallets", action="store_true", help="Print wallets and exit")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    console.print(Panel("Export Money Lover transactions to JSON", title="Money Lover Export", border_style="blue"))

    start_date = args.start_date or date(1900, 1, 1)
    end_date = args.end_date or datetime.now(timezone.utc).date()
    if start_date > end_date:
        console.print("[red]--start-date must be on or before --end-date[/red]")
        return 2

    try:
        token = _resolve_token(args)
        client = MoneyLoverClient(token)

        wallets: list[dict[str, Any]] = []
        if args.list_wallets or args.wallet_name:
            with console.status("Loading wallets..."):
                wallets = client.get_wallets()

        if args.list_wallets:
            _render_wallets_table(wallets)
            return 0

        wallet_id = args.wallet_id or "all"
        if args.wallet_name:
            wallet_id = resolve_wallet_id(wallets, args.wallet_name, args.wallet_id)

        with console.status("Fetching transactions..."):
            txn_data = client.get_transactions(start_date=start_date, end_date=end_date, wallet_id=wallet_id)

        output_payload = {
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": {
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
            },
            "wallet_id": wallet_id,
            "data": txn_data,
        }

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=True), encoding="utf-8")

        console.print(
            Panel(
                f"[green]Export complete[/green]\n"
                f"Output: [bold]{output_path}[/bold]\n"
                f"Wallet ID: [cyan]{wallet_id}[/cyan]\n"
                f"Range: [magenta]{start_date.strftime('%Y-%m-%d')}[/magenta] to [magenta]{end_date.strftime('%Y-%m-%d')}[/magenta]\n"
                f"Transactions: [bold]{_count_transactions(txn_data)}[/bold]",
                title="Success",
                border_style="green",
            )
        )
        return 0
    except TokenExpiredError as exc:
        console.print(f"[red]Failed to export transactions:[/red] {exc}")
        console.print("Please provide a fresh token via --token or MONEYLOVER_TOKEN.")
        return 1
    except Exception as exc:
        console.print(f"[red]Failed to export transactions:[/red] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
