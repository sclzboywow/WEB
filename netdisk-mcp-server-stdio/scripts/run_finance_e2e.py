#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Non-pytest finance E2E: create order -> pay -> refund -> reconcile
Exit code: 0 when reconcile returns success JSON (structure), regardless of anomalies.
"""

import json
import os
import sys
import time
import requests


def main() -> int:
    base = os.environ.get('BASE_URL', 'http://127.0.0.1:8007')
    H={'Content-Type':'application/json'}

    # mock users
    requests.get(f'{base}/oauth/mock-login', params={'user_id':'cli_fin_buyer','role':'basic'}, timeout=10)
    requests.get(f'{base}/oauth/mock-login', params={'user_id':'cli_fin_seller','role':'seller'}, timeout=10)

    # create + review listing
    lr = requests.post(f'{base}/api/listings', headers=H, data=json.dumps({'seller_id':'cli_fin_seller','title':'F','price_cents':500,'listing_type':'single'}), timeout=10).json()
    lid = lr.get('listing_id')
    requests.post(f'{base}/api/listings/{lid}/review', headers=H, data=json.dumps({'status':'approved','remark':'ok','reviewer_id':'admin'}), timeout=10)

    # order
    od = requests.post(f'{base}/api/orders', headers=H, data=json.dumps({'buyer_id':'cli_fin_buyer','items':[{'listing_id':lid,'quantity':1}]}), timeout=10).json()
    oid = od.get('order_id')
    pay = requests.post(f'{base}/api/orders/{oid}/pay', headers=H, data=json.dumps({'provider':'mock'}), timeout=10).json()
    txn = pay.get('transaction_id'); amt = pay.get('amount_cents',500)
    time.sleep(0.2)
    requests.post(f'{base}/api/payment/callback', headers=H, data=json.dumps({'transaction_id':txn,'status':'success','amount_cents':amt,'message':'ok'}), timeout=20)

    # refund
    requests.post(f'{base}/api/orders/{oid}/refund', headers=H, data=json.dumps({'buyer_id':'cli_fin_buyer','reason':'t'}), timeout=10)
    time.sleep(0.2)
    rr = requests.get(f'{base}/api/refund-requests', timeout=10).json(); rid = rr.get('items')[0]['id']
    requests.post(f'{base}/api/orders/{oid}/refund/review', headers=H, data=json.dumps({'refund_id':rid,'reviewer_id':'admin','status':'approved','remark':'ok'}), timeout=10)
    requests.post(f'{base}/api/refund-requests/{rid}/process', headers=H, data=json.dumps({'operator_id':'admin','remark':'ok'}), timeout=20)

    # reconcile
    rep = requests.get(f'{base}/api/reports/finance/reconcile', timeout=10).json()
    print(json.dumps(rep, ensure_ascii=False))
    return 0 if isinstance(rep, dict) and 'summary' in rep and 'anomalies' in rep else 1


if __name__ == '__main__':
    sys.exit(main())


