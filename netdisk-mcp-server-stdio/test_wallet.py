#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钱包功能测试脚本
验证卖家收益与提现流程
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_wallet_flow():
    """测试完整的钱包流程"""
    print("🧪 开始测试钱包功能...")
    
    # 1. 创建测试用户
    print("\n1️⃣ 创建测试用户...")
    user_id = f"test_user_{int(time.time())}"
    
    # 2. 创建测试订单
    print("\n2️⃣ 创建测试订单...")
    order_data = {
        "buyer_id": f"buyer_{int(time.time())}",
        "items": [
            {
                "listing_id": 1,
                "quantity": 1
            }
        ],
        "remark": "测试订单"
    }
    
    try:
        # 模拟订单创建（这里需要先有商品）
        print("   订单创建功能需要先有商品，跳过...")
        
        # 3. 测试钱包信息查询
        print("\n3️⃣ 测试钱包信息查询...")
        wallet_response = requests.get(f"{BASE_URL}/api/wallet/{user_id}")
        if wallet_response.status_code == 200:
            wallet_data = wallet_response.json()
            print(f"   ✅ 钱包查询成功: {wallet_data}")
        else:
            print(f"   ❌ 钱包查询失败: {wallet_response.status_code}")
        
        # 4. 测试提现申请
        print("\n4️⃣ 测试提现申请...")
        payout_data = {
            "user_id": user_id,
            "amount_cents": 10000,  # 100元
            "method": "alipay",
            "account_info": "test@example.com",
            "remark": "测试提现"
        }
        
        payout_response = requests.post(f"{BASE_URL}/api/payouts", json=payout_data)
        if payout_response.status_code == 200:
            payout_result = payout_response.json()
            print(f"   ✅ 提现申请成功: {payout_result}")
            
            if payout_result.get("status") == "success":
                payout_id = payout_result.get("payout_id")
                
                # 5. 测试提现记录查询
                print("\n5️⃣ 测试提现记录查询...")
                payouts_response = requests.get(f"{BASE_URL}/api/payouts/mine?user_id={user_id}")
                if payouts_response.status_code == 200:
                    payouts_data = payouts_response.json()
                    print(f"   ✅ 提现记录查询成功: {payouts_data}")
                else:
                    print(f"   ❌ 提现记录查询失败: {payouts_response.status_code}")
                
                # 6. 测试管理员审核
                print("\n6️⃣ 测试管理员审核...")
                review_data = {
                    "status": "approved",
                    "reviewer_id": "admin001",
                    "remark": "测试审核通过"
                }
                
                review_response = requests.post(f"{BASE_URL}/api/payouts/{payout_id}/review", json=review_data)
                if review_response.status_code == 200:
                    review_result = review_response.json()
                    print(f"   ✅ 审核成功: {review_result}")
                else:
                    print(f"   ❌ 审核失败: {review_response.status_code}")
        
        else:
            print(f"   ❌ 提现申请失败: {payout_response.status_code}")
            print(f"   错误信息: {payout_response.text}")
        
        # 7. 测试管理员提现列表
        print("\n7️⃣ 测试管理员提现列表...")
        admin_payouts_response = requests.get(f"{BASE_URL}/api/payouts?status=pending")
        if admin_payouts_response.status_code == 200:
            admin_payouts_data = admin_payouts_response.json()
            print(f"   ✅ 管理员提现列表查询成功: {len(admin_payouts_data.get('payouts', []))} 条记录")
        else:
            print(f"   ❌ 管理员提现列表查询失败: {admin_payouts_response.status_code}")
        
        print("\n🎉 钱包功能测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")

def test_api_endpoints():
    """测试API端点是否可访问"""
    print("\n🔍 测试API端点可访问性...")
    
    endpoints = [
        "/api/wallet/test_user",
        "/api/payouts",
        "/api/payouts/mine?user_id=test_user",
        "/api/orders/seller?seller_id=test_seller"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}")
            print(f"   {endpoint}: {response.status_code}")
        except Exception as e:
            print(f"   {endpoint}: ❌ {e}")

if __name__ == "__main__":
    print("🚀 钱包功能测试开始")
    print("=" * 50)
    
    # 测试API端点
    test_api_endpoints()
    
    # 测试完整流程
    test_wallet_flow()
    
    print("\n" + "=" * 50)
    print("✅ 测试完成！")
