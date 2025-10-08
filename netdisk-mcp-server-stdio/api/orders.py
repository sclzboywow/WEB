#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订单管理API路由
包含订单创建、支付、查询等功能
"""

import sqlite3
import time
from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional

from services.db import init_sync_db
from api.deps import get_current_user
from services.payment_service import create_alipay_page_pay
from services.order_service import create_order, create_payment_record, apply_refund, review_refund

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.post("")
async def api_orders_create(payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """创建订单"""
    buyer_id = user.get("user_id")
    items = payload.get("items", [])
    
    resp = create_order(buyer_id, items)
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

@router.get("/mine")
async def api_orders_mine(status: Optional[str] = Query(None), user: Dict[str, Any] = Depends(get_current_user)):
    """获取买家的订单列表"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        where_clause = "WHERE buyer_id = ?"
        params = [user.get("user_id")]
        
        if status:
            where_clause += " AND status = ?"
            params.append(status)
        
        cursor.execute(f'''
            SELECT id, order_no, seller_id, total_amount_cents, platform_fee_cents,
                   seller_amount_cents, currency, status, payment_status,
                   created_at, updated_at, paid_at, delivered_at, completed_at,
                   refund_status, refund_requested_at, refund_processed_at, refund_reason
            FROM orders
            {where_clause}
            ORDER BY created_at DESC
        ''', params)
        
        rows = cursor.fetchall()
        orders = []
        
        for row in rows:
            order_id = row[0]
            
            # 获取订单项
            cursor.execute('''
                SELECT oi.id, oi.listing_id, oi.price_cents, oi.quantity, oi.delivered_at,
                       l.title, l.description, l.listing_type
                FROM order_items oi
                LEFT JOIN listings l ON oi.listing_id = l.id
                WHERE oi.order_id = ?
            ''', (order_id,))
            
            items = []
            for item_row in cursor.fetchall():
                items.append({
                    "id": item_row[0],
                    "listing_id": item_row[1],
                    "price_cents": item_row[2],
                    "quantity": item_row[3],
                    "delivered_at": item_row[4],
                    "title": item_row[5],
                    "description": item_row[6],
                    "listing_type": item_row[7]
                })
            
            # 获取支付记录
            cursor.execute('''
                SELECT id, provider, transaction_id, amount_cents, status, paid_at
                FROM order_payments
                WHERE order_id = ?
                ORDER BY created_at DESC
            ''', (order_id,))
            
            payments = []
            for payment_row in cursor.fetchall():
                payments.append({
                    "id": payment_row[0],
                    "provider": payment_row[1],
                    "transaction_id": payment_row[2],
                    "amount_cents": payment_row[3],
                    "status": payment_row[4],
                    "paid_at": payment_row[5]
                })
            
            orders.append({
                "id": row[0],
                "order_no": row[1],
                "seller_id": row[2],
                "total_amount_cents": row[3],
                "platform_fee_cents": row[4],
                "seller_amount_cents": row[5],
                "currency": row[6],
                "status": row[7],
                "payment_status": row[8],
                "created_at": row[9],
                "updated_at": row[10],
                "paid_at": row[11],
                "delivered_at": row[12],
                "completed_at": row[13],
                "refund_status": row[14],
                "refund_requested_at": row[15],
                "refund_processed_at": row[16],
                "refund_reason": row[17],
                "items": items,
                "payments": payments
            })
        
        return JSONResponse({
            "status": "success",
            "orders": orders,
            "total": len(orders)
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.get("/seller")
async def api_orders_seller(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """获取卖家的订单列表（置于动态路由之前，避免被 /{order_id} 捕获）"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        where_clause = "WHERE seller_id = ?"
        params: List[Any] = [user.get("user_id")]

        if status:
            where_clause += " AND status = ?"
            params.append(status)

        cursor.execute(f'''
            SELECT id, order_no, buyer_id, total_amount_cents, platform_fee_cents,
                   seller_amount_cents, currency, status, payment_status,
                   created_at, updated_at, paid_at, delivered_at, completed_at
            FROM orders
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (*params, limit, offset))

        rows = cursor.fetchall()
        orders: List[Dict[str, Any]] = []

        for row in rows:
            orders.append({
                "id": row[0],
                "order_no": row[1],
                "buyer_id": row[2],
                "total_amount_cents": row[3],
                "platform_fee_cents": row[4],
                "seller_amount_cents": row[5],
                "currency": row[6],
                "status": row[7],
                "payment_status": row[8],
                "created_at": row[9],
                "updated_at": row[10],
                "paid_at": row[11],
                "delivered_at": row[12],
                "completed_at": row[13]
            })

        # 获取总数
        cursor.execute(f'''SELECT COUNT(*) FROM orders {where_clause}''', params)
        total = cursor.fetchone()[0]

        return JSONResponse({
            "status": "success",
            "orders": orders,
            "total": total
        })

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.get("/{order_id}")
async def api_orders_detail(order_id: int):
    """获取订单详情"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT id, order_no, buyer_id, seller_id, total_amount_cents, 
                   platform_fee_cents, seller_amount_cents, currency, status, 
                   payment_status, created_at, updated_at, paid_at, delivered_at, 
                   completed_at,
                   refund_status, refund_requested_at, refund_processed_at, refund_reason
            FROM orders
            WHERE id = ?
        ''', (order_id,))
        
        row = cursor.fetchone()
        if not row:
            return JSONResponse({"status": "error", "message": "order not found"}, status_code=404)
        
        # 获取订单项
        cursor.execute('''
            SELECT oi.id, oi.listing_id, oi.price_cents, oi.quantity, oi.delivered_at,
                   l.title, l.description, l.listing_type
            FROM order_items oi
            LEFT JOIN listings l ON oi.listing_id = l.id
            WHERE oi.order_id = ?
        ''', (order_id,))
        
        items = []
        for item_row in cursor.fetchall():
            items.append({
                "id": item_row[0],
                "listing_id": item_row[1],
                "price_cents": item_row[2],
                "quantity": item_row[3],
                "delivered_at": item_row[4],
                "title": item_row[5],
                "description": item_row[6],
                "listing_type": item_row[7]
            })
        
        # 获取支付记录
        cursor.execute('''
            SELECT id, provider, transaction_id, amount_cents, status, paid_at, created_at
            FROM order_payments
            WHERE order_id = ?
            ORDER BY created_at DESC
        ''', (order_id,))
        
        payments = []
        for payment_row in cursor.fetchall():
            payments.append({
                "id": payment_row[0],
                "provider": payment_row[1],
                "transaction_id": payment_row[2],
                "amount_cents": payment_row[3],
                "status": payment_row[4],
                "paid_at": payment_row[5],
                "created_at": payment_row[6]
            })
        
        return JSONResponse({
            "status": "success",
            "order": {
                "id": row[0],
                "order_no": row[1],
                "buyer_id": row[2],
                "seller_id": row[3],
                "total_amount_cents": row[4],
                "platform_fee_cents": row[5],
                "seller_amount_cents": row[6],
                "currency": row[7],
                "status": row[8],
                "payment_status": row[9],
                "created_at": row[10],
                "updated_at": row[11],
                "paid_at": row[12],
                "delivered_at": row[13],
                "completed_at": row[14],
                "refund_status": row[15],
                "refund_requested_at": row[16],
                "refund_processed_at": row[17],
                "refund_reason": row[18],
                "items": items,
                "payments": payments
            }
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.post("/{order_id}/pay")
async def api_orders_pay(order_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """发起支付"""
    provider = payload.get("provider", "alipay")
    payment_method = payload.get("payment_method", "alipay")
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查订单状态与归属
        cursor.execute('''
            SELECT id, total_amount_cents, status, buyer_id FROM orders WHERE id = ?
        ''', (order_id,))
        
        order_row = cursor.fetchone()
        if not order_row:
            return JSONResponse({"status": "error", "message": "order not found"}, status_code=404)
        
        # 验证订单归属：仅买家本人可支付
        buyer_id = order_row[3]
        if user.get("user_id") != buyer_id:
            return JSONResponse({"status": "error", "message": "forbidden"}, status_code=403)

        if order_row[2] != "pending":
            return JSONResponse({"status": "error", "message": "order not available for payment"}, status_code=400)
        
        amount_cents = order_row[1]
        
        # 创建支付记录
        transaction_id = payload.get("transaction_id", f"txn_{int(time.time())}")
        resp = create_payment_record(order_id, provider, transaction_id, amount_cents)
        if resp.get("status") != "success":
            return JSONResponse(resp, status_code=400)
        
        payment_id = resp["payment_id"]
        # 使用本地生成的 transaction_id，避免返回结构缺失导致 KeyError
        
        # 生成支付宝网页支付链接（无回调，前端轮询）
        subject = f"订单{order_id}"
        amount_yuan = max(0.01, round(amount_cents / 100.0, 2))
        pay_res = create_alipay_page_pay(subject=subject, total_amount=amount_yuan, out_trade_no=transaction_id)
        if pay_res.get('status') != 'success':
            return JSONResponse({"status": "error", "message": pay_res.get('message', 'failed to create pay url')}, status_code=500)
        return JSONResponse({
            "status": "success",
            "payment_id": payment_id,
            "transaction_id": transaction_id,
            "amount_cents": amount_cents,
            "provider": provider,
            "payment_url": pay_res.get('pay_url'),
            "message": "支付链接已生成，请在前端打开或展示二维码"
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.post("/{order_id}/refund")
async def api_orders_refund_apply(order_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """买家申请退款"""
    buyer_id = user.get("user_id")
    reason = payload.get("reason") or ""
    if not buyer_id:
        return JSONResponse({"status":"error","message":"buyer_id required"}, status_code=400)
    resp = apply_refund(order_id, buyer_id, reason)
    return JSONResponse(resp, status_code=(200 if resp.get('status')=='success' else 400))

@router.post("/{order_id}/refund/review")
async def api_orders_refund_review(order_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """管理员/客服审核退款（传 refund_id）"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    refund_id = payload.get("refund_id")
    reviewer_id = user.get("user_id") or "admin"
    status = payload.get("status")
    remark = payload.get("remark") or ""
    if not refund_id or status not in ("approved","rejected"):
        return JSONResponse({"status":"error","message":"invalid params"}, status_code=400)
    resp = review_refund(int(refund_id), reviewer_id, status, remark)
    return JSONResponse(resp, status_code=(200 if resp.get('status')=='success' else 400))

# 购买记录API
@router.get("/purchases/mine")
async def api_purchases_mine(user: Dict[str, Any] = Depends(get_current_user)):
    """获取买家的已购文件列表"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT up.id, up.order_id, up.listing_id, up.file_path, 
                   up.download_count, up.last_accessed_at, up.created_at,
                   l.title, l.description, l.listing_type,
                   o.order_no, o.status as order_status
            FROM user_purchases up
            LEFT JOIN listings l ON up.listing_id = l.id
            LEFT JOIN orders o ON up.order_id = o.id
            WHERE up.buyer_id = ?
            ORDER BY up.created_at DESC
        ''', (user.get("user_id"),))
        
        rows = cursor.fetchall()
        purchases = []
        
        for row in rows:
            purchases.append({
                "id": row[0],
                "order_id": row[1],
                "order_no": row[10],
                "listing_id": row[2],
                "title": row[7],
                "description": row[8],
                "listing_type": row[9],
                "file_path": row[3],
                "download_count": row[4],
                "last_accessed_at": row[5],
                "created_at": row[6],
                "order_status": row[11]
            })
        
        return JSONResponse({
            "status": "success",
            "purchases": purchases,
            "total": len(purchases)
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()
