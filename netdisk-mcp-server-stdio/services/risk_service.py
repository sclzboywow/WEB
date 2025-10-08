#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风控服务层
包含频控、额度限制、审计日志等功能
"""

import time
import sqlite3
from typing import Dict, Any, Optional
from .db import init_sync_db

# 频控配置
RATE_LIMITS = {
    'create_order': {'max_requests': 10, 'window_seconds': 60},  # 1分钟内最多10次下单
    'create_payout': {'max_requests': 3, 'window_seconds': 60},  # 1分钟内最多3次提现申请
    'payment_config': {'max_requests': 5, 'window_seconds': 300},  # 5分钟内最多5次配置修改
}

# 额度限制配置
LIMITS = {
    'min_payout_amount': 100,  # 最小提现金额（分）
    'max_payout_amount': 1000000,  # 最大提现金额（分）
    'daily_payout_limit': 5000000,  # 每日提现限额（分）
}

def check_rate_limit(user_id: str, action: str) -> Dict[str, Any]:
    """
    检查用户操作频控
    """
    if action not in RATE_LIMITS:
        return {"status": "success", "allowed": True}
    
    limit_config = RATE_LIMITS[action]
    max_requests = limit_config['max_requests']
    window_seconds = limit_config['window_seconds']
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 获取时间窗口内的请求次数
        window_start = time.time() - window_seconds
        cursor.execute('''
            SELECT COUNT(*) FROM rate_limit_logs 
            WHERE user_id = ? AND action = ? AND created_at > ?
        ''', (user_id, action, window_start))
        
        request_count = cursor.fetchone()[0]
        
        if request_count >= max_requests:
            return {
                "status": "error",
                "message": f"操作过于频繁，{window_seconds}秒内最多允许{max_requests}次{action}操作",
                "allowed": False,
                "retry_after": window_seconds
            }
        
        # 记录本次请求
        cursor.execute('''
            INSERT INTO rate_limit_logs (user_id, action, created_at)
            VALUES (?, ?, ?)
        ''', (user_id, action, time.time()))
        
        conn.commit()
        
        return {
            "status": "success",
            "allowed": True,
            "remaining": max_requests - request_count - 1
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e), "allowed": False}
    finally:
        conn.close()

def check_payout_limits(user_id: str, amount_cents: int) -> Dict[str, Any]:
    """
    检查提现额度限制
    """
    if amount_cents < LIMITS['min_payout_amount']:
        return {
            "status": "error",
            "message": f"提现金额不能少于{LIMITS['min_payout_amount']/100:.2f}元"
        }
    
    if amount_cents > LIMITS['max_payout_amount']:
        return {
            "status": "error",
            "message": f"单次提现金额不能超过{LIMITS['max_payout_amount']/100:.2f}元"
        }
    
    # 检查每日提现限额
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 获取今日已提现金额
        today_start = time.time() - (time.time() % 86400)  # 今日0点
        cursor.execute('''
            SELECT COALESCE(SUM(amount_cents), 0) FROM payout_requests 
            WHERE user_id = ? AND created_at > ? AND status IN ('pending', 'approved', 'paid')
        ''', (user_id, today_start))
        
        today_payouts = cursor.fetchone()[0]
        
        if today_payouts + amount_cents > LIMITS['daily_payout_limit']:
            remaining = LIMITS['daily_payout_limit'] - today_payouts
            return {
                "status": "error",
                "message": f"今日提现额度不足，剩余额度: {remaining/100:.2f}元"
            }
        
        return {"status": "success", "message": "额度检查通过"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def log_order_operation(order_id: int, action: str, details: Dict[str, Any], user_id: Optional[str] = None) -> None:
    """
    记录订单操作日志
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO order_logs (order_id, action, details, user_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, action, str(details), user_id, time.time()))
        
        conn.commit()
    except Exception as e:
        print(f"记录订单日志失败: {e}")
    finally:
        conn.close()

def log_payment_callback(order_id: int, provider: str, transaction_id: str, status: str, payload: Dict[str, Any]) -> None:
    """
    记录支付回调日志
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO payment_callback_logs (order_id, provider, transaction_id, status, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (order_id, provider, transaction_id, status, str(payload), time.time()))
        
        conn.commit()
    except Exception as e:
        print(f"记录支付回调日志失败: {e}")
    finally:
        conn.close()

def get_user_operation_stats(user_id: str, action: str, hours: int = 24) -> Dict[str, Any]:
    """
    获取用户操作统计
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        since_time = time.time() - (hours * 3600)
        
        cursor.execute('''
            SELECT COUNT(*) FROM rate_limit_logs 
            WHERE user_id = ? AND action = ? AND created_at > ?
        ''', (user_id, action, since_time))
        
        count = cursor.fetchone()[0]
        
        return {
            "user_id": user_id,
            "action": action,
            "count": count,
            "hours": hours
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def record_risk_event(user_id: str, event_type: str, reference_id: str = None, details: Dict[str, Any] = None, score: int = 0) -> Dict[str, Any]:
    """写入风控事件。"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO risk_events (user_id, event_type, reference_id, details, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, event_type, reference_id or '', str(details or {}), int(score), time.time()))
        conn.commit()
        return {"status": "success", "id": cursor.lastrowid}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def check_refund_frequency(user_id: str, window_seconds: int = 3600, max_requests: int = 3) -> Dict[str, Any]:
    """示例规则：最近 window 内退款申请次数上限校验。"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        since = time.time() - window_seconds
        cursor.execute('''
            SELECT COUNT(*) FROM refund_requests WHERE buyer_id = ? AND created_at > ?
        ''', (user_id, since))
        cnt = cursor.fetchone()[0]
        if cnt >= max_requests:
            # 记录风控事件
            record_risk_event(user_id, 'refund_freq_exceed', None, {"count": cnt, "window": window_seconds}, score=50)
            # 管理员预警广播（不影响主流程）
            try:
                from .notify_service import dispatch_notifications
                dispatch_notifications(
                    target_scope='role', target_role='admin', title='高频退款预警',
                    content=f'用户 {user_id} 在 {window_seconds}s 内退款申请 {cnt} 次',
                    notification_type='warning', sender_role='system', channel='risk'
                )
            except Exception:
                pass
            return {"status": "error", "message": "退款过于频繁，请稍后再试", "allowed": False}
        return {"status": "success", "allowed": True, "count": cnt}
    except Exception as e:
        return {"status": "error", "message": str(e), "allowed": False}
    finally:
        conn.close()
