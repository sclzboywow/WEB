#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户管理API路由
包含用户列表、详情、支付账户管理等功能
"""

import sqlite3
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Optional

from services.db import init_sync_db

router = APIRouter(prefix="/api/users", tags=["Users"])

@router.get("")
async def api_users_list(keyword: Optional[str] = Query(None), 
                        limit: int = Query(20, ge=1, le=200), 
                        offset: int = Query(0, ge=0)):
    """用户列表查询"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        params = []
        where_clause = ""
        
        if keyword:
            where_clause = "WHERE user_id LIKE ? OR display_name LIKE ?"
            kw = f"%{keyword}%"
            params.extend([kw, kw])
        
        cursor.execute(f'''
            SELECT user_id, display_name, avatar_url, role, registered_at, last_login_at
            FROM users
            {where_clause}
            ORDER BY registered_at DESC
            LIMIT ? OFFSET ?
        ''', (*params, limit, offset))
        
        rows = cursor.fetchall()
        users = []
        
        for row in rows:
            users.append({
                "user_id": row[0],
                "display_name": row[1],
                "avatar_url": row[2],
                "role": row[3],
                "registered_at": row[4],
                "last_login_at": row[5]
            })
        
        # 获取总数
        cursor.execute(f'''
            SELECT COUNT(*) FROM users {where_clause}
        ''', params)
        total = cursor.fetchone()[0]
        
        return JSONResponse({
            "status": "success",
            "total": total,
            "users": users
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.get("/{user_id}")
async def api_users_detail(user_id: str):
    """用户详情查询"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT user_id, display_name, avatar_url, role, registered_at, last_login_at
            FROM users
            WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        if not row:
            return JSONResponse({"status": "error", "message": "user not found"}, status_code=404)
        
        # 获取支付账户列表
        cursor.execute('''
            SELECT id, provider, account_no, account_name, status, verified_at, created_at
            FROM payment_accounts
            WHERE user_id = ? AND deleted_at IS NULL
            ORDER BY created_at DESC
        ''', (user_id,))
        
        accounts = []
        for r in cursor.fetchall():
            accounts.append({
                "id": r[0],
                "provider": r[1],
                "account_no": r[2],
                "account_name": r[3],
                "status": r[4],
                "verified_at": r[5],
                "created_at": r[6]
            })
        
        return JSONResponse({
            "status": "success",
            "user": {
                "user_id": row[0],
                "display_name": row[1],
                "avatar_url": row[2],
                "role": row[3],
                "registered_at": row[4],
                "last_login_at": row[5]
            },
            "payment_accounts": accounts
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.put("/{user_id}/role")
async def api_users_update_role(user_id: str, role_data: dict):
    """更新用户角色"""
    new_role = role_data.get("role")
    
    if not new_role:
        return JSONResponse({"status": "error", "message": "缺少角色参数"}, status_code=400)
    
    if new_role not in ["basic", "seller", "admin"]:
        return JSONResponse({"status": "error", "message": "无效的角色类型"}, status_code=400)
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查用户是否存在
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            return JSONResponse({"status": "error", "message": "用户不存在"}, status_code=404)
        
        # 更新角色
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, user_id))
        conn.commit()
        
        return JSONResponse({
            "status": "success",
            "message": f"用户角色已更新为: {new_role}",
            "user_id": user_id,
            "role": new_role
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()
