#!/usr/bin/env python
"""CLI orchestration for exporting Money Lover transactions."""

from __future__ import annotations

import argparse
import csv
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


def _extract_transactions(txn_data: Any) -> list[dict[str, Any]]:
    if isinstance(txn_data, dict):
        if isinstance(txn_data.get("transactions"), list):
            return [t for t in txn_data["transactions"] if isinstance(t, dict)]
        if isinstance(txn_data.get("data"), list):
            return [t for t in txn_data["data"] if isinstance(t, dict)]
    if isinstance(txn_data, list):
        return [t for t in txn_data if isinstance(t, dict)]
    return []


def _count_transactions(txn_data: Any) -> int:
    return len(_extract_transactions(txn_data))


def _csv_cell(value: Any) -> str:
    """Convert nested Money Lover values into a single CSV cell.

    For common nested objects (category, campaign, wallet, ...) we prefer `.name`.
    """

    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        return str(value)

    if isinstance(value, dict):
        # Money Lover embeds many objects like {"_id": "...", "name": "Food"}
        if "name" in value and value.get("name") is not None:
            return str(value.get("name"))
        if "title" in value and value.get("title") is not None:
            return str(value.get("title"))
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    if isinstance(value, list):
        # Lists are uncommon in txns, but if they are list-of-named-objects,
        # join them; otherwise, JSON-stringify.
        if all(isinstance(item, dict) and "name" in item for item in value):
            return ", ".join(str(item.get("name")) for item in value if item.get("name") is not None)
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def _write_csv(path: Path, txn_data: Any) -> int:
    transactions = _extract_transactions(txn_data)
    if not transactions:
        path.write_text("", encoding="utf-8")
        return 0

    # Union of keys across all transactions.
    keys: set[str] = set()
    for txn in transactions:
        keys.update(str(k) for k in txn.keys())

    preferred = [
        "_id",
        "displayDate",
        "date",
        "amount",
        "note",
        "category",
        "campaign",
        "wallet",
        "event",
        "type",
    ]
    fieldnames = [k for k in preferred if k in keys] + sorted(k for k in keys if k not in preferred)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for txn in transactions:
            writer.writerow({k: _csv_cell(txn.get(k)) for k in fieldnames})

    return len(transactions)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Money Lover transactions to JSON or CSV")
    parser.add_argument("--token", help="AuthJWT token, or full redirect URL containing access_token")
    parser.add_argument("--start-date", type=_parse_date, help="Start date (YYYY-MM-DD or MM/DD/YYYY)")
    parser.add_argument("--end-date", type=_parse_date, help="End date (YYYY-MM-DD or MM/DD/YYYY)")
    parser.add_argument("--wallet-name", help="Wallet name to filter transactions")
    parser.add_argument("--wallet-id", help="Wallet ID to filter transactions")
    parser.add_argument(
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output",
        help="Output file path. Defaults to transactions.json (json) or transactions.csv (csv)",
    )
    parser.add_argument("--list-wallets", action="store_true", help="Print wallets and exit")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    console.print(
        Panel(
            f"Export Money Lover transactions to {args.format.upper()}",
            title="Money Lover Export",
            border_style="blue",
        )
    )

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

        default_name = "transactions.json" if args.format == "json" else "transactions.csv"
        output_path = Path(args.output or default_name)

        if args.format == "json":
            output_payload = {
                "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "date_range": {
                    "start": start_date.strftime("%Y-%m-%d"),
                    "end": end_date.strftime("%Y-%m-%d"),
                },
                "wallet_id": wallet_id,
                "data": txn_data,
            }

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(output_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            _write_csv(output_path, txn_data)

        console.print(
            Panel(
                f"[green]Export complete[/green]\n"
                f"Format: [bold]{args.format.upper()}[/bold]\n"
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
