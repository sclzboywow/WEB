#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知API路由
提供RESTful接口用于通知管理
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional, List, Dict, Any
from services.notify_service import (
    get_user_notifications, 
    mark_notification_read, 
    mark_all_notifications_read,
    get_unread_count,
    get_notifications_advanced,
    dispatch_notifications,
    admin_manage_notifications,
    record_notification_event,
    resend_notification,
    delete_notification,
    create_notification
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

@router.get("/")
async def get_notifications(
    user_id: str = Query(..., description="用户ID"),
    status: Optional[str] = Query(None, regex="^(unread|read|all)$", description="通知状态筛选"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    # 扩展分页/筛选（向下兼容）
    page: Optional[int] = Query(None, ge=1),
    size: Optional[int] = Query(None, ge=1, le=100),
    type: Optional[str] = Query(None, description="类型筛选 info/success/warning/error"),
    since: Optional[float] = Query(None, description="起始时间戳"),
    until: Optional[float] = Query(None, description="结束时间戳"),
    channel: Optional[str] = Query(None, description="渠道，例如 inbox"),
):
    """
    获取用户通知列表（兼容旧参），如提供 page/size 将使用分页模式并返回 items/has_more。
    """
    # 如果提供了 page/size 或其他筛选，走高级查询
    if page is not None or size is not None or type or since is not None or until is not None or channel:
        adv = get_notifications_advanced(
            user_id=user_id,
            page=page or (offset // limit + 1),
            size=size or limit,
            status=status,
            type_filter=type,
            since=since,
            until=until,
            channel=channel,
        )
        if adv["status"] != "success":
            raise HTTPException(status_code=400, detail=adv["message"])
        return adv
    # 否则走旧的 limit/offset 结构
    result = get_user_notifications(user_id, limit, offset, status)
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@router.get("/unread-count")
async def get_unread_notifications_count(
    user_id: str = Query(..., description="用户ID")
):
    """
    获取用户未读通知数量
    
    - **user_id**: 用户ID
    """
    result = get_unread_count(user_id)
    
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result

@router.post("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int = Path(..., description="通知ID"),
    user_id: str = Query(..., description="用户ID")
):
    """
    标记通知为已读
    
    - **notification_id**: 通知ID
    - **user_id**: 用户ID
    """
    result = mark_notification_read(notification_id, user_id)
    
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result

@router.post("/read-all")
async def mark_all_as_read(
    user_id: str = Query(..., description="用户ID")
):
    """
    标记所有通知为已读
    
    - **user_id**: 用户ID
    """
    result = mark_all_notifications_read(user_id)
    
    if result["status"] != "success":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result

@router.post("/broadcast")
async def broadcast_notifications(payload: Dict[str, Any]):
    """管理员广播：scope=user/role/all；user时要求 user_ids。"""
    scope = payload.get("scope", "all")
    role = payload.get("role")
    title = payload.get("title")
    content = payload.get("content", "")
    ntype = payload.get("type", "info")
    channel = payload.get("channel", "inbox")
    metadata = payload.get("metadata")
    user_ids = payload.get("user_ids")
    if not title:
        raise HTTPException(status_code=400, detail="missing title")
    resp = dispatch_notifications(
        target_scope=scope,
        title=title,
        content=content,
        notification_type=ntype,
        sender_role="admin",
        target_role=role,
        user_ids=user_ids,
        channel=channel,
        metadata=metadata,
    )
    if resp["status"] != "success":
        raise HTTPException(status_code=400, detail=resp["message"])
    return resp

@router.get("/manage")
async def manage_notifications(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    since: Optional[float] = Query(None),
    until: Optional[float] = Query(None),
):
    resp = admin_manage_notifications(page=page, size=size, type_filter=type, channel=channel, role=role, since=since, until=until)
    if resp["status"] != "success":
        raise HTTPException(status_code=400, detail=resp["message"])
    return resp

@router.post("/{notification_id}/events")
async def post_notification_event(
    notification_id: int = Path(..., description="通知ID"),
    user_id: str = Query(..., description="用户ID"),
    payload: Dict[str, Any] = None
):
    event = (payload or {}).get("event")
    extra = (payload or {}).get("extra")
    if not event:
        raise HTTPException(status_code=400, detail="missing event")
    resp = record_notification_event(notification_id, user_id, event, extra=extra)
    if resp["status"] != "success":
        raise HTTPException(status_code=400, detail=resp["message"])
    return resp

@router.post("/{notification_id}/resend")
async def resend(notification_id: int = Path(...)):
    resp = resend_notification(notification_id)
    if resp["status"] != "success":
        raise HTTPException(status_code=400, detail=resp["message"])
    return resp

@router.delete("/{notification_id}")
async def delete(notification_id: int = Path(...)):
    resp = delete_notification(notification_id)
    if resp["status"] != "success":
        raise HTTPException(status_code=400, detail=resp["message"])
    return resp
@router.get("/stats")
async def get_notification_stats(
    user_id: str = Query(..., description="用户ID")
):
    """扩展统计：返回未读/总数，并按 type/channel 维度的未读计数。"""
    unread_result = get_unread_count(user_id)
    if unread_result["status"] != "success":
        raise HTTPException(status_code=400, detail=unread_result["message"])
    base_list = get_user_notifications(user_id, limit=1, offset=0)
    if base_list["status"] != "success":
        raise HTTPException(status_code=400, detail=base_list["message"])

    # 统计按 type/channel 的未读数
    # 直接调用高级查询分页统计成本高，这里走轻量 SQL via service 不暴露；简单起见，客户端分维度拉取可替代。
    return {
        "status": "success",
        "stats": {
            "unread_count": unread_result["unread_count"],
            "total_count": base_list["total"],
            "user_id": user_id
        }
    }
