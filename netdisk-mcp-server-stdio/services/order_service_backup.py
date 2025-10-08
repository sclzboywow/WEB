#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订单服务�?
包含订单创建、支付处理、钱包管理等功能
"""

import sqlite3
import secrets
import time
from typing import Dict, Any, List, Optional
from .db import init_sync_db
from .listing_service import deliver_order
from .wallet_service import award_seller, settle_seller

def check_duplicate_purchase(buyer_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    检查重复购�?
    """
    if not buyer_id or not items:
        return {"has_duplicate": False}
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        listing_ids = [item["listing_id"] for item in items]
        placeholders = ",".join(["?" for _ in listing_ids])
        
        # 查询用户已购买的商品
        cursor.execute(f'''
            SELECT DISTINCT up.listing_id, l.title
            FROM user_purchases up
            LEFT JOIN listings l ON up.listing_id = l.id
            WHERE up.buyer_id = ? AND up.listing_id IN ({placeholders})
        ''', [buyer_id] + listing_ids)
        
        purchased_items = cursor.fetchall()
        
        if purchased_items:
            duplicate_items = [item[1] or f"商品ID:{item[0]}" for item in purchased_items]
            return {
                "has_duplicate": True,
                "duplicate_items": duplicate_items,
                "duplicate_count": len(duplicate_items)
            }
        
        return {"has_duplicate": False}
        
    except Exception as e:
        print(f"检查重复购买失�? {e}")
        return {"has_duplicate": False}
    finally:
        conn.close()

