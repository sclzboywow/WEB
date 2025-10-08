#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订单服务层
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
    检查重复购买
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
        print(f"检查重复购买失败: {e}")
        return {"has_duplicate": False}
    finally:
        conn.close()

def create_order(buyer_id: str, items: List[Dict[str, Any]], 
                check_duplicate: bool = True) -> Dict[str, Any]:
    """
    创建订单
    """
    if not buyer_id or not items:
        return {"status": "error", "message": "缺少必要参数"}
    
    # 导入风控服务
    from .risk_service import check_rate_limit
    
    # 检查频控
    rate_limit_result = check_rate_limit(buyer_id, "create_order")
    if not rate_limit_result.get("allowed", True):
        return {"status": "error", "message": "操作过于频繁，请稍后再试"}
    
    # 检查重复购买（可选功能）
    if check_duplicate:
        duplicate_check = check_duplicate_purchase(buyer_id, items)
        if duplicate_check.get("has_duplicate"):
            return {
                "status": "warning", 
                "message": f"您已购买过以下商品: {', '.join(duplicate_check.get('duplicate_items', []))}，是否继续？",
                "duplicate_items": duplicate_check.get("duplicate_items", [])
            }
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 开始事务
        cursor.execute("BEGIN TRANSACTION")
        
        # 生成订单号
        order_no = f"ORD{int(time.time())}{secrets.randbelow(1000):03d}"
        
        # 计算总金额
        total_amount_cents = 0
        platform_fee_cents = 0
        seller_amount_cents = 0
        seller_id = None
        
        for item in items:
            listing_id = item["listing_id"]
            quantity = item.get("quantity", 1)
            
            # 获取商品信息
            cursor.execute('''
                SELECT seller_id, price_cents, platform_split, seller_split, status
                FROM listings 
                WHERE id = ? AND status = 'live'
            ''', (listing_id,))
            
            listing_row = cursor.fetchone()
            if not listing_row:
                raise Exception(f"商品 {listing_id} 不存在或已下架")
            
            item_seller_id, price_cents, platform_split, seller_split, status = listing_row
            
            if seller_id is None:
                seller_id = item_seller_id
            elif seller_id != item_seller_id:
                raise Exception("订单中的商品必须来自同一卖家")
            
            item_total = price_cents * quantity
            item_platform_fee = int(item_total * platform_split)
            item_seller_amount = int(item_total * seller_split)
            
            total_amount_cents += item_total
            platform_fee_cents += item_platform_fee
            seller_amount_cents += item_seller_amount
        
        # 创建订单
        cursor.execute('''
            INSERT INTO orders (order_no, buyer_id, seller_id, total_amount_cents, 
                              platform_fee_cents, seller_amount_cents, currency, status, 
                              payment_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'CNY', 'pending', 'pending', ?, ?)
        ''', (order_no, buyer_id, seller_id, total_amount_cents, 
              platform_fee_cents, seller_amount_cents, time.time(), time.time()))
        
        order_id = cursor.lastrowid
        
        # 创建订单项
        for item in items:
            listing_id = item["listing_id"]
            quantity = item.get("quantity", 1)
            
            cursor.execute('''
                SELECT price_cents FROM listings WHERE id = ?
            ''', (listing_id,))
            
            price_cents = cursor.fetchone()[0]
            
            cursor.execute('''
                INSERT INTO order_items (order_id, listing_id, price_cents, quantity, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (order_id, listing_id, price_cents, quantity, time.time()))
        
        # 更新订单总金额
        cursor.execute('''
            UPDATE orders 
            SET total_amount_cents = ?, platform_fee_cents = ?, seller_amount_cents = ?
            WHERE id = ?
        ''', (total_amount_cents, platform_fee_cents, seller_amount_cents, order_id))
        
        # 提交事务
        conn.commit()
        
        return {
            "status": "success",
            "order_id": order_id,
            "order_no": order_no,
            "total_amount_cents": total_amount_cents,
            "platform_fee_cents": platform_fee_cents,
            "seller_amount_cents": seller_amount_cents
        }
        
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def process_payment_callback(transaction_id: str, status: str, 
                           amount_cents: int, message: str = None) -> Dict[str, Any]:
    """
    处理支付回调
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 查找对应的支付记录
        cursor.execute('''
            SELECT id, order_id, amount_cents, status
            FROM order_payments 
            WHERE transaction_id = ? AND status = 'pending'
        ''', (transaction_id,))
        
        payment_row = cursor.fetchone()
        if not payment_row:
            return {"status": "error", "message": "支付记录不存在"}
        
        payment_id, order_id, expected_amount, current_status = payment_row
        
        # 验证金额
        if amount_cents != expected_amount:
            return {"status": "error", "message": f"金额不匹配: 期望 {expected_amount}, 实际 {amount_cents}"}
        
        if status == "success":
            # 更新支付记录
            cursor.execute('''
                UPDATE order_payments 
                SET status = 'success', paid_at = ?
                WHERE id = ?
            ''', (time.time(), payment_id))
            
            # 更新订单状态
            cursor.execute('''
                UPDATE orders 
                SET status = 'paid', payment_status = 'success', paid_at = ?
                WHERE id = ?
            ''', (time.time(), order_id))
            
            # 获取订单信息
            cursor.execute('''
                SELECT seller_id, seller_amount_cents FROM orders WHERE id = ?
            ''', (order_id,))
            
            seller_id, seller_amount_cents = cursor.fetchone()
            
            # 更新卖家钱包（加到待结算）
            award_result = award_seller(order_id, seller_id, seller_amount_cents)
            if award_result.get("status") != "success":
                print(f"结算卖家收益失败: {award_result.get('message')}")
            
            # 交付订单
            deliver_result = deliver_order(order_id)
            if deliver_result.get("status") == "success":
                # 更新订单状态为已完成
                cursor.execute('''
                    UPDATE orders SET status = 'completed', completed_at = ?
                    WHERE id = ?
                ''', (time.time(), order_id))
            
            print(f"支付成功处理: 订单 {order_id} 金额 ¥{(payment_row[2] / 100):.2f}")
            
            # 发送支付成功通知给买家
            from .notify_service import send_payment_success_notification, send_order_delivered_notification, create_notification
            send_payment_success_notification(buyer_id, order_id, payment_row[2])
            
            # 发送卖家通知
            create_notification(seller_id, "订单已支付", "收益已转入待结算，请及时处理", notification_type="success", sender_role="system")
            
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
            
            # 更新订单状态
            cursor.execute('''
                UPDATE orders 
                SET status = 'failed', payment_status = 'failed'
                WHERE id = ?
            ''', (order_id,))
        
        conn.commit()
        
        return {
            "status": "success",
            "message": f"支付回调处理完成: {status}",
            "order_id": order_id
        }
        
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def create_payment_record(order_id: int, provider: str, transaction_id: str, 
                         amount_cents: int) -> Dict[str, Any]:
    """
    创建支付记录
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO order_payments (order_id, provider, transaction_id, amount_cents, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        ''', (order_id, provider, transaction_id, amount_cents, time.time()))
        
        payment_id = cursor.lastrowid
        conn.commit()
        
        return {
            "status": "success",
            "payment_id": payment_id,
            "message": "支付记录创建成功"
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def get_order_detail(order_id: int) -> Dict[str, Any]:
    """
    获取订单详情
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 获取订单基本信息
        cursor.execute('''
            SELECT o.id, o.order_no, o.buyer_id, o.seller_id, o.total_amount_cents,
                   o.platform_fee_cents, o.seller_amount_cents, o.currency, o.status,
                   o.payment_status, o.created_at, o.updated_at, o.paid_at, o.delivered_at,
                   o.completed_at, u.display_name as buyer_name, s.display_name as seller_name
            FROM orders o
            LEFT JOIN users u ON o.buyer_id = u.user_id
            LEFT JOIN users s ON o.seller_id = s.user_id
            WHERE o.id = ?
        ''', (order_id,))
        
        order_row = cursor.fetchone()
        if not order_row:
            return {"status": "error", "message": "订单不存在"}
        
        # 获取订单项
        cursor.execute('''
            SELECT oi.id, oi.listing_id, oi.price_cents, oi.quantity, oi.delivered_at,
                   l.title, l.description
            FROM order_items oi
            LEFT JOIN listings l ON oi.listing_id = l.id
            WHERE oi.order_id = ?
        ''', (order_id,))
        
        items = []
        for row in cursor.fetchall():
            items.append({
                "id": row[0],
                "listing_id": row[1],
                "price_cents": row[2],
                "quantity": row[3],
                "delivered_at": row[4],
                "title": row[5],
                "description": row[6]
            })
        
        # 获取支付记录
        cursor.execute('''
            SELECT id, provider, transaction_id, amount_cents, status, created_at, paid_at
            FROM order_payments 
            WHERE order_id = ?
            ORDER BY created_at DESC
        ''', (order_id,))
        
        payments = []
        for row in cursor.fetchall():
            payments.append({
                "id": row[0],
                "provider": row[1],
                "transaction_id": row[2],
                "amount_cents": row[3],
                "status": row[4],
                "created_at": row[5],
                "paid_at": row[6]
            })
        
        return {
            "status": "success",
            "order": {
                "id": order_row[0],
                "order_no": order_row[1],
                "buyer_id": order_row[2],
                "seller_id": order_row[3],
                "total_amount_cents": order_row[4],
                "platform_fee_cents": order_row[5],
                "seller_amount_cents": order_row[6],
                "currency": order_row[7],
                "status": order_row[8],
                "payment_status": order_row[9],
                "created_at": order_row[10],
                "updated_at": order_row[11],
                "paid_at": order_row[12],
                "delivered_at": order_row[13],
                "completed_at": order_row[14],
                "buyer_name": order_row[15],
                "seller_name": order_row[16],
                "items": items,
                "payments": payments
            }
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def get_user_orders(user_id: str, role: str = "buyer", 
                   status: Optional[str] = None, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """
    获取用户订单列表
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 构建查询条件
        if role == "buyer":
            where_clause = "WHERE o.buyer_id = ?"
            params = [user_id]
        elif role == "seller":
            where_clause = "WHERE o.seller_id = ?"
            params = [user_id]
        else:
            return {"status": "error", "message": "无效的角色类型"}
        
        if status:
            where_clause += " AND o.status = ?"
            params.append(status)
        
        # 获取订单列表
        cursor.execute(f'''
            SELECT o.id, o.order_no, o.buyer_id, o.seller_id, o.total_amount_cents,
                   o.currency, o.status, o.payment_status, o.created_at, o.paid_at,
                   u.display_name as buyer_name, s.display_name as seller_name
            FROM orders o
            LEFT JOIN users u ON o.buyer_id = u.user_id
            LEFT JOIN users s ON o.seller_id = s.user_id
            {where_clause}
            ORDER BY o.created_at DESC
            LIMIT ? OFFSET ?
        ''', (*params, limit, offset))
        
        orders = []
        for row in cursor.fetchall():
            orders.append({
                "id": row[0],
                "order_no": row[1],
                "buyer_id": row[2],
                "seller_id": row[3],
                "total_amount_cents": row[4],
                "currency": row[5],
                "status": row[6],
                "payment_status": row[7],
                "created_at": row[8],
                "paid_at": row[9],
                "buyer_name": row[10],
                "seller_name": row[11]
            })
        
        # 获取总数
        cursor.execute(f'''
            SELECT COUNT(*) FROM orders o {where_clause}
        ''', params)
        
        total = cursor.fetchone()[0]
        
        return {
            "status": "success",
            "orders": orders,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()
