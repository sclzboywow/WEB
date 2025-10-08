#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钱包服务层
包含卖家收益、提现申请、钱包管理等功能
"""

import sqlite3
import time
from typing import Dict, Any, Optional, List
from .db import init_sync_db

def check_pending_payout_requests(user_id: str) -> Dict[str, Any]:
    """
    检查用户是否有pending状态的提现申请
    """
    if not user_id:
        return {"has_pending": False}
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT COUNT(*) FROM payout_requests 
            WHERE user_id = ? AND status = 'pending'
        ''', (user_id,))
        
        pending_count = cursor.fetchone()[0]
        
        return {
            "has_pending": pending_count > 0,
            "pending_count": pending_count
        }
        
    except Exception as e:
        print(f"检查pending提现申请失败: {e}")
        return {"has_pending": False}
    finally:
        conn.close()

def award_seller(order_id: int, seller_id: str, seller_amount_cents: int) -> Dict[str, Any]:
    """
    支付成功后奖励卖家，增加待结算金额
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 检查用户钱包是否存在，不存在则创建
        cursor.execute('''
            INSERT OR IGNORE INTO user_wallets (user_id, balance_cents, pending_settlement_cents)
            VALUES (?, 0, 0)
        ''', (seller_id,))
        
        # 更新待结算金额
        cursor.execute('''
            UPDATE user_wallets 
            SET pending_settlement_cents = pending_settlement_cents + ?, updated_at = ?
            WHERE user_id = ?
        ''', (seller_amount_cents, time.time(), seller_id))
        
        # 获取更新后的余额
        cursor.execute('''
            SELECT balance_cents, pending_settlement_cents FROM user_wallets WHERE user_id = ?
        ''', (seller_id,))
        
        wallet_row = cursor.fetchone()
        if wallet_row:
            balance_cents, pending_settlement_cents = wallet_row
            
            # 记录钱包流水
            cursor.execute('''
                INSERT INTO wallet_logs (user_id, change_cents, balance_after, type, reference_id, remark)
                VALUES (?, ?, ?, 'sale', ?, ?)
            ''', (seller_id, seller_amount_cents, pending_settlement_cents, str(order_id), 
                  f"订单 {order_id} 支付成功，待结算金额 +{seller_amount_cents/100:.2f}元"))
        
        conn.commit()
        
        return {
            "status": "success",
            "message": f"卖家 {seller_id} 获得待结算金额 {seller_amount_cents/100:.2f}元"
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def settle_seller(order_id: int, seller_id: str) -> Dict[str, Any]:
    """
    交付完成时，按订单维度将该订单的收益从待结算转入余额。
    - 幂等：若 wallet_logs 已存在 (user_id, type='settlement', reference_id=order_id) 则直接返回成功。
    - 仅结算本订单金额：不会清空卖家全部待结算。
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 获取订单的卖家与应结算金额
        cursor.execute('''
            SELECT seller_id, seller_amount_cents FROM orders WHERE id = ?
        ''', (order_id,))
        ord_row = cursor.fetchone()
        if not ord_row:
            return {"status": "error", "message": "order not found"}
        order_seller_id, settle_amount = ord_row
        if not order_seller_id or settle_amount is None:
            return {"status": "error", "message": "order missing settlement fields"}
        if seller_id and seller_id != order_seller_id:
            return {"status": "error", "message": "seller mismatch for order"}
        seller_id = order_seller_id
        
        # 幂等：已结算则直接返回成功
        cursor.execute('''
            SELECT 1 FROM wallet_logs 
            WHERE user_id = ? AND type = 'settlement' AND reference_id = ?
            LIMIT 1
        ''', (seller_id, str(order_id)))
        if cursor.fetchone():
            return {"status": "success", "message": "already settled", "settled_amount": 0}
        
        # 确保钱包存在
        cursor.execute('''
            INSERT OR IGNORE INTO user_wallets (user_id, balance_cents, pending_settlement_cents)
            VALUES (?, 0, 0)
        ''', (seller_id,))
        
        # 查询当前钱包状态
        cursor.execute('''
            SELECT balance_cents, pending_settlement_cents FROM user_wallets WHERE user_id = ?
        ''', (seller_id,))
        wallet_row = cursor.fetchone()
        if not wallet_row:
            return {"status": "error", "message": "wallet not found"}
        balance_cents, pending_settlement_cents = wallet_row
        
        # 校验待结算是否足额
        if settle_amount <= 0:
            return {"status": "error", "message": "invalid settle amount"}
        if pending_settlement_cents < settle_amount:
            return {"status": "error", "message": "insufficient pending settlement"}
        
        # 进行结算：余额增加、待结算减少
        new_balance = balance_cents + settle_amount
        new_pending = pending_settlement_cents - settle_amount
        cursor.execute('''
            UPDATE user_wallets 
            SET balance_cents = ?, pending_settlement_cents = ?, updated_at = ?
            WHERE user_id = ?
        ''', (new_balance, new_pending, time.time(), seller_id))
        
        # 记录钱包流水（结算）
        cursor.execute('''
            INSERT INTO wallet_logs (user_id, change_cents, balance_after, type, reference_id, remark)
            VALUES (?, ?, ?, 'settlement', ?, ?)
        ''', (seller_id, settle_amount, new_balance, str(order_id),
              f"订单 {order_id} 结算 {settle_amount/100:.2f}元"))
        
        conn.commit()
        return {
            "status": "success",
            "message": f"卖家 {seller_id} 订单结算完成，余额增加 {settle_amount/100:.2f}元",
            "settled_amount": settle_amount,
            "new_balance": new_balance,
            "new_pending": new_pending
        }
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def create_payout_request(user_id: str, amount_cents: int, method: str, 
                         account_info: str, remark: str = "") -> Dict[str, Any]:
    """
    创建提现申请
    """
    if amount_cents <= 0:
        return {"status": "error", "message": "invalid amount"}
    
    # 导入风控服务
    from .risk_service import check_rate_limit, check_payout_limits
    
    # 检查频控
    rate_limit_result = check_rate_limit(user_id, 'create_payout')
    if not rate_limit_result.get('allowed', False):
        return {"status": "error", "message": rate_limit_result.get('message', '操作过于频繁')}
    
    # 检查额度限制
    limit_result = check_payout_limits(user_id, amount_cents)
    if limit_result.get('status') != 'success':
        return limit_result
    
    # 检查是否有pending状态的提现申请
    pending_check = check_pending_payout_requests(user_id)
    if pending_check.get('has_pending'):
        return {
            "status": "error", 
            "message": f"您还有{pending_check.get('pending_count', 0)}个待处理的提现申请，请等待处理完成后再申请"
        }
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')

        # 检查用户钱包余额
        cursor.execute('''
            SELECT balance_cents FROM user_wallets WHERE user_id = ?
        ''', (user_id,))

        wallet_row = cursor.fetchone()
        if not wallet_row:
            # 自动创建钱包，默认余额为 0，提升用户体验
            cursor.execute('''
                INSERT INTO user_wallets (user_id, balance_cents, pending_settlement_cents)
                VALUES (?, 0, 0)
            ''', (user_id,))
            conn.commit()
            balance_cents = 0
        else:
            balance_cents = wallet_row[0]

        # 校验余额是否足额
        if balance_cents < amount_cents:
            return {
                "status": "error",
                "message": f"余额不足，当前余额 {balance_cents/100:.2f}元，申请提现 {amount_cents/100:.2f}元"
            }

        # 创建提现申请
        cursor.execute('''
            INSERT INTO payout_requests (user_id, amount_cents, status, method, account_info, remark)
            VALUES (?, ?, 'pending', ?, ?, ?)
        ''', (user_id, amount_cents, method, account_info, remark))

        payout_id = cursor.lastrowid

        # 预扣余额（冻结资金）
        new_balance = balance_cents - amount_cents

        cursor.execute('''
            UPDATE user_wallets 
            SET balance_cents = ?, updated_at = ?
            WHERE user_id = ?
        ''', (new_balance, time.time(), user_id))

        # 记录钱包流水
        cursor.execute('''
            INSERT INTO wallet_logs (user_id, change_cents, balance_after, type, reference_id, remark)
            VALUES (?, ?, ?, 'payout_freeze', ?, ?)
        ''', (user_id, -amount_cents, new_balance, str(payout_id),
              f"提现申请 {payout_id}，冻结 {amount_cents/100:.2f}元"))

        conn.commit()

        return {
            "status": "success",
            "payout_id": payout_id,
            "message": f"提现申请已提交，冻结金额 {amount_cents/100:.2f}元"
        }

    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def review_payout_request(request_id: int, reviewer_id: str, status: str, 
                          remark: str = "") -> Dict[str, Any]:
    """
    审核提现申请
    """
    if status not in ["approved", "rejected", "paid"]:
        return {"status": "error", "message": "invalid status"}
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 获取提现申请信息
        cursor.execute('''
            SELECT user_id, amount_cents, status FROM payout_requests WHERE id = ?
        ''', (request_id,))
        
        payout_row = cursor.fetchone()
        if not payout_row:
            return {"status": "error", "message": "payout request not found"}
        
        user_id, amount_cents, current_status = payout_row
        
        if current_status != "pending":
            return {"status": "error", "message": "payout request already processed"}
        
        # 更新提现申请状态
        cursor.execute('''
            UPDATE payout_requests 
            SET status = ?, processed_at = ?
            WHERE id = ?
        ''', (status, time.time(), request_id))
        
        # 记录审核日志
        cursor.execute('''
            INSERT INTO payout_logs (payout_id, action, reviewer_id, remark)
            VALUES (?, ?, ?, ?)
        ''', (request_id, status, reviewer_id, remark))
        
        if status == "rejected":
            # 拒绝时，解冻资金
            cursor.execute('''
                SELECT balance_cents FROM user_wallets WHERE user_id = ?
            ''', (user_id,))
            
            wallet_row = cursor.fetchone()
            if wallet_row:
                balance_cents = wallet_row[0]
                new_balance = balance_cents + amount_cents
                
                cursor.execute('''
                    UPDATE user_wallets 
                    SET balance_cents = ?, updated_at = ?
                    WHERE user_id = ?
                ''', (new_balance, time.time(), user_id))
                
                # 记录解冻流水
                cursor.execute('''
                    INSERT INTO wallet_logs (user_id, change_cents, balance_after, type, reference_id, remark)
                    VALUES (?, ?, ?, 'payout_reject', ?, ?)
                ''', (user_id, amount_cents, new_balance, str(request_id),
                      f"提现申请 {request_id} 被拒绝，解冻 {amount_cents/100:.2f}元"))
        
        elif status == "paid":
            # 已支付时，记录最终扣款
            cursor.execute('''
                SELECT balance_cents FROM user_wallets WHERE user_id = ?
            ''', (user_id,))
            
            wallet_row = cursor.fetchone()
            if wallet_row:
                balance_cents = wallet_row[0]
                
                # 记录最终扣款流水
                cursor.execute('''
                    INSERT INTO wallet_logs (user_id, change_cents, balance_after, type, reference_id, remark)
                    VALUES (?, ?, ?, 'payout_paid', ?, ?)
                ''', (user_id, 0, balance_cents, str(request_id),
                      f"提现申请 {request_id} 已支付，最终扣款 {amount_cents/100:.2f}元"))
        
        conn.commit()
        
        # 发送通知
        from .notify_service import send_payout_approved_notification, send_payout_rejected_notification, send_payout_paid_notification
        
        if status == "approved":
            send_payout_approved_notification(user_id, request_id, amount_cents)
        elif status == "rejected":
            send_payout_rejected_notification(user_id, request_id, remark)
        elif status == "paid":
            send_payout_paid_notification(user_id, amount_cents, remark)
        
        return {
            "status": "success",
            "message": f"提现申请 {request_id} {status} 成功"
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def get_user_wallet(user_id: str) -> Dict[str, Any]:
    """
    获取用户钱包信息
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 获取钱包基本信息
        cursor.execute('''
            SELECT balance_cents, pending_settlement_cents, updated_at
            FROM user_wallets WHERE user_id = ?
        ''', (user_id,))
        
        wallet_row = cursor.fetchone()
        if not wallet_row:
            # 如果钱包不存在，创建默认钱包
            cursor.execute('''
                INSERT INTO user_wallets (user_id, balance_cents, pending_settlement_cents)
                VALUES (?, 0, 0)
            ''', (user_id,))
            conn.commit()
            
            balance_cents = 0
            pending_settlement_cents = 0
            updated_at = time.time()
        else:
            balance_cents, pending_settlement_cents, updated_at = wallet_row
        
        # 计算累计收入
        cursor.execute('''
            SELECT COALESCE(SUM(change_cents), 0) FROM wallet_logs 
            WHERE user_id = ? AND type = 'settlement'
        ''', (user_id,))
        
        total_income = cursor.fetchone()[0]
        
        # 获取提现记录
        cursor.execute('''
            SELECT id, amount_cents, status, method, account_info, remark, 
                   created_at, processed_at
            FROM payout_requests 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 10
        ''', (user_id,))
        
        payouts = []
        for row in cursor.fetchall():
            payouts.append({
                "id": row[0],
                "amount_cents": row[1],
                "amount_yuan": row[1] / 100,
                "status": row[2],
                "method": row[3],
                "account_info": row[4],
                "remark": row[5],
                "created_at": row[6],
                "processed_at": row[7]
            })
        
        # 获取最近的钱包流水
        cursor.execute('''
            SELECT change_cents, type, reference_id, remark, created_at
            FROM wallet_logs 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        ''', (user_id,))
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                "change_cents": row[0],
                "change_yuan": row[0] / 100,
                "type": row[1],
                "reference_id": row[2],
                "remark": row[3],
                "created_at": row[4]
            })
        
        return {
            "status": "success",
            "wallet": {
                "user_id": user_id,
                "balance_cents": balance_cents,
                "balance_yuan": balance_cents / 100,
                "pending_settlement_cents": pending_settlement_cents,
                "pending_settlement_yuan": pending_settlement_cents / 100,
                "total_income_cents": total_income,
                "total_income_yuan": total_income / 100,
                "updated_at": updated_at
            },
            "payouts": payouts,
            "logs": logs
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def refund_out(user_id: str, amount_cents: int, reference_id: str, remark: str = "") -> Dict[str, Any]:
    """从卖家余额或待结算中扣减退款（简单实现：优先扣余额，不足则扣待结算）。"""
    if amount_cents <= 0:
        return {"status": "error", "message": "invalid amount"}
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        conn.execute('BEGIN TRANSACTION')
        cursor.execute('SELECT balance_cents, pending_settlement_cents FROM user_wallets WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if not row:
            return {"status": "error", "message": "wallet not found"}
        balance, pending = row
        take_from_balance = min(balance, amount_cents)
        remaining = amount_cents - take_from_balance
        new_balance = balance - take_from_balance
        new_pending = pending
        if remaining > 0:
            if pending < remaining:
                return {"status": "error", "message": "insufficient funds"}
            new_pending = pending - remaining
        cursor.execute('UPDATE user_wallets SET balance_cents = ?, pending_settlement_cents = ?, updated_at = ? WHERE user_id = ?', (new_balance, new_pending, time.time(), user_id))
        cursor.execute('INSERT INTO wallet_logs (user_id, change_cents, balance_after, type, reference_id, remark) VALUES (?, ?, ?, "refund_out", ?, ?)', (user_id, -amount_cents, new_balance, str(reference_id), remark or f"退款扣减 {amount_cents/100:.2f}元"))
        conn.commit()
        return {"status": "success", "new_balance": new_balance, "new_pending": new_pending}
    except Exception as e:
        conn.rollback(); return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def refund_in(user_id: str, amount_cents: int, reference_id: str, remark: str = "") -> Dict[str, Any]:
    """向买家余额入账退款（简单实现：直接加余额并记录流水）。"""
    if amount_cents <= 0:
        return {"status": "error", "message": "invalid amount"}
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        conn.execute('BEGIN TRANSACTION')
        cursor.execute('INSERT OR IGNORE INTO user_wallets (user_id, balance_cents, pending_settlement_cents) VALUES (?, 0, 0)', (user_id,))
        cursor.execute('SELECT balance_cents FROM user_wallets WHERE user_id = ?', (user_id,))
        row = cursor.fetchone(); balance = row[0] if row else 0
        new_balance = balance + amount_cents
        cursor.execute('UPDATE user_wallets SET balance_cents = ?, updated_at = ? WHERE user_id = ?', (new_balance, time.time(), user_id))
        cursor.execute('INSERT INTO wallet_logs (user_id, change_cents, balance_after, type, reference_id, remark) VALUES (?, ?, ?, "refund_in", ?, ?)', (user_id, amount_cents, new_balance, str(reference_id), remark or f"退款入账 {amount_cents/100:.2f}元"))
        conn.commit(); return {"status": "success", "new_balance": new_balance}
    except Exception as e:
        conn.rollback(); return {"status": "error", "message": str(e)}
    finally:
        conn.close()
