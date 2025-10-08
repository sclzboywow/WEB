#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证相关API路由
包含OAuth登录、回调、会话管理等功能
"""

import os
import json
import hashlib
import base64
from urllib.parse import urlencode
import requests
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from dotenv import load_dotenv
import time
from typing import Dict, Any, Optional

from services.auth_service import upsert_user, create_session, verify_session
from services.db import init_sync_db

# 加载环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# 百度网盘API配置
CLIENT_ID = os.getenv('BAIDU_CLIENT_ID')
CLIENT_SECRET = os.getenv('BAIDU_CLIENT_SECRET')
REDIRECT_URI = os.getenv('BAIDU_REDIRECT_URI', 'http://localhost:8000/oauth/callback')

# 全局状态存储（临时方案）
auth_state = {
    "authorized": False,
    "last_user_id": None,
    "last_session": None
}

router = APIRouter(prefix="/oauth", tags=["OAuth"])

def fetch_user_info(access_token: str) -> Dict[str, Any]:
    """获取用户信息"""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            "https://pan.baidu.com/rest/2.0/xpan/nas",
            params={"method": "uinfo"},
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"获取用户信息失败: {e}")
        return {"error": str(e)}

@router.get("/login")
async def oauth_login():
    """OAuth登录入口"""
    if not CLIENT_ID:
        return JSONResponse({"error": "CLIENT_ID not configured"}, status_code=500)
    
    # 生成state参数防止CSRF攻击
    state = hashlib.md5(f"{time.time()}".encode()).hexdigest()
    
    # 构建授权URL
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "basic netdisk",
        "state": state
    }
    
    auth_url = f"https://openapi.baidu.com/oauth/2.0/authorize?{urlencode(params)}"
    
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def oauth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """OAuth回调处理"""
    if error:
        return HTMLResponse(f"<h1>授权失败</h1><p>错误: {error}</p>")
    
    if not code:
        return HTMLResponse("<h1>授权失败</h1><p>未收到授权码</p>")
    
    try:
        # 换取access_token
        token_params = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI
        }
        
        response = requests.post(
            "https://openapi.baidu.com/oauth/2.0/token",
            data=token_params,
            timeout=30
        )
        response.raise_for_status()
        token = response.json()
        
        if "error" in token:
            return HTMLResponse(f"<h1>Token获取失败</h1><p>错误: {token['error']}</p>")
        
        # 获取用户信息
        user_info = fetch_user_info(token["access_token"])
        
        # 保存认证结果
        auth_result = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "token": token,
            "user_info": user_info
        }
        
        with open(os.path.join(BASE_DIR, "auth_result.json"), "w", encoding="utf-8") as f:
            json.dump(auth_result, f, ensure_ascii=False, indent=2)
        
        # === 新增: 注册/更新用户 + 创建平台会话 ===
        user_id = None
        session_payload = None
        
        if isinstance(user_info, dict):
            user_id = user_info.get('uk') or user_info.get('userid') or token.get('userid') or token.get('uid')
            if user_id is not None:
                user_id = str(user_id)
        
        if user_id:
            upsert_user(
                user_id=user_id,
                display_name=user_info.get('baidu_name') if isinstance(user_info, dict) else None,
                avatar_url=user_info.get('avatar', '') if isinstance(user_info, dict) else None
            )
            
            session_payload = create_session(
                user_id=user_id,
                user_agent=request.headers.get('user-agent'),
                ip_address=(request.client.host if request.client else None)
            )
        else:
            session_payload = {"status": "error", "message": "无法识别用户ID"}
        
        auth_state["authorized"] = True
        auth_state["last_user_id"] = user_id
        auth_state["last_session"] = session_payload
        
        # 更新combined结果
        combined = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "token": token,
            "user_info": user_info,
            "session": session_payload,
        }
        
        with open(os.path.join(BASE_DIR, "auth_result.json"), "w", encoding="utf-8") as f:
            json.dump(combined, f, ensure_ascii=False, indent=2)
        
        # 返回成功页面
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>授权成功</title>
            <meta charset="utf-8">
        </head>
        <body>
            <h1>✅ 授权成功</h1>
            <p>授权完成，已写入 Token 并创建平台会话。</p>
            {"<pre style='background:#f5f5f5;padding:12px;border-radius:6px;'>Session: " + json.dumps(session_payload, ensure_ascii=False, indent=2) + "</pre>" if session_payload else ""}
            <p>可以关闭此窗口，回到控制台继续操作。</p>
        </body>
        </html>
        """
        
        return HTMLResponse(html_content)
        
    except Exception as e:
        return HTMLResponse(f"<h1>授权失败</h1><p>错误: {str(e)}</p>")