def create_order(buyer_id: str, items: List[Dict[str, Any]], remark: Optional[str] = "") -> Dict[str, Any]:
    """
    创建订单
    """
    if not buyer_id or not items:
        return {"status": "error", "message": "missing buyer_id or items"}
    
    # 导入风控服务
    from .risk_service import check_rate_limit, log_order_operation
    
    # 检查频�?
    rate_limit_result = check_rate_limit(buyer_id, 'create_order')
    if not rate_limit_result.get('allowed', False):
        return {"status": "error", "message": rate_limit_result.get('message', '操作过于频繁')}
    
    # 检查重复购买（可选功能）
    duplicate_check = check_duplicate_purchase(buyer_id, items)
    if duplicate_check.get('has_duplicate'):
        return {
            "status": "warning", 
            "message": f"您已购买过以下商�? {', '.join(duplicate_check.get('duplicate_items', []))}，是否继续？",
            "duplicate_items": duplicate_check.get('duplicate_items', [])
        }
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 生成唯一订单�?
        order_no = f"ORD{int(time.time() * 1000)}{secrets.randbelow(1000):03d}"
        
        # 查询所有商品信息并验证
        listing_ids = [item["listing_id"] for item in items]
        placeholders = ",".join(["?" for _ in listing_ids])
        
        cursor.execute(f'''
            SELECT id, seller_id, price_cents, platform_split, seller_split, status
            FROM listings
            WHERE id IN ({placeholders})
        ''', listing_ids)
        
        listings_data = {row[0]: row for row in cursor.fetchall()}
        
        # 检查所有商品是否存在且可购�?
        for listing_id in listing_ids:
            if listing_id not in listings_data:
                return {"status": "error", "message": f"listing {listing_id} not found"}
            
            listing_data = listings_data[listing_id]
            if listing_data[5] != "live":  # status
                return {"status": "error", "message": f"listing {listing_id} not available"}
        
        sale_id = listings_data[listing_ids[0]][1]  # 取第一个商品的卖家ID作为订单卖家
        
        # 计算订单总额和分�?
        total_amount = 0
        platform_fee = 0
        seller_amount = 0
        
        # 插入订单
        cursor.execute('''
            INSERT INTO orders (order_no, buyer_id, seller_id, total_amount_cents, 
                              platform_fee_cents, seller_amount_cents, status, remark)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        ''', (order_no, buyer_id, sale_id, total_amount, platform_fee, seller_amount, remark))
        
        order_id = cursor.lastrowid
        
        # 计算各个商品的分成并插入订单�?
        order_items_data = []
        for item in items:
            listing_id = item["listing_id"]
            quantity = item.get("quantity", 1)
            listing_data = listings_data[listing_id]
            
            price_cents = listing_data[2]
            platform_split = listing_data[3]
            seller_split = listing_data[4]
            
            item_amount = price_cents * quantity
            item_platform_fee = int(item_amount * platform_split)
            item_seller_amount = int(item_amount * seller_split)
            
            cursor.execute('''
                INSERT INTO order_items (order_id, listing_id, price_cents, quantity)
                VALUES (?, ?, ?, ?)
            ''', (order_id, listing_id, item_amount, quantity))
            
            order_items_data.append({
                "listing_id": listing_id,
                "quantity": quantity,
                "price_cents": item_amount,
                "platform_fee_cents": item_platform_fee,
                "seller_amount_cents": item_seller_amount
            })
            
            total_amount += item_amount
            platform_fee += item_platform_fee
            seller_amount += item_seller_amount
        
        # 更新订单总额和分�?
        cursor.execute('''
            UPDATE orders 
            SET total_amount_cents = ?, platform_fee_cents = ?, seller_amount_cents = ?
            WHERE id = ?
        ''', (total_amount, platform_fee, seller_amount, order_id))
        
        conn.commit()
        
        # 记录订单操作日志
        log_order_operation(order_id, 'created', {
            'buyer_id': buyer_id,
            'total_amount_cents': total_amount,
            'items_count': len(order_items_data)
        }, buyer_id)
        
        # 发送新订单通知给卖�?
        from .notify_service import send_order_created_notification
        send_order_created_notification(sale_id, order_id, buyer_id, total_amount)
        
        return {
            "status": "success",
            "order": {
                "id": order_id,
                "order_no": order_no,
                "buyer_id": buyer_id,
                "seller_id": sale_id,
                "total_amount_cents": total_amount,
                "platform_fee_cents": platform_fee,
                "seller_amount_cents": seller_amount,
                "status": "pending",
                "payment_status": "pending",
                "items": order_items_data
            }
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def process_payment_callback(order_id: int, provider: str, transaction_id: str, 
                           status: str, message: Optional[str] = None) -> Dict[str, Any]:
    """
    处理支付回调
    """
    if status not in ["success", "failed"]:
        return {"status": "error", "message": "invalid status"}
    
    # 导入风控服务
    from .risk_service import log_payment_callback, log_order_operation
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 检查支付记�?
        cursor.execute('''
            SELECT id, order_id, amount_cents FROM order_payments
            WHERE transaction_id = ? AND status = 'pending'
        ''', (transaction_id,))
        
        payment_row = cursor.fetchone()
        if not payment_row:
            return {"status": "error", "message": "payment not found or already processed"}
        
        payment_id = payment_row[0]
        actual_order_id = payment_row[1]
        
        if actual_order_id != order_id:
            return {"status": "error", "message": "order_id mismatch"}
        
        now = time.time()
        
        if status == "success":
            # 更新支付记录
            cursor.execute('''
                UPDATE order_payments 
                SET status = 'success', paid_at = ?
                WHERE id = ?
            ''', (now, payment_id))
            
            # 更新订单状�?
            cursor.execute('''
                UPDATE orders 
                SET status = 'paid', payment_status = 'success', paid_at = ?
                WHERE id = ?
            ''', (now, order_id))
            
            # 更新卖家钱包（加到待结算�?
            cursor.execute('''
                SELECT seller_id, seller_amount_cents FROM orders WHERE id = ?
            ''', (order_id,))
            
            seller_row = cursor.fetchone()
            if seller_row:
                seller_id, seller_amount = seller_row
                
                # 调用钱包服务奖励卖家
                award_result = award_seller(order_id, seller_id, seller_amount)
                if award_result.get("status") != "success":
                    print(f"奖励卖家失败: {award_result.get('message')}")
            
            # 调用交付逻辑
            deliver_result = deliver_order(order_id)
            if deliver_result.get("status") == "success":
                # 更新订单为已完成
                cursor.execute('''
                    UPDATE orders SET status = 'completed', completed_at = ?
                    WHERE id = ?
                ''', (now, order_id))
                
                # 结算卖家收益
                if seller_row:
                    seller_id, seller_amount = seller_row
                    settle_result = settle_seller(order_id, seller_id)
                    if settle_result.get("status") != "success":
                        print(f"结算卖家收益失败: {settle_result.get('message')}")
            
            print(f"支付成功处理: 订单 {order_id} 金额 ¥{(payment_row[2] / 100):.2f}")
            
            # 发送支付成功通知给买�?
            from .notify_service import send_payment_success_notification, send_order_delivered_notification, create_notification
            send_payment_success_notification(buyer_id, order_id, payment_row[2])
            
            # 发送卖家通知
            create_notification(seller_id, "订单已支�?, "收益已转入待结算，请及时处理", notification_type="success", sender_role="system")
            
            # 如果交付成功，发送交付通知
            if deliver_result.get("status") == "success":
                send_order_delivered_notification(buyer_id, order_id, seller_id)
            
        else:  # failed
            # 更新支付记录
            cursor.execute('''
                UPDATE order_payments 
                SET status = 'failed', payload = ?
                WHERE id = ?
            ''', (f"Failure reason: {message or 'Unknown'}", payment_id))
            
            print(f"支付失败记录: 订单 {order_id} - {message or 'Unknown'}")
        
        conn.commit()
        
        # 记录支付回调日志
        log_payment_callback(order_id, provider, transaction_id, status, {
            'message': message,
            'payment_id': payment_id,
            'amount_cents': payment_row[2]
        })
        
        # 记录订单操作日志
        log_order_operation(order_id, f'payment_{status}', {
            'provider': provider,
            'transaction_id': transaction_id,
            'message': message
        })
        
        return {
            "status": "success",
            "message": f"payment callback processed: {status}"
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def create_payment_record(order_id: int, provider: str, amount_cents: int) -> Dict[str, Any]:
    """
    创建支付记录
    """
    transaction_id = f"TXN{int(time.time() * 1000)}{secrets.randbelow(10000):04d}"
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO order_payments (order_id, provider, transaction_id, amount_cents, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', (order_id, provider, transaction_id, amount_cents))
        
        payment_id = cursor.lastrowid
        
        conn.commit()
        
        return {
            "status": "success",
            "payment_id": payment_id,
            "transaction_id": transaction_id
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()
