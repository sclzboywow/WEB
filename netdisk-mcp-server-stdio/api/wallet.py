#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钱包管理API路由
包含卖家收益、提现申请、钱包查询等功能
"""

import sqlite3
from fastapi import APIRouter, Query, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional

from services.db import init_sync_db
from api.deps import get_current_user
from services.wallet_service import (
    create_payout_request, 
    review_payout_request, 
    get_user_wallet
)

router = APIRouter(prefix="/api", tags=["Wallet"])

# 卖家订单列表（为避免与 /api/orders/{order_id} 冲突，提供别名 /api/seller/orders）
@router.get("/orders/seller")
async def api_orders_seller(status: Optional[str] = Query(None),
                           limit: int = Query(20, ge=1, le=200),
                           offset: int = Query(0, ge=0),
                           user: Dict[str, Any] = Depends(get_current_user)):
    """获取卖家的订单列表"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        where_clause = "WHERE seller_id = ?"
        params = [user.get("user_id")]
        
        if status:
            where_clause += " AND status = ?"
            params.append(status)
        
        cursor.execute(f'''\
            SELECT id, order_no, buyer_id, total_amount_cents, platform_fee_cents,
                   seller_amount_cents, currency, status, payment_status,
                   created_at, updated_at, paid_at, delivered_at, completed_at
            FROM orders
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (*params, limit, offset))
        
        rows = cursor.fetchall()
        orders = []
        
        for row in rows:
            orders.append({
                "id": row[0],
                "order_no": row[1],
                "buyer_id": row[2],
                "total_amount_cents": row[3],
                "total_amount_yuan": row[3] / 100,
                "platform_fee_cents": row[4],
                "platform_fee_yuan": row[4] / 100,
                "seller_amount_cents": row[5],
                "seller_amount_yuan": row[5] / 100,
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
        cursor.execute(f'''\
            SELECT COUNT(*) FROM orders {where_clause}
        ''', params)
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

@router.get("/seller/orders")
async def api_orders_seller_alias(status: Optional[str] = Query(None),
                                  limit: int = Query(20, ge=1, le=200),
                                  offset: int = Query(0, ge=0),
                                  user: Dict[str, Any] = Depends(get_current_user)):
    """别名：避免与 /api/orders/{order_id} 动态路由冲突"""
    return await api_orders_seller(status=status, limit=limit, offset=offset, user=user)

# 钱包信息
@router.get("/wallet/me")
async def api_wallet_info(user: Dict[str, Any] = Depends(get_current_user)):
    """获取用户钱包信息"""
    resp = get_user_wallet(user.get("user_id"))
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

# 提现申请
@router.post("/payouts")
async def api_payouts_create(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    """创建提现申请"""
    user_id = user.get("user_id")
    payload: Dict[str, Any] = {}
    try:
        payload = await request.json()
    except Exception:
        try:
            form = await request.form()
            payload = {k: form.get(k) for k in form.keys()}
        except Exception:
            payload = {}

    amount_cents = payload.get("amount_cents")
    method = payload.get("method")
    account_info = payload.get("account_info")
    remark = payload.get("remark", "")
    try:
        print(f"[payouts.create] user_id={user_id} payload={{'amount_cents':{amount_cents},'method':{method},'account_info':{account_info},'remark':{remark}}}")
    except Exception:
        pass
    
    if not user_id:
        print("[payouts.create] error: unauthorized: missing user")
        return JSONResponse({"status": "error", "message": "unauthorized: missing user"}, status_code=401)
    if method is None or method == "":
        print("[payouts.create] error: missing parameter: method")
        return JSONResponse({"status": "error", "message": "missing parameter: method"}, status_code=400)
    if account_info is None or str(account_info).strip() == "":
        print("[payouts.create] error: missing parameter: account_info")
        return JSONResponse({"status": "error", "message": "missing parameter: account_info"}, status_code=400)
    try:
        amount_cents = int(amount_cents)
    except Exception:
        print("[payouts.create] error: invalid amount_cents")
        return JSONResponse({"status": "error", "message": "invalid amount_cents"}, status_code=400)
    if amount_cents < 1:
        print("[payouts.create] error: amount must be at least 1 cent")
        return JSONResponse({"status": "error", "message": "amount must be at least 1 cent"}, status_code=400)
    
    resp = create_payout_request(user_id, amount_cents, method, account_info, remark)
    if resp.get("status") != "success":
        try:
            print(f"[payouts.create] service_error: {resp}")
        except Exception:
            pass
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

# 卖家提现记录
@router.get("/payouts/mine")
async def api_payouts_mine(status: Optional[str] = Query(None), user: Dict[str, Any] = Depends(get_current_user)):
    """获取用户的提现记录"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        where_clause = "WHERE user_id = ?"
        params = [user.get("user_id")]
        
        if status:
            where_clause += " AND status = ?"
            params.append(status)
        
        cursor.execute(f'''\
            SELECT id, amount_cents, status, method, account_info, remark,
                   created_at, processed_at
            FROM payout_requests
            {where_clause}
            ORDER BY created_at DESC
        ''', params)
        
        rows = cursor.fetchall()
        payouts = []
        
        for row in rows:
            payouts.append({
                "id": row[0],
                "amount_cents": row[1],
                "amount_yuan": row[1] / 100,
                "status": row[2],
                "method": row[3],
                "account_info": row[4],
                "remark": row[5],
                "created_at": row[6],
                "processed_at": row[7]
            })
        
        return JSONResponse({
            "status": "success",
            "payouts": payouts,
            "total": len(payouts)
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

# 管理员提现审核列表
@router.get("/payouts")
async def api_payouts_list(status: Optional[str] = Query(None),
                          limit: int = Query(20, ge=1, le=200),
                          offset: int = Query(0, ge=0),
                          user: Dict[str, Any] = Depends(get_current_user)):
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='forbidden')
    """管理员查看提现申请列表"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        where_clause = ""
        params = []
        
        if status:
            where_clause = "WHERE status = ?"
            params.append(status)
        
        cursor.execute(f'''\
            SELECT pr.id, pr.user_id, pr.amount_cents, pr.status, pr.method, 
                   pr.account_info, pr.remark, pr.created_at, pr.processed_at,
                   u.display_name
            FROM payout_requests pr
            LEFT JOIN users u ON pr.user_id = u.user_id
            {where_clause}
            ORDER BY pr.created_at DESC
            LIMIT ? OFFSET ?
        ''', (*params, limit, offset))
        
        rows = cursor.fetchall()
        payouts = []
        
        for row in rows:
            payouts.append({
                "id": row[0],
                "user_id": row[1],
                "user_name": row[9],
                "amount_cents": row[2],
                "amount_yuan": row[2] / 100,
                "status": row[3],
                "method": row[4],
                "account_info": row[5],
                "remark": row[6],
                "created_at": row[7],
                "processed_at": row[8]
            })
        
        # 获取总数
        cursor.execute(f'''\
            SELECT COUNT(*) FROM payout_requests {where_clause}
        ''', params)
        total = cursor.fetchone()[0]
        
        return JSONResponse({
            "status": "success",
            "payouts": payouts,
            "total": total
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

# 管理员提现审核
@router.post("/payouts/{request_id}/review")
async def api_payouts_review(request_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """管理员审核提现申请"""
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='forbidden')
    status = payload.get("status")
    reviewer_id = user.get('user_id')
    remark = payload.get("remark", "")
    
    if not status or not reviewer_id:
        return JSONResponse({"status": "error", "message": "missing parameters"}, status_code=400)
    
    resp = review_payout_request(request_id, reviewer_id, status, remark)
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)
