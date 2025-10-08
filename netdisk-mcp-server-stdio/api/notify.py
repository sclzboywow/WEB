#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知API路由
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from services.notify_service import (
    get_user_notifications, 
    mark_notification_read, 
    mark_all_notifications_read,
    get_unread_count
)

router = APIRouter(prefix="/api/notify", tags=["notifications"])

# 兼容旧前端轮询接口：/api/notify?since=0&limit=50
# 无 user_id 的情况下返回空列表以避免前端报错
@router.get("")
async def notify_poll_compat(since: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    return {
        "status": "success",
        "notifications": [],
        "total": 0,
        "limit": limit,
        "offset": 0
    }

@router.get("/{user_id}")
async def get_notifications(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None)
):
    """获取用户通知列表"""
    result = get_user_notifications(user_id, limit, offset, status)
    
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result

@router.get("/{user_id}/unread-count")
async def get_unread_notifications_count(user_id: str):
    """获取用户未读通知数量"""
    result = get_unread_count(user_id)
    
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result

@router.post("/{notification_id}/read")
async def mark_notification_as_read(notification_id: int, user_id: str):
    """标记通知为已读"""
    result = mark_notification_read(notification_id, user_id)
    
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result

@router.post("/{user_id}/read-all")
async def mark_all_as_read(user_id: str):
    """标记所有通知为已读"""
    result = mark_all_notifications_read(user_id)
    
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result
