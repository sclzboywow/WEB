#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付相关API路由
包含支付账户绑定、平台配置、支付处理等功能
"""

import sqlite3
import time
from fastapi import APIRouter, Query, Header, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional

from services.db import init_sync_db
from services.payment_service import (
    bind_payment_account, 
    load_platform_payment_config, 
    save_platform_payment_config,
    process_payment_transaction
)
from services.payment_service import query_alipay_trade
from services.order_service import process_payment_callback
from services.db import init_sync_db
import sqlite3
from api.deps import get_current_user

router = APIRouter(prefix="/api/payment", tags=["Payment"])

# 支付账户管理
@router.post("/bind")
async def api_payment_bind(payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """绑定支付账户"""
    user_id = str(user.get("user_id") or "")
    provider = (payload.get("provider") or "").strip()
    account_no = (payload.get("account_no") or "").strip()
    account_name = (payload.get("account_name") or "").strip()
    
    resp = bind_payment_account(
        user_id=user_id,
        provider=provider,
        account_no=account_no,
        account_name=account_name
    )
    
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

@router.get("/list")
async def api_payment_list(user: Dict[str, Any] = Depends(get_current_user)):
    """获取用户支付账户列表"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT id, provider, account_no, account_name, status, verified_at, created_at
            FROM payment_accounts
            WHERE user_id = ? AND deleted_at IS NULL
            ORDER BY created_at DESC
        ''', (user.get("user_id"),))
        
        rows = cursor.fetchall()
        items = []
        
        for row in rows:
            items.append({
                "id": row[0],
                "provider": row[1],
                "account_no": row[2],
                "account_name": row[3],
                "status": row[4],
                "verified_at": row[5],
                "created_at": row[6]
            })
        
        return JSONResponse({
            "status": "success",
            "items": items,
            "total": len(items)
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.post("/verify")
async def api_payment_verify(payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """审核支付账户"""
    account_id = payload.get("account_id")
    status = payload.get("status")
    remark = payload.get("remark", "")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    operator_id = user.get("user_id") or "admin"
    
    if not account_id or not status:
        return JSONResponse({"status": "error", "message": "missing parameters"}, status_code=400)
    
    if status not in ["verified", "rejected"]:
        return JSONResponse({"status": "error", "message": "invalid status"}, status_code=400)
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 检查账户是否存在且状态为pending
        cursor.execute('''
            SELECT user_id, status FROM payment_accounts 
            WHERE id = ? AND deleted_at IS NULL
        ''', (account_id,))
        
        account_row = cursor.fetchone()
        if not account_row:
            return JSONResponse({"status": "error", "message": "account not found"}, status_code=404)
        
        user_id, current_status = account_row
        
        if current_status != "pending":
            return JSONResponse({"status": "error", "message": "account already processed"}, status_code=400)
        
        # 更新账户状态
        if status == "verified":
            cursor.execute('''
                UPDATE payment_accounts 
                SET status = 'verified', verified_at = ?, updated_at = ?
                WHERE id = ?
            ''', (time.time(), time.time(), account_id))
            
            # 自动升级用户角色为premium
            cursor.execute('''
                UPDATE users 
                SET role = 'premium'
                WHERE user_id = ? AND role = 'basic'
            ''', (user_id,))
        else:
            cursor.execute('''
                UPDATE payment_accounts 
                SET status = 'rejected', updated_at = ?
                WHERE id = ?
            ''', (time.time(), account_id))
        
        # 记录审计日志
        cursor.execute('''
            INSERT INTO payment_account_logs (account_id, action, status, remark, operator_id)
            VALUES (?, 'verify', ?, ?, ?)
        ''', (account_id, status, remark, operator_id))
        
        conn.commit()
        
        return JSONResponse({
            "status": "success",
            "message": f"account {status} successfully"
        })
        
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)
    finally:
        conn.close()

@router.post("/disable")
async def api_payment_disable(payload: Dict[str, Any]):
    """禁用支付账户"""
    account_id = payload.get("account_id")
    remark = payload.get("remark", "")
    operator_id = payload.get("operator_id", "admin")
    
    if not account_id:
        return JSONResponse({"status": "error", "message": "missing account_id"}, status_code=400)
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        cursor.execute('''
            UPDATE payment_accounts 
            SET status = 'disabled', updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
        ''', (time.time(), account_id))
        
        if cursor.rowcount == 0:
            return JSONResponse({"status": "error", "message": "account not found"}, status_code=404)
        
        # 记录审计日志
        cursor.execute('''
            INSERT INTO payment_account_logs (account_id, action, status, remark, operator_id)
            VALUES (?, 'disable', 'disabled', ?, ?)
        ''', (account_id, remark, operator_id))
        
        conn.commit()
        
        return JSONResponse({
            "status": "success",
            "message": "account disabled successfully"
        })
        
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)
    finally:
        conn.close()

@router.delete("/{account_id}")
async def api_payment_delete(account_id: int):
    """删除支付账户（软删除）"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        cursor.execute('''
            UPDATE payment_accounts 
            SET deleted_at = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
        ''', (time.time(), time.time(), account_id))
        
        if cursor.rowcount == 0:
            return JSONResponse({"status": "error", "message": "account not found"}, status_code=404)
        
        # 记录审计日志
        cursor.execute('''
            INSERT INTO payment_account_logs (account_id, action, status, remark, operator_id)
            VALUES (?, 'delete', 'deleted', 'Account deleted', 'admin')
        ''', (account_id,))
        
        conn.commit()
        
        return JSONResponse({
            "status": "success",
            "message": "account deleted successfully"
        })
        
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)
    finally:
        conn.close()

@router.get("/logs")
async def api_payment_logs(account_id: Optional[int] = Query(None)):
    """查询支付账户审计日志"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        if account_id:
            cursor.execute('''
                SELECT id, account_id, action, status, remark, operator_id, created_at
                FROM payment_account_logs
                WHERE account_id = ?
                ORDER BY created_at DESC
            ''', (account_id,))
        else:
            cursor.execute('''
                SELECT id, account_id, action, status, remark, operator_id, created_at
                FROM payment_account_logs
                ORDER BY created_at DESC
                LIMIT 100
            ''')
        
        rows = cursor.fetchall()
        logs = []
        
        for row in rows:
            logs.append({
                "id": row[0],
                "account_id": row[1],
                "action": row[2],
                "status": row[3],
                "remark": row[4],
                "operator_id": row[5],
                "created_at": row[6]
            })
        
        return JSONResponse({
            "status": "success",
            "logs": logs,
            "total": len(logs)
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

# 平台支付配置管理
@router.get("/config")
async def api_payment_config_list(user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    """获取平台支付配置列表"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT provider, status, created_at, updated_at
            FROM platform_payment_configs
            ORDER BY created_at DESC
        ''')
        
        rows = cursor.fetchall()
        configs = []
        
        for row in rows:
            configs.append({
                "provider": row[0],
                "status": row[1],
                "created_at": row[2],
                "updated_at": row[3]
            })
        
        return JSONResponse({
            "status": "success",
            "configs": configs
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.post("/config")
async def api_payment_config_save(payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    """保存平台支付配置"""
    provider = payload.get("provider")
    public_key = payload.get("public_key")
    private_key = payload.get("private_key")
    
    if not provider or not public_key or not private_key:
        return JSONResponse({"status": "error", "message": "missing parameters"}, status_code=400)
    
    resp = save_platform_payment_config(provider, public_key, private_key)
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

@router.get("/config/{provider}")
async def api_payment_config_get(provider: str, user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    """获取特定支付渠道的配置状态"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT provider, status, created_at, updated_at
            FROM platform_payment_configs
            WHERE provider = ?
        ''', (provider,))
        
        row = cursor.fetchone()
        if not row:
            return JSONResponse({"status": "error", "message": "config not found"}, status_code=404)
        
        return JSONResponse({
            "status": "success",
            "config": {
                "provider": row[0],
                "status": row[1],
                "created_at": row[2],
                "updated_at": row[3]
            }
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.post("/config/{provider}/test")
async def api_payment_config_test(provider: str, user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    """测试支付配置"""
    config = load_platform_payment_config(provider)
    
    if not config:
        return JSONResponse({"status": "error", "message": "config not found"}, status_code=404)
    
    return JSONResponse({
        "status": "success",
        "message": "config is valid",
        "provider": provider,
        "has_keys": bool(config.get("public_key") and config.get("private_key"))
    })

@router.post("/config/clear")
async def api_payment_config_clear(payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    """清空平台支付配置"""
    provider = payload.get("provider")
    
    if not provider:
        return JSONResponse({"status": "error", "message": "missing provider"}, status_code=400)
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE platform_payment_configs 
            SET status = 'disabled', updated_at = ?
            WHERE provider = ?
        ''', (time.time(), provider))
        
        return JSONResponse({
            "status": "success",
            "message": f"config for {provider} cleared"
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

# 支付交易处理
@router.post("/transaction")
async def api_payment_transaction(payload: Dict[str, Any]):
    """处理支付交易（示例）"""
    provider = payload.get("provider", "alipay")
    amount = payload.get("amount", 0.01)
    order_id = payload.get("order_id", "test_order")
    
    resp = process_payment_transaction(provider, amount, order_id)
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

@router.get("/alipay/query")
async def api_alipay_query(out_trade_no: str):
    """前端轮询调用：查询支付状态，返回 {status, paid, raw}."""
    res = query_alipay_trade(out_trade_no)
    # 若已支付，落库：更新 order_payments 与 orders 等（幂等）
    if res.get('status') == 'success' and res.get('paid'):
        try:
            db_path = init_sync_db()
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute('SELECT amount_cents FROM order_payments WHERE transaction_id = ? LIMIT 1', (out_trade_no,))
            row = cur.fetchone()
            conn.close()
            amount_cents = int(row[0]) if row and row[0] is not None else 0
        except Exception:
            amount_cents = 0
        # 调用已有回调处理逻辑（内部会幂等处理 pending->success，并联动钱包/订单/通知）
        try:
            cb = process_payment_callback(out_trade_no, 'success', amount_cents or 0, message='polled')
            res['callback'] = cb
        except Exception as _e:
            res['callback'] = {"status": "error", "message": str(_e)}
    code = 200 if res.get('status') == 'success' else 400
    return JSONResponse(res, status_code=code)

@router.post("/callback")
async def api_payment_callback(payload: Dict[str, Any], x_callback_secret: str = Header(default=None, alias="X-Callback-Secret")):
    """支付回调处理"""
    from services.order_service import process_payment_callback
    import os
    # 安全开关：默认关闭，仅当 ENABLE_PAYMENT_CALLBACKS=true 时启用
    if (os.getenv('ENABLE_PAYMENT_CALLBACKS') or '').lower() != 'true':
        return JSONResponse({"status": "error", "message": "callbacks disabled"}, status_code=403)
    # 共享密钥校验
    expected = os.getenv('PAY_CALLBACK_SECRET')
    if not expected or x_callback_secret != expected:
        return JSONResponse({"status": "error", "message": "forbidden"}, status_code=403)
    
    transaction_id = payload.get("transaction_id")
    status = payload.get("status")
    amount_cents = payload.get("amount_cents")
    message = payload.get("message")
    
    # 更稳健的参数校验，避免 all([...]) 带来的布尔短路歧义
    if transaction_id is None or status is None or amount_cents is None:
        # 调试输出：返回收到的字段，便于定位前端/调用端问题
        return JSONResponse({
            "status": "error",
            "message": "missing parameters",
            "received": {
                "transaction_id": transaction_id,
                "status": status,
                "amount_cents": amount_cents,
                "message": message
            }
        }, status_code=400)
    
    resp = process_payment_callback(transaction_id, status, int(amount_cents), message)
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)
