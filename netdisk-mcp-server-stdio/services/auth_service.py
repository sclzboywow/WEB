#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证服务层
包含用户注册、登录、会话管理等功能
"""

import sqlite3
import secrets
import time
from typing import Dict, Any, Optional
from .db import init_sync_db

def upsert_user(user_id: str, display_name: Optional[str] = None,
                avatar_url: Optional[str] = None) -> Dict[str, Any]:
    """
    注册或更新用户信息。扫码成功后调用。
    """
    if not user_id:
        return {"status": "error", "message": "missing user_id"}

    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    now = time.time()

    try:
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None

        if exists:
            cursor.execute('''
                UPDATE users
                SET display_name = COALESCE(?, display_name),
                    avatar_url = COALESCE(?, avatar_url),
                    last_login_at = ?
                WHERE user_id = ?
            ''', (display_name, avatar_url, now, user_id))
            message = "user updated"
        else:
            cursor.execute('''
                INSERT INTO users (user_id, display_name, avatar_url, role, registered_at, last_login_at)
                VALUES (?, ?, ?, 'basic', ?, ?)
            ''', (user_id, display_name, avatar_url, now, now))
            message = "user created"

        conn.commit()
        return {"status": "success", "message": message}

    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def create_session(user_id: str, ttl_seconds: int = 7 * 24 * 3600,
                   user_agent: Optional[str] = None,
                   ip_address: Optional[str] = None) -> Dict[str, Any]:
    """
    为指定用户创建平台会话。返回 session_id 和过期时间。
    """
    if not user_id:
        return {"status": "error", "message": "missing user_id"}

    session_id = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + ttl_seconds

    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO sessions (session_id, user_id, created_at, expires_at,
                                  user_agent, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, user_id, now, expires_at, user_agent, ip_address))
        conn.commit()
        return {
            "status": "success",
            "session_id": session_id,
            "expires_at": expires_at
        }
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def verify_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    验证session并返回用户信息
    """
    if not session_id:
        return None
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT s.user_id, s.expires_at, u.display_name, u.avatar_url, u.role, u.registered_at, u.last_login_at
            FROM sessions s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.session_id = ?
        ''', (session_id,))
        
        row = cursor.fetchone() 
        if not row:
            return None
        
        user_id, expires_at, display_name, avatar_url, role, registered_at, last_login_at = row
        
        if expires_at and expires_at < time.time():
            return None
            
        return {
            "user_id": user_id,
            "expires_at": expires_at,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "role": role,
            "registered_at": registered_at,
            "last_login_at": last_login_at
        }
        
    except Exception:
        return None
    finally:
        conn.close()
