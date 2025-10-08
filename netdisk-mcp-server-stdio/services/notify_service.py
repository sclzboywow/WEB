#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知服务层
包含消息推送、通知管理等功能
"""

import sqlite3
import time
from typing import Dict, Any, List, Optional, Iterable
from .db import init_sync_db

def create_notification(
    user_id: Optional[str],
    title: str,
    content: str = "",
    notification_type: str = "info",
    sender_role: Optional[str] = None,
    *,
    target_scope: str = "user",  # user/role/all
    target_role: Optional[str] = None,
    channel: str = "inbox",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    创建通知
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 如果sender_role为None，使用默认值
        if sender_role is None:
            sender_role = "system"
        # 校验类型与范围
        if notification_type not in {"info", "success", "warning", "error"}:
            return {"status": "error", "message": "invalid notification_type"}
        if target_scope not in {"user", "role", "all"}:
            return {"status": "error", "message": "invalid target_scope"}
        if target_scope == "user" and not user_id:
            return {"status": "error", "message": "user_id required for user scope"}
        if target_scope in {"role", "all"}:
            # 兼容：允许 user_id 为空
            user_id = user_id or "__broadcast__"
            
        cursor.execute('''
            INSERT INTO notifications (
                user_id, title, content, type, status, sender_role, created_at,
                target_scope, target_role, channel, metadata
            )
            VALUES (?, ?, ?, ?, 'unread', ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, title, content, notification_type, sender_role, time.time(),
            target_scope, target_role, channel, (None if metadata is None else str(metadata))
        ))
        
        notification_id = cursor.lastrowid
        conn.commit()
        
        return {
            "status": "success",
            "notification_id": notification_id,
            "message": "通知创建成功"
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def dispatch_notifications(
    *,
    target_scope: str,
    title: str,
    content: str,
    notification_type: str = "info",
    sender_role: Optional[str] = None,
    target_role: Optional[str] = None,
    user_ids: Optional[Iterable[str]] = None,
    channel: str = "inbox",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """将按角色/全员广播拆分为具体用户记录，或按用户集合批量插入。
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        if sender_role is None:
            sender_role = "system"
        if notification_type not in {"info", "success", "warning", "error"}:
            return {"status": "error", "message": "invalid notification_type"}
        if target_scope not in {"user", "role", "all"}:
            return {"status": "error", "message": "invalid target_scope"}

        # 解析目标用户
        targets: List[str] = []
        if target_scope == "user":
            if not user_ids:
                return {"status": "error", "message": "user_ids required for user scope"}
            targets = list(user_ids)
        elif target_scope == "role":
            if not target_role:
                return {"status": "error", "message": "target_role required for role scope"}
            cursor.execute("SELECT user_id FROM users WHERE role = ?", (target_role,))
            targets = [row[0] for row in cursor.fetchall()]
        else:  # all
            cursor.execute("SELECT user_id FROM users")
            targets = [row[0] for row in cursor.fetchall()]

        now_ts = time.time()
        rows = [
            (
                uid,
                title,
                content,
                notification_type,
                'unread',
                sender_role,
                now_ts,
                target_scope,
                target_role,
                channel,
                (None if metadata is None else str(metadata))
            )
            for uid in targets
        ]
        if not rows:
            return {"status": "success", "inserted": 0}
        cursor.executemany('''
            INSERT INTO notifications (
                user_id, title, content, type, status, sender_role, created_at,
                target_scope, target_role, channel, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', rows)
        conn.commit()
        return {"status": "success", "inserted": len(rows)}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def get_user_notifications(user_id: str, limit: int = 20, offset: int = 0, 
                          status: Optional[str] = None) -> Dict[str, Any]:
    """
    获取用户通知列表
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 构建查询条件
        where_conditions = ["user_id = ?"]
        params = [user_id]
        
        if status and status != "all":
            where_conditions.append("status = ?")
            params.append(status)
        
        where_clause = " AND ".join(where_conditions)
        
        # 获取通知列表
        cursor.execute(f'''
            SELECT id, title, content, type, status, sender_role, created_at, read_at
            FROM notifications 
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', params + [limit, offset])
        
        notifications = []
        for row in cursor.fetchall():
            notifications.append({
                "id": row[0],
                "title": row[1],
                "content": row[2],
                "type": row[3],
                "status": row[4],
                "sender_role": row[5],
                "created_at": row[6],
                "read_at": row[7]
            })
        
        # 获取总数
        cursor.execute(f'''
            SELECT COUNT(*) FROM notifications WHERE {where_clause}
        ''', params)
        
        total = cursor.fetchone()[0]
        
        return {
            "status": "success",
            "notifications": notifications,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def get_notifications_advanced(
    *,
    user_id: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    status: Optional[str] = None,
    type_filter: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    channel: Optional[str] = None,
    target_scope: Optional[str] = None,
    target_role: Optional[str] = None,
) -> Dict[str, Any]:
    """通用查询（支持分页与筛选），向下兼容现有结构。"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        where = []
        params: List[Any] = []
        if user_id:
            where.append("user_id = ?"); params.append(user_id)
        if status and status != "all":
            where.append("status = ?"); params.append(status)
        if type_filter:
            where.append("type = ?"); params.append(type_filter)
        if since is not None:
            where.append("created_at >= ?"); params.append(since)
        if until is not None:
            where.append("created_at <= ?"); params.append(until)
        if channel:
            where.append("channel = ?"); params.append(channel)
        if target_scope:
            where.append("target_scope = ?"); params.append(target_scope)
        if target_role:
            where.append("target_role = ?"); params.append(target_role)
        where_clause = (" WHERE " + " AND ".join(where)) if where else ""

        size = max(1, min(int(size), 100))
        page = max(1, int(page))
        offset = (page - 1) * size

        cursor.execute(f'''
            SELECT id, user_id, title, content, type, status, sender_role, created_at, read_at,
                   target_scope, target_role, channel, metadata
            FROM notifications
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', params + [size + 1, offset])
        rows = cursor.fetchall()
        has_more = len(rows) > size
        rows = rows[:size]

        items = []
        for r in rows:
            items.append({
                "id": r[0],
                "user_id": r[1],
                "title": r[2],
                "content": r[3],
                "type": r[4],
                "status": r[5],
                "sender_role": r[6],
                "created_at": r[7],
                "read_at": r[8],
                "target_scope": r[9],
                "target_role": r[10],
                "channel": r[11],
                "metadata": r[12],
            })

        return {
            "status": "success",
            "items": items,
            "page": page,
            "size": size,
            "has_more": has_more,
            "next_page": (page + 1) if has_more else None,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def record_notification_event(
    notification_id: int,
    user_id: str,
    event: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """写入通知事件，支持 read/view/click。"""
    if event not in {"read", "view", "click"}:
        return {"status": "error", "message": "invalid event"}
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        now_ts = time.time()
        read_at = now_ts if event == "read" else None
        viewed_at = now_ts if event == "view" else None
        cursor.execute('''
            INSERT INTO notification_events (notification_id, user_id, event, read_at, viewed_at, extra, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (notification_id, user_id, event, read_at, viewed_at, (None if extra is None else str(extra)), now_ts))
        conn.commit()
        return {"status": "success", "event_id": cursor.lastrowid}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def admin_manage_notifications(
    *, page: int = 1, size: int = 20, type_filter: Optional[str] = None, channel: Optional[str] = None,
    role: Optional[str] = None, since: Optional[float] = None, until: Optional[float] = None
) -> Dict[str, Any]:
    return get_notifications_advanced(
        user_id=None, page=page, size=size, status=None, type_filter=type_filter,
        since=since, until=until, channel=channel, target_scope=None,
        target_role=role,
    )


def resend_notification(notification_id: int) -> Dict[str, Any]:
    """简单重发：读取原通知并为同一用户再插入一条相同内容。"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT user_id, title, content, type, sender_role, target_scope, target_role, channel, metadata
            FROM notifications WHERE id = ?
        ''', (notification_id,))
        row = cursor.fetchone()
        if not row:
            return {"status": "error", "message": "notification not found"}
        return create_notification(
            user_id=row[0], title=row[1], content=row[2], notification_type=row[3], sender_role=row[4],
            target_scope=row[5] or 'user', target_role=row[6], channel=row[7] or 'inbox', metadata=None
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def delete_notification(notification_id: int) -> Dict[str, Any]:
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM notifications WHERE id = ?', (notification_id,))
        if cursor.rowcount == 0:
            return {"status": "error", "message": "notification not found"}
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def mark_notification_read(notification_id: int, user_id: str) -> Dict[str, Any]:
    """
    标记通知为已读
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE notifications 
            SET status = 'read', read_at = ?
            WHERE id = ? AND user_id = ?
        ''', (time.time(), notification_id, user_id))
        
        if cursor.rowcount == 0:
            return {"status": "error", "message": "通知不存在或无权限"}
        
        conn.commit()
        
        return {
            "status": "success",
            "message": "通知已标记为已读"
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def mark_all_notifications_read(user_id: str) -> Dict[str, Any]:
    """
    标记用户所有通知为已读
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE notifications 
            SET status = 'read', read_at = ?
            WHERE user_id = ? AND status = 'unread'
        ''', (time.time(), user_id))
        
        affected_count = cursor.rowcount
        conn.commit()
        
        return {
            "status": "success",
            "message": f"已标记 {affected_count} 条通知为已读"
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def get_unread_count(user_id: str) -> Dict[str, Any]:
    """
    获取用户未读通知数量
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT COUNT(*) FROM notifications 
            WHERE user_id = ? AND status = 'unread'
        ''', (user_id,))
        
        count = cursor.fetchone()[0]
        
        return {
            "status": "success",
            "unread_count": count
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def send_payment_success_notification(buyer_id: str, order_id: int, amount_cents: int) -> Dict[str, Any]:
    """
    发送支付成功通知
    """
    title = "支付成功"
    content = f"您的订单 {order_id} 支付成功，金额 ¥{amount_cents/100:.2f}，商品已交付到您的账户。"
    
    return create_notification(
        user_id=buyer_id,
        title=title,
        content=content,
        notification_type="success",
        sender_role="system"
    )

def send_payout_approved_notification(seller_id: str, payout_id: int, amount_cents: int) -> Dict[str, Any]:
    """
    发送提现审核通过通知
    """
    title = "提现审核通过"
    content = f"您的提现申请 {payout_id} 已审核通过，金额 ¥{amount_cents/100:.2f}，请查收。"
    
    return create_notification(
        user_id=seller_id,
        title=title,
        content=content,
        notification_type="success",
        sender_role="admin"
    )

def send_payout_rejected_notification(seller_id: str, payout_id: int, reason: str) -> Dict[str, Any]:
    """
    发送提现审核拒绝通知
    """
    title = "提现审核未通过"
    content = f"您的提现申请 {payout_id} 未通过审核，原因：{reason}。资金已解冻。"
    
    return create_notification(
        user_id=seller_id,
        title=title,
        content=content,
        notification_type="warning",
        sender_role="admin"
    )

def send_order_created_notification(seller_id: str, order_id: int, buyer_id: str, amount_cents: int) -> Dict[str, Any]:
    """
    发送新订单通知给卖家
    """
    title = "新订单"
    content = f"您有新的订单 {order_id}，买家：{buyer_id}，金额：¥{amount_cents/100:.2f}，请及时处理。"
    
    return create_notification(
        user_id=seller_id,
        title=title,
        content=content,
        notification_type="info",
        sender_role="system"
    )

def send_listing_approved_notification(seller_id: str, listing_id: int, title: str) -> Dict[str, Any]:
    """
    发送商品审核通过通知
    """
    title_text = "商品审核通过"
    content = f"您的商品「{title}」已通过审核，现在可以正常销售了。"
    
    return create_notification(
        user_id=seller_id,
        title=title_text,
        content=content,
        notification_type="success",
        sender_role="admin"
    )

def send_listing_rejected_notification(seller_id: str, listing_id: int, title: str, reason: str) -> Dict[str, Any]:
    """
    发送商品审核拒绝通知
    """
    title_text = "商品审核未通过"
    content = f"您的商品「{title}」未通过审核，原因：{reason}。请修改后重新提交。"
    
    return create_notification(
        user_id=seller_id,
        title=title_text,
        content=content,
        notification_type="warning",
        sender_role="admin"
    )

def send_order_delivered_notification(buyer_id: str, order_id: int, seller_id: str) -> Dict[str, Any]:
    """
    发送订单交付通知给买家
    """
    title = "订单已交付"
    content = f"您的订单 {order_id} 已交付完成，商品已添加到您的已购清单中。"
    
    return create_notification(
        user_id=buyer_id,
        title=title,
        content=content,
        notification_type="success",
        sender_role="system"
    )

def send_system_maintenance_notification(user_id: str, message: str) -> Dict[str, Any]:
    """
    发送系统维护通知
    """
    title = "系统维护通知"
    content = message
    
    return create_notification(
        user_id=user_id,
        title=title,
        content=content,
        notification_type="info",
        sender_role="system"
    )

def send_payout_paid_notification(user_id: str, amount_cents: int, remark: str = "") -> Dict[str, Any]:
    """
    发送提现到账通知
    """
    amount_yuan = amount_cents / 100
    title = "提现已到账"
    content = f"您的提现申请已处理完成，金额：¥{amount_yuan:.2f}"
    if remark:
        content += f"，备注：{remark}"
    
    return create_notification(
        user_id=user_id,
        title=title,
        content=content,
        notification_type="success",
        sender_role="admin"
    )
