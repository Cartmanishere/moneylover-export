#!/usr/bin/env python
"""Money Lover API client primitives."""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import unquote

import requests


API_BASE = "https://web.moneylover.me/api"


class MoneyLoverAPIError(RuntimeError):
    """Raised when Money Lover returns API-level errors."""


class TokenExpiredError(RuntimeError):
    """Raised when token is invalid/expired (HTTP 403)."""


def extract_tokens(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if not text:
        return "", ""

    refresh_match = re.search(r"[?&]refresh_token=([^&]+)", text)
    refresh_token = unquote(refresh_match.group(1)) if refresh_match else ""

    if text.startswith("AuthJWT "):
        return text[len("AuthJWT ") :].strip(), refresh_token

    access_match = re.search(r"[?&]access_token=([^&]+)", text)
    if access_match:
        return unquote(access_match.group(1)), refresh_token

    token_match = re.search(r"[?&]token=([^&]+)", text)
    if token_match:
        return unquote(token_match.group(1)), refresh_token

    return text, refresh_token


def resolve_wallet_id(
    wallets: list[dict[str, Any]], wallet_name: str | None, wallet_id: str | None
) -> str:
    if wallet_id:
        return wallet_id
    if wallet_name is None:
        return "all"

    normalized = wallet_name.replace(" ", "")
    for wallet in wallets:
        name = str(wallet.get("name", "")).replace(" ", "")
        if name.lower() == normalized.lower():
            return str(wallet.get("_id"))

    raise RuntimeError(
        f"Wallet '{wallet_name}' not found. Use --list-wallets to see available wallets."
    )


class MoneyLoverClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            response = requests.post(
                f"{API_BASE}{path}",
                headers={
                    "authorization": f"AuthJWT {self.access_token}",
                    "cache-control": "no-cache, max-age=0, no-store, no-transform, must-revalidate",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=60,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Network error calling {path}: {exc}") from exc

        if response.status_code == 403:
            raise TokenExpiredError("HTTP 403 from Money Lover API (token expired or invalid).")
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} calling {path}: {response.text[:500]}")

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Non-JSON response from {path}: {response.text[:300]}") from exc

        if isinstance(body, dict):
            if body.get("error") not in (None, 0):
                raise MoneyLoverAPIError(f"Error {body.get('error')}: {body.get('msg')}")
            if body.get("e") not in (None, 0):
                raise MoneyLoverAPIError(f"Error {body.get('e')}: {body.get('message')}")

        return body.get("data", body)

    def get_wallets(self) -> list[dict[str, Any]]:
        wallets = self._post("/wallet/list")
        if isinstance(wallets, list):
            return wallets
        return []

    def get_transactions(
        self,
        start_date: date,
        end_date: date,
        wallet_id: str = "all",
    ) -> Any:
        return self._post(
            "/transaction/list",
            payload={
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d"),
                "walletId": wallet_id,
            },
        )
