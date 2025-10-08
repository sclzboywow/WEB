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
CLIENT_ID = os.getenv('BAIDU_CLIENT_ID') or os.getenv('BAIDU_NETDISK_APP_KEY')
CLIENT_SECRET = os.getenv('BAIDU_CLIENT_SECRET') or os.getenv('BAIDU_NETDISK_SECRET_KEY')
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
        # 百度网盘API使用access_token作为参数，不是Bearer认证
        params = {
            "method": "uinfo",
            "access_token": access_token
        }
        response = requests.get(
            "https://pan.baidu.com/rest/2.0/xpan/nas",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        print(f"百度API返回的用户信息: {result}")
        return result
    except Exception as e:
        print(f"获取用户信息失败: {e}")
        return {"error": str(e)}

@router.get("/url")
async def oauth_url():
    """获取OAuth授权URL"""
    if not CLIENT_ID:
        return JSONResponse({"status": "error", "message": "CLIENT_ID not configured"}, status_code=500)
    
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
    
    return JSONResponse({
        "status": "success",
        "auth_url": auth_url,
        "state": state
    })

@router.get("/login")
async def oauth_login():
    """OAuth登录入口（重定向到授权页面）"""
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
    # 添加调试信息
    print(f"OAuth回调调试信息:")
    print(f"  URL: {request.url}")
    print(f"  Query params: {request.query_params}")
    print(f"  code: {code}")
    print(f"  state: {state}")
    print(f"  error: {error}")
    
    if error:
        return HTMLResponse(f"<h1>授权失败</h1><p>错误: {error}</p>")
    
    if not code:
        # 显示更多调试信息
        debug_info = f"""
        <h1>授权失败</h1>
        <p>未收到授权码</p>
        <h3>调试信息:</h3>
        <p>URL: {request.url}</p>
        <p>Query params: {dict(request.query_params)}</p>
        <p>code: {code}</p>
        <p>state: {state}</p>
        <p>error: {error}</p>
        """
        return HTMLResponse(debug_info)
    
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
        print(f"OAuth回调获取到的用户信息: {user_info}")
        print(f"用户信息类型: {type(user_info)}")
        print(f"用户信息是否包含errno: {'errno' in user_info if isinstance(user_info, dict) else False}")
        if isinstance(user_info, dict) and 'errno' in user_info:
            print(f"errno值: {user_info['errno']}")
        
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
        
        if isinstance(user_info, dict) and 'errno' in user_info and user_info['errno'] == 0:
            # 百度API成功返回，使用uk作为用户ID
            user_id = user_info.get('uk')
            if user_id is not None:
                user_id = str(user_id)
        else:
            # 如果API失败，尝试从token中获取
            user_id = token.get('userid') or token.get('uid')
            if user_id is not None:
                user_id = str(user_id)
        
        print(f"提取的用户ID: {user_id}")
        print(f"用户信息类型: {type(user_info)}")
        print(f"用户信息内容: {user_info}")
        
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
        
        # 返回友好的成功页面
        # 调试信息
        print(f"准备显示的用户信息: {user_info}")
        print(f"用户ID: {user_id}")
        
        # 安全地获取用户名
        if isinstance(user_info, dict) and 'errno' in user_info and user_info['errno'] == 0:
            # 百度API成功返回
            user_name = user_info.get('baidu_name') or user_info.get('netdisk_name') or '用户'
        else:
            user_name = '用户'
        
        # 确保user_id有值
        if not user_id:
            user_id = '未知'
        
        # 获取实际的授权时间
        auth_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"最终显示的用户名: {user_name}")
        print(f"最终显示的用户ID: {user_id}")
        print(f"授权时间: {auth_time}")
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>授权成功 - 百度网盘MCP服务</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <style>
                .success-animation {{
                    animation: successPulse 2s ease-in-out;
                }}
                @keyframes successPulse {{
                    0% {{ transform: scale(1); }}
                    50% {{ transform: scale(1.05); }}
                    100% {{ transform: scale(1); }}
                }}
                .fade-in {{
                    animation: fadeIn 1s ease-in;
                }}
                @keyframes fadeIn {{
                    from {{ opacity: 0; transform: translateY(20px); }}
                    to {{ opacity: 1; transform: translateY(0); }}
                }}
            </style>
        </head>
        <body class="min-h-screen bg-gradient-to-br from-green-50 to-blue-50 flex items-center justify-center p-4">
            <div class="max-w-md w-full bg-white rounded-2xl shadow-xl p-8 text-center fade-in">
                <!-- 成功图标 -->
                <div class="success-animation mb-6">
                    <div class="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto">
                        <svg class="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                    </div>
                </div>
                
                <!-- 标题 -->
                <h1 class="text-2xl font-bold text-gray-800 mb-2">🎉 授权成功！</h1>
                <p class="text-gray-600 mb-6">欢迎回来，{user_name}！</p>
                
                <!-- 状态信息 -->
                <div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                    <div class="flex items-center justify-center text-green-700 mb-2">
                        <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                        </svg>
                        <span class="font-medium">授权完成</span>
                    </div>
                    <p class="text-sm text-green-600">已成功获取访问令牌并创建平台会话</p>
                </div>
                
                <!-- 用户信息 -->
                <div class="bg-gray-50 rounded-lg p-4 mb-6 text-left">
                    <h3 class="font-medium text-gray-800 mb-3">用户信息</h3>
                    <div class="space-y-2 text-sm">
                        <div class="flex justify-between">
                            <span class="text-gray-600">用户名：</span>
                            <span class="font-medium">{user_name}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-600">用户ID：</span>
                            <span class="font-mono text-xs">{user_id}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-600">授权时间：</span>
                            <span class="text-xs">{auth_time}</span>
                        </div>
                    </div>
                </div>
                
                <!-- 操作按钮 -->
                <div class="space-y-3">
                    <button onclick="window.close()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg transition-colors">
                        关闭窗口
                    </button>
                    <button onclick="window.location.href='/src/admin.html'" class="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium py-2 px-4 rounded-lg transition-colors">
                        进入管理后台
                    </button>
                </div>
                
                <!-- 提示信息 -->
                <p class="text-xs text-gray-500 mt-6">
                    授权信息已保存，您可以安全地关闭此窗口
                </p>
            </div>
            
            <script>
                // 3秒后自动关闭窗口（如果用户没有操作）
                setTimeout(() => {{
                    if (confirm('授权已完成，是否关闭此窗口？')) {{
                        window.close();
                    }}
                }}, 3000);
            </script>
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

@router.get("/test-user-info")
async def test_user_info():
    """测试用户信息获取"""
    try:
        # 读取现有的auth_result.json
        auth_file = os.path.join(BASE_DIR, "auth_result.json")
        if os.path.exists(auth_file):
            with open(auth_file, 'r', encoding='utf-8') as f:
                auth_data = json.load(f)
            
            token = auth_data.get('token', {})
            access_token = token.get('access_token')
            
            if access_token:
                user_info = fetch_user_info(access_token)
                return JSONResponse({
                    "status": "success",
                    "user_info": user_info,
                    "token_info": {
                        "access_token": access_token[:20] + "...",
                        "expires_in": token.get('expires_in')
                    }
                })
            else:
                return JSONResponse({"status": "error", "message": "No access token found"})
        else:
            return JSONResponse({"status": "error", "message": "No auth result file found"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

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
