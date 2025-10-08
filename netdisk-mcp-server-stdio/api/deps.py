#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用依赖：基于会话的用户鉴权。
优先从 Header `X-Session-Id` 获取；其次从 Cookie `session_id` 获取。
验证失败抛 401。
"""

from fastapi import Depends, Header, Cookie, HTTPException
from typing import Optional, Dict, Any
from services.auth_service import verify_session


def get_current_user(
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    session_cookie: Optional[str] = Cookie(default=None, alias="session_id"),
) -> Dict[str, Any]:
    session_id = x_session_id or session_cookie
    if not session_id:
        raise HTTPException(status_code=401, detail="missing session id")
    user = verify_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


