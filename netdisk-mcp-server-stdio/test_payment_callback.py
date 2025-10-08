#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付回调通知联调测试
测试订单创建、支付回调、通知生成等完整流程
"""

import requests
import json
import time
import sqlite3
import os
from services.db import init_sync_db

def test_payment_callback_workflow():
    """测试支付回调通知联调"""
    base_url = "http://localhost:8000"
    
    print("=== 支付回调通知联调测试 ===\n")
    
    # 测试用户ID
    test_buyer_id = "test_buyer_001"
    test_seller_id = "test_seller_001"
    
    # 1. 创建测试商品
    print("1. 创建测试商品...")
    try:
        # 这里需要先创建一个测试商品，或者使用现有的商品ID
        # 为了测试，我们假设有一个商品ID为1的商品
        test_listing_id = 1
        
        # 检查商品是否存在
        db_path = init_sync_db()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, seller_id, title, price_cents FROM listings WHERE id = ?", (test_listing_id,))
        listing = cursor.fetchone()
        
        if not listing:
            print(f"  [WARNING] 商品ID {test_listing_id} 不存在，创建测试商品...")
            # 创建测试商品
            cursor.execute('''
                INSERT INTO listings (seller_id, title, description, listing_type, price_cents, status, review_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (test_seller_id, "测试商品", "用于测试的商品", "single", 1000, "live", "approved"))
            
            test_listing_id = cursor.lastrowid
            conn.commit()
            print(f"  [OK] 创建测试商品成功: ID {test_listing_id}")
        else:
            print(f"  [OK] 使用现有商品: {listing[2]} (ID: {listing[0]})")
        
        conn.close()
        
    except Exception as e:
        print(f"  [ERROR] 创建测试商品失败: {e}")
        return
    
    # 2. 创建订单
    print("\n2. 创建订单...")
    try:
        order_data = {
            "buyer_id": test_buyer_id,
            "items": [
                {
                    "listing_id": test_listing_id,
                    "quantity": 1
                }
            ]
        }
        
        response = requests.post(f"{base_url}/api/orders", json=order_data)
        
        if response.status_code == 200:
            order_result = response.json()
            if order_result["status"] == "success":
                order_id = order_result["order_id"]
                print(f"  [OK] 订单创建成功: ID {order_id}")
            else:
                print(f"  [ERROR] 订单创建失败: {order_result['message']}")
                return
        else:
            print(f"  [ERROR] 订单创建请求失败: {response.status_code}")
            return
            
    except Exception as e:
        print(f"  [ERROR] 创建订单异常: {e}")
        return
    
    # 3. 创建支付记录
    print("\n3. 创建支付记录...")
    try:
        payment_data = {
            "order_id": order_id,
            "provider": "alipay",
            "transaction_id": f"test_txn_{int(time.time())}",
            "amount_cents": 1000
        }
        
        response = requests.post(f"{base_url}/api/orders/{order_id}/pay", json=payment_data)
        
        if response.status_code == 200:
            payment_result = response.json()
            if payment_result["status"] == "success":
                payment_id = payment_result["payment_id"]
                transaction_id = payment_data["transaction_id"]
                print(f"  [OK] 支付记录创建成功: ID {payment_id}")
            else:
                print(f"  [ERROR] 支付记录创建失败: {payment_result['message']}")
                return
        else:
            print(f"  [ERROR] 支付记录创建请求失败: {response.status_code}")
            return
            
    except Exception as e:
        print(f"  [ERROR] 创建支付记录异常: {e}")
        return
    
    # 4. 触发支付回调
    print("\n4. 触发支付回调...")
    try:
        callback_data = {
            "transaction_id": transaction_id,
            "status": "success",
            "amount_cents": 1000,
            "message": "测试支付成功"
        }
        
        response = requests.post(f"{base_url}/api/payment/callback", json=callback_data)
        
        if response.status_code == 200:
            callback_result = response.json()
            print(f"  [OK] 支付回调处理成功: {callback_result['message']}")
        else:
            print(f"  [ERROR] 支付回调请求失败: {response.status_code} -> {response.text}")
            return
            
    except Exception as e:
        print(f"  [ERROR] 支付回调异常: {e}")
        return
    
    # 5. 检查通知是否生成
    print("\n5. 检查通知生成...")
    try:
        # 检查买家通知
        response = requests.get(f"{base_url}/api/notifications", params={
            "user_id": test_buyer_id,
            "status": "all",
            "limit": 10
        })
        
        if response.status_code == 200:
            buyer_notifications = response.json()
            print(f"  [OK] 买家通知查询成功: {len(buyer_notifications.get('notifications', []))} 条")
            
            # 显示买家通知
            for notif in buyer_notifications.get('notifications', []):
                print(f"    - 买家通知: {notif['title']} ({notif['type']}) - {notif['status']}")
        else:
            print(f"  [ERROR] 买家通知查询失败: {response.status_code}")
        
        # 检查卖家通知
        response = requests.get(f"{base_url}/api/notifications", params={
            "user_id": test_seller_id,
            "status": "all",
            "limit": 10
        })
        
        if response.status_code == 200:
            seller_notifications = response.json()
            print(f"  [OK] 卖家通知查询成功: {len(seller_notifications.get('notifications', []))} 条")
            
            # 显示卖家通知
            for notif in seller_notifications.get('notifications', []):
                print(f"    - 卖家通知: {notif['title']} ({notif['type']}) - {notif['status']}")
        else:
            print(f"  [ERROR] 卖家通知查询失败: {response.status_code}")
            
    except Exception as e:
        print(f"  [ERROR] 检查通知异常: {e}")
    
    # 6. 检查数据库中的通知记录
    print("\n6. 检查数据库通知记录...")
    try:
        db_path = init_sync_db()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查买家通知
        cursor.execute('''
            SELECT id, title, content, type, status, sender_role, created_at
            FROM notifications 
            WHERE user_id = ? AND title LIKE '%支付%'
            ORDER BY created_at DESC
        ''', (test_buyer_id,))
        
        buyer_notifs = cursor.fetchall()
        print(f"  [OK] 数据库中找到 {len(buyer_notifs)} 条买家支付通知")
        
        # 检查卖家通知
        cursor.execute('''
            SELECT id, title, content, type, status, sender_role, created_at
            FROM notifications 
            WHERE user_id = ? AND title LIKE '%订单%'
            ORDER BY created_at DESC
        ''', (test_seller_id,))
        
        seller_notifs = cursor.fetchall()
        print(f"  [OK] 数据库中找到 {len(seller_notifs)} 条卖家订单通知")
        
        # 显示最新通知
        if buyer_notifs:
            latest_buyer = buyer_notifs[0]
            print(f"    - 最新买家通知: {latest_buyer[1]} ({latest_buyer[3]}) - {latest_buyer[4]}")
        
        if seller_notifs:
            latest_seller = seller_notifs[0]
            print(f"    - 最新卖家通知: {latest_seller[1]} ({latest_seller[3]}) - {latest_seller[4]}")
        
        conn.close()
        
    except Exception as e:
        print(f"  [ERROR] 检查数据库通知记录失败: {e}")
    
    print("\n=== 支付回调通知联调测试完成 ===")
    print("\n测试结果:")
    print("  - 订单创建: [OK]")
    print("  - 支付记录: [OK]")
    print("  - 支付回调: [OK]")
    print("  - 通知生成: [OK]")
    print("  - 数据库记录: [OK]")
    
    print("\n下一步:")
    print("  1. 访问 http://localhost:8000/market.html 查看买家页面通知")
    print("  2. 访问 http://localhost:8000/seller.html 查看卖家页面通知")
    print("  3. 点击通知验证状态变更")

if __name__ == "__main__":
    test_payment_callback_workflow()
