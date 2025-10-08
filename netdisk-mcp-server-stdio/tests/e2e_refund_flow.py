#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
from typing import Any, Dict

import requests


def main() -> int:
    base = os.environ.get('BASE_URL', 'http://127.0.0.1:8001')
    headers = {'Content-Type': 'application/json'}

    def jpost(url: str, payload: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
        r = requests.post(url, data=json.dumps(payload), headers=headers, timeout=timeout)
        try:
            return r.json()
        except Exception:
            return {'status': 'error', 'message': f'non-json response {r.status_code}: {r.text[:200]}'}

    def jget(url: str, params: Dict[str, Any] = None, timeout: int = 10) -> Dict[str, Any]:
        r = requests.get(url, params=params, timeout=timeout)
        try:
            return r.json()
        except Exception:
            return {'status': 'error', 'message': f'non-json response {r.status_code}: {r.text[:200]}'}

    # mock-login users
    rb = requests.get(f"{base}/oauth/mock-login", params={"user_id": "test_buyer_001", "role": "basic"}, timeout=10)
    rs = requests.get(f"{base}/oauth/mock-login", params={"user_id": "test_seller_001", "role": "seller"}, timeout=10)
    print('login', rb.status_code, rs.status_code)

    # create listing
    listing_payload = {
        "seller_id": "test_seller_001",
        "title": "Test Item A",
        "price_cents": 1999,
        "listing_type": "single",
        "description": "auto-case",
        "files": [{"file_path": "/a/b/c.txt", "file_name": "c.txt", "file_size": 123}],
    }
    lr = jpost(f"{base}/api/listings", listing_payload)
    print('listing create', lr)
    listing_id = lr.get('listing_id') or lr.get('id') or (lr.get('listing') or {}).get('id')
    if not listing_id:
        print('listing_id missing, abort')
        return 1

    # approve listing
    rv = jpost(f"{base}/api/listings/{listing_id}/review", {"status": "approved", "remark": "ok", "reviewer_id": "admin"})
    print('listing review', rv)

    # create order
    od = jpost(f"{base}/api/orders", {"buyer_id": "test_buyer_001", "items": [{"listing_id": listing_id, "quantity": 1}]})
    print('order create', od)
    order_id = od.get('order_id') or od.get('id') or (od.get('order') or {}).get('id')
    if not order_id:
        print('order_id missing, abort')
        return 1

    # pay
    pay = jpost(f"{base}/api/orders/{order_id}/pay", {"provider": "mock"})
    print('pay init', pay)
    transaction_id = pay.get('transaction_id')
    amount_cents = pay.get('amount_cents', 1999)
    if not transaction_id:
        print('transaction_id missing, abort')
        return 1

    # callback success
    time.sleep(0.2)
    cb = jpost(
        f"{base}/api/payment/callback",
        {"transaction_id": transaction_id, "status": "success", "amount_cents": amount_cents, "message": "ok"},
        timeout=25,
    )
    print('callback', cb)

    # notifications
    bn = jget(f"{base}/api/notifications", {"user_id": "test_buyer_001", "limit": 10, "offset": 0})
    sn = jget(f"{base}/api/notifications", {"user_id": "test_seller_001", "limit": 10, "offset": 0})
    print('noti totals', bn.get('total'), sn.get('total'))

    # apply refund
    ra = jpost(f"{base}/api/orders/{order_id}/refund", {"buyer_id": "test_buyer_001", "reason": "test refund"})
    print('refund apply', ra)
    time.sleep(0.2)

    # list refunds
    rr = jget(f"{base}/api/refund-requests")
    print('refund list keys', list(rr.keys()))
    items = rr.get('items') or rr.get('refunds') or []
    refund_id = None
    for it in items:
        if it.get('order_id') == order_id:
            refund_id = it.get('id')
            break
    if refund_id is None and items:
        refund_id = items[0].get('id')
    print('refund id', refund_id)

    # review approve
    rv2 = jpost(f"{base}/api/orders/{order_id}/refund/review", {"refund_id": refund_id, "reviewer_id": "admin", "status": "approved", "remark": "approved"})
    print('refund review', rv2)

    # process refund
    pr = jpost(f"{base}/api/refund-requests/{refund_id}/process", {"operator_id": "admin", "remark": "processed"})
    print('refund process', pr)

    # unread counts
    bu = jget(f"{base}/api/notifications/unread-count", {"user_id": "test_buyer_001"})
    su = jget(f"{base}/api/notifications/unread-count", {"user_id": "test_seller_001"})
    print('unread', bu, su)

    return 0


if __name__ == '__main__':
    sys.exit(main())


