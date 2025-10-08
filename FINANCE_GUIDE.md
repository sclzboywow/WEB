# Finance Reconciliation Guide

## CLI Script

Run:

```bash
python netdisk-mcp-server-stdio/scripts/reconcile_finance.py --start 1690000000 --end 1690086400 --output report.json
```

Args:
- `--start/--end`: Unix seconds or ISO date (default: last 24h)
- `--output`: Optional path (.json or .csv). CSV exports anomaly list only

Output JSON:

```json
{
  "status": "success",
  "summary": {
    "window": {"start": 0, "end": 0},
    "orders": {"total_amount_cents": 0, "platform_fee_cents": 0, "seller_amount_cents": 0},
    "wallet_logs": {"sale": 0, "settlement": 0, "refund_in": 0, "refund_out": 0, "payout_freeze": 0, "payout_paid": 0}
  },
  "anomalies": [
    {"type": "mismatch", "reference": "wallet_logs.sale vs orders.seller_amount", "expected": 0, "actual": 0, "reason": "sale sum != seller_amount sum"}
  ]
}
```

Exit code: 0 (no anomalies), 1 (anomalies found), 2 (execution error).

## API

`GET /api/reports/finance/reconcile?start=...&end=...`
Returns the same structure as the CLI.

## Admin Panel

- Navigate to Reconcile panel, pick datetime range, click Generate Report
- Export button downloads the last report JSON

## Common Issues

- Negative wallet balances: investigate `wallet_logs` for unexpected deductions; correct via admin adjustment and root-cause fix
- Pending refund/payout SLA: process items older than 24h
- sale vs seller_amount mismatch: check orders created during the window vs wallet logs timing; ensure payment callback writes `sale` once per order


