# Money Lover Transaction Export (Python)

This repo contains a Python script that exports transaction data from Money Lover into a JSON file.

Implementation is based on the API flow used in:
- https://github.com/allexxis/moneylover-client

## Script

- Python: 3.9+
- Dependencies: `rich`, `requests`

Install dependency:

```bash
python -m pip install rich requests
```

## Usage

This exporter is token-based, which works for Google SSO accounts.

Provide the token in one of these ways:
- `--token "<access token>"`
- `.env` file with `MONEYLOVER_TOKEN=...`

### Export transactions

```bash
python export_moneylover_transactions.py \
  --token "<AuthJWT token>" \
  --start-date "2026-01-01" \
  --end-date "2026-01-31" \
  --output "exports/january-2026.json"
```

With env var:

```bash
export MONEYLOVER_TOKEN="<AuthJWT token>"
python export_moneylover_transactions.py \
  --start-date "2026-01-01" \
  --end-date "2026-01-31" \
  --output "exports/january-2026.json"
```

If `--start-date` and `--end-date` are omitted, the script exports all transactions by using a very wide date window (`1900-01-01` to today).

### Filter by wallet

By wallet name:

```bash
python export_moneylover_transactions.py \
  --token "<AuthJWT token>" \
  --start-date "2026-01-01" \
  --end-date "2026-01-31" \
  --wallet-name "Main Wallet"
```

By wallet ID:

```bash
python export_moneylover_transactions.py \
  --token "<AuthJWT token>" \
  --start-date "2026-01-01" \
  --end-date "2026-01-31" \
  --wallet-id "<wallet_id>"
```

### List wallets

```bash
python export_moneylover_transactions.py --token "<AuthJWT token>" --start-date "2026-01-01" --end-date "2026-01-31" --list-wallets
```

### How to get the access token with Google SSO

1. Open `https://web.moneylover.me` and sign in with Google.
2. Open browser DevTools.
3. Go to Application/Storage -> Local Storage -> `https://web.moneylover.me`.
4. Copy the value of key `access_token`.
5. Pass it via `--token`, env var, or paste when prompted.

`--start-date` and `--end-date` are optional and accept `YYYY-MM-DD` or `MM/DD/YYYY`.
