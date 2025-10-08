#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
触发支付回调并验证通知写入与查询
"""
import sqlite3
import os
import requests
import json

BASE_URL = "http://localhost:8000"
# 兼容从仓库根目录或从 netdisk 目录运行
DB_PATH = os.path.join(os.path.dirname(__file__), "sync_data.db")

def main():
    # 读取最新订单与支付记录
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, order_no, buyer_id, seller_id FROM orders ORDER BY id DESC LIMIT 1")
    order = cur.fetchone()
    if not order:
        print("[ERROR] 无订单记录")
        return
    order_id, order_no, buyer_id, seller_id = order

    cur.execute("SELECT transaction_id, amount_cents, status FROM order_payments WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,))
    pay = cur.fetchone()
    if not pay:
        print("[ERROR] 无支付记录，请先调用 /api/orders/{id}/pay")
        return
    transaction_id, amount_cents, pay_status = pay
    print(f"订单: {order_id} 交易号: {transaction_id} 金额: {amount_cents} 状态: {pay_status}")
    conn.close()

    # 触发支付回调
    payload = {
        "transaction_id": transaction_id,
        "status": "success",
        "amount_cents": amount_cents,
        "message": "测试支付成功"
    }
    r = requests.post(f"{BASE_URL}/api/payment/callback", json=payload)
    print("回调响应:", r.status_code, r.text)

    # 查询通知（买家、卖家）
    for uid in [buyer_id, seller_id]:
        rr = requests.get(f"{BASE_URL}/api/notifications", params={
            "user_id": uid,
            "status": "all",
            "limit": 10
        })
        print(f"通知列表({uid}):", rr.status_code)
        try:
            data = rr.json()
        except Exception:
            print(rr.text)
            continue
        notifs = data.get("notifications", []) if isinstance(data, dict) else []
        print(json.dumps({"count": len(notifs), "titles": [n.get("title") for n in notifs]}, ensure_ascii=False))

if __name__ == "__main__":
    main()


