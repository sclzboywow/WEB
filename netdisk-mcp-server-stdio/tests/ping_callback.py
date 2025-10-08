#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests

def main():
    base = os.environ.get('BASE_URL', 'http://127.0.0.1:8002')
    url = f"{base}/api/payment/callback"
    payload = {"transaction_id": "no_such", "status": "success", "amount_cents": 123, "message": "ok"}
    r = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload), timeout=5)
    print(r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text[:200])

if __name__ == '__main__':
    main()