@router.get("/status")
async def oauth_status():
    """获取OAuth状态"""
    return JSONResponse({
        "authorized": auth_state["authorized"],
        "last_user_id": auth_state["last_user_id"],
        "has_session": auth_state["last_session"] is not None
    })

@router.post("/mock-login")
async def oauth_mock_login(payload: Dict[str, Any]):
    """测试用：无需真实OAuth，快速创建会话。
    payload: { user_id: str, role?: "basic"|"seller"|"admin", display_name?: str }
    """
    user_id = str(payload.get("user_id", "")).strip()
    role = payload.get("role", "basic")
    display_name = payload.get("display_name", None)
    if not user_id:
        return JSONResponse({"status": "error", "message": "missing user_id"}, status_code=400)

    # 写入/更新用户（upsert_user 不接受 role，后续单独更新）
    upsert_user(
        user_id=user_id,
        display_name=display_name,
        avatar_url=None
    )

    # 创建平台会话
    session_payload = create_session(
        user_id=user_id,
        user_agent="mock-client",
        ip_address=None
    )

    # 更新角色
    try:
        db_path = init_sync_db()
        import sqlite3
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        conn.commit()
        conn.close()
    except Exception:
        pass

    auth_state["authorized"] = True
    auth_state["last_user_id"] = user_id
    auth_state["last_session"] = session_payload

    return JSONResponse({
        "status": "success",
        "user_id": user_id,
        "role": role,
        "session": session_payload
    })

@router.get("/mock-login")
async def oauth_mock_login_get(user_id: str, role: str = "basic", display_name: str = None):
    return await oauth_mock_login({"user_id": user_id, "role": role, "display_name": display_name})

@router.post("/reset")
async def oauth_reset():
    """重置OAuth状态"""
    global auth_state
    auth_state = {
        "authorized": False,
        "last_user_id": None,
        "last_session": None
    }
    
    # 删除认证结果文件
    auth_file = os.path.join(BASE_DIR, "auth_result.json")
    if os.path.exists(auth_file):
        os.remove(auth_file)
    
    return JSONResponse({"status": "success", "message": "OAuth state reset"})

# 会话管理API
@router.get("/session/latest")
async def auth_session_latest():
    """返回最近一次OAuth成功后生成的会话信息"""
    session_payload = auth_state.get("last_session")
    user_id = auth_state.get("last_user_id")
    
    if not session_payload:
        return JSONResponse({"status": "error", "message": "no recent session"}, status_code=404)
    
    # 获取用户详细信息，包括role
    user_info = None
    if user_id:
        user_info = verify_session(session_payload.get("session_id", ""))
    
    return JSONResponse({
        "status": "success",
        "user_id": user_id,
        "session": session_payload,
        "role": user_info.get("role") if user_info else None,
        "display_name": user_info.get("display_name") if user_info else None,
        "avatar_url": user_info.get("avatar_url") if user_info else None
    })

# 用户认证API
@router.get("/api/users/me")
async def api_users_me(session_id: str = Query(...)):
    """通过session_id查询当前用户信息"""
    if not session_id:
        return JSONResponse({"status": "error", "message": "missing session_id"}, status_code=400)
    
    user_info = verify_session(session_id)
    if not user_info:
        return JSONResponse({"status": "error", "message": "session not found or expired"}, status_code=404)
    
    return JSONResponse({
        "status": "success",
        "user": {
            "user_id": user_info["user_id"],
            "display_name": user_info["display_name"],
            "avatar_url": user_info["avatar_url"],
            "role": user_info["role"],
            "registered_at": user_info["registered_at"],
            "last_login_at": user_info["last_login_at"]
        },
        "session": {
            "session_id": session_id,
            "expires_at": user_info["expires_at"]
        }
    })
