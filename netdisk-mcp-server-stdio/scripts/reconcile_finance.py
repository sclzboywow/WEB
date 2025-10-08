#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sync_data.db')


def parse_time_arg(val: str) -> float:
    # Accept unix seconds or ISO date/time
    if not val:
        return time.time()
    try:
        return float(val)
    except Exception:
        # try ISO
        try:
            return datetime.fromisoformat(val).timestamp()
        except Exception:
            raise argparse.ArgumentTypeError(f"Invalid time: {val}")


def load_db():
    from services.db import init_sync_db
    path = init_sync_db()
    return sqlite3.connect(path)


def reconcile(start_ts: float, end_ts: float) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    conn = load_db(); c = conn.cursor()
    anomalies: List[Dict[str, Any]] = []

    # Orders summary
    c.execute(
        '''SELECT COALESCE(SUM(total_amount_cents),0), COALESCE(SUM(platform_fee_cents),0), COALESCE(SUM(seller_amount_cents),0)
           FROM orders WHERE created_at BETWEEN ? AND ?''', (start_ts, end_ts)
    )
    row = c.fetchone()
    orders_total, platform_total, seller_total = row if row else (0, 0, 0)

    # Wallet logs breakdown
    c.execute(
        '''SELECT type, COALESCE(SUM(change_cents),0) FROM wallet_logs
           WHERE created_at BETWEEN ? AND ? GROUP BY type''', (start_ts, end_ts)
    )
    logs_map = {t: v for t, v in c.fetchall()}
    sale_sum = logs_map.get('sale', 0)
    settlement_sum = logs_map.get('settlement', 0)
    refund_in_sum = logs_map.get('refund_in', 0)
    refund_out_sum = logs_map.get('refund_out', 0)
    payout_freeze_sum = logs_map.get('payout_freeze', 0)
    payout_paid_sum = logs_map.get('payout_paid', 0)

    # Consistency checks
    # sale should equal seller_total added to pending_settlement; settlement reflects transfers to balance (can lag)
    if sale_sum != seller_total:
        anomalies.append({
            'type': 'mismatch', 'reference': 'wallet_logs.sale vs orders.seller_amount',
            'expected': seller_total, 'actual': sale_sum, 'reason': 'sale sum != seller_amount sum'
        })

    # refund_out should be non-positive; refund_in should be positive
    if refund_out_sum > 0:
        anomalies.append({'type': 'sign', 'reference': 'refund_out', 'amount': refund_out_sum, 'reason': 'refund_out should be <= 0'})
    if refund_in_sum < 0:
        anomalies.append({'type': 'sign', 'reference': 'refund_in', 'amount': refund_in_sum, 'reason': 'refund_in should be >= 0'})

    # SLA checks: pending refunds/payouts older than 24h
    cutoff = time.time() - 24*3600
    c.execute('SELECT id, amount_cents, created_at FROM refund_requests WHERE status = "pending" AND created_at < ?', (cutoff,))
    for rid, amt, created in c.fetchall():
        anomalies.append({'type': 'sla', 'reference': f'refund_request:{rid}', 'amount': amt, 'reason': 'refund pending over 24h'})

    c.execute('SELECT id, amount_cents, created_at FROM payout_requests WHERE status = "pending" AND created_at < ?', (cutoff,))
    for pid, amt, created in c.fetchall():
        anomalies.append({'type': 'sla', 'reference': f'payout_request:{pid}', 'amount': amt, 'reason': 'payout pending over 24h'})

    # Wallet non-negative invariant
    c.execute('SELECT user_id, balance_cents, pending_settlement_cents FROM user_wallets')
    for uid, bal, pend in c.fetchall():
        if (bal or 0) < 0 or (pend or 0) < 0:
            anomalies.append({'type': 'wallet', 'reference': f'user_wallet:{uid}', 'amount': (bal or 0)+(pend or 0), 'reason': 'negative balance or pending'})

    summary = {
        'window': {'start': start_ts, 'end': end_ts},
        'orders': {
            'total_amount_cents': orders_total,
            'platform_fee_cents': platform_total,
            'seller_amount_cents': seller_total,
        },
        'wallet_logs': {
            'sale': sale_sum,
            'settlement': settlement_sum,
            'refund_in': refund_in_sum,
            'refund_out': refund_out_sum,
            'payout_freeze': payout_freeze_sum,
            'payout_paid': payout_paid_sum,
        }
    }
    conn.close()
    return summary, anomalies


def main() -> int:
    parser = argparse.ArgumentParser(description='Finance reconciliation')
    default_end = time.time(); default_start = default_end - 24*3600
    parser.add_argument('--start', type=str, default=str(int(default_start)))
    parser.add_argument('--end', type=str, default=str(int(default_end)))
    parser.add_argument('--output', type=str, default=None, help='Path to save JSON/CSV')
    args = parser.parse_args()

    start_ts = parse_time_arg(args.start)
    end_ts = parse_time_arg(args.end)

    try:
        summary, anomalies = reconcile(start_ts, end_ts)
    except Exception as e:
        print(json.dumps({'status': 'error', 'message': str(e)}), flush=True)
        return 2

    result = {'status': 'success', 'summary': summary, 'anomalies': anomalies}

    if args.output:
        out_lower = args.output.lower()
        if out_lower.endswith('.csv'):
            # Write anomalies CSV
            with open(args.output, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['type','reference','amount','reason','expected','actual'])
                writer.writeheader()
                for a in anomalies:
                    writer.writerow(a)
        else:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if not anomalies else 1


if __name__ == '__main__':
    sys.exit(main())
