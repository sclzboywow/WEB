#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品上架服务层
包含商品创建、审核、交付等功能
"""

import sqlite3
import secrets
import time
from typing import Dict, Any, List, Optional
from .db import init_sync_db

def create_listing(seller_id: str, title: str, price_cents: int,
                   listing_type: str = "single", description: str = "", 
                   files: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    创建商品上架记录
    """
    if not seller_id or not title or price_cents <= 0:
        return {"status": "error", "message": "missing required parameters"}
    
    if listing_type not in ["single", "bundle", "subscription", "limited"]:
        return {"status": "error", "message": "invalid listing_type"}
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 插入商品记录
        cursor.execute('''
            INSERT INTO listings (seller_id, title, description, listing_type, 
                                price_cents, status, review_status)
            VALUES (?, ?, ?, ?, ?, 'draft', 'pending')
        ''', (seller_id, title, description, listing_type, price_cents))
        
        listing_id = cursor.lastrowid
        
        # 插入文件记录
        if files:
            for file_info in files:
                cursor.execute('''
                    INSERT INTO listing_files (listing_id, file_path, file_name, 
                                             file_size, file_md5)
                    VALUES (?, ?, ?, ?, ?)
                ''', (listing_id, 
                      file_info.get('file_path', ''),
                      file_info.get('file_name', ''),
                      file_info.get('file_size'),
                      file_info.get('file_md5')))
        
        conn.commit()
        
        return {
            "status": "success",
            "listing_id": listing_id,
            "message": "listing created successfully"
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def submit_listing_for_review(listing_id: int) -> Dict[str, Any]:
    """
    提交商品审核
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        query = cursor.execute('SELECT id FROM listings WHERE id = ?', (listing_id,))
        if not query.fetchone():
            return {"status": "error", "message": "listing not found"}
        
        # 更新商品状态为待审核
        cursor.execute('''
            UPDATE listings 
            SET status = 'pending', updated_at = ?
            WHERE id = ?
        ''', (time.time(), listing_id))
        
        # 创建审核记录
        cursor.execute('''
            INSERT INTO listing_reviews (listing_id, status)
            VALUES (?, 'pending')
        ''', (listing_id,))
        
        conn.commit()
        
        return {
            "status": "success",
            "message": "listing submitted for review"
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def approve_listing(listing_id: int, reviewer_id: str, remark: str = "") -> Dict[str, Any]:
    """
    审核通过商品
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 获取商品信息
        cursor.execute('''
            SELECT seller_id, title FROM listings WHERE id = ?
        ''', (listing_id,))
        
        listing_row = cursor.fetchone()
        if not listing_row:
            return {"status": "error", "message": "listing not found"}
        
        seller_id, title = listing_row
        
        # 更新商品状态
        cursor.execute('''
            UPDATE listings 
            SET status = 'live', review_status = 'approved', updated_at = ?, published_at = ?
            WHERE id = ?
        ''', (time.time(), time.time(), listing_id))
        
        # 创建审核记录
        cursor.execute('''
            INSERT INTO listing_reviews (listing_id, reviewer_id, status, remark, reviewed_at)
            VALUES (?, ?, 'approved', ?, ?)
        ''', (listing_id, reviewer_id, remark, time.time()))
        
        conn.commit()
        
        # 发送审核通过通知
        from .notify_service import send_listing_approved_notification
        send_listing_approved_notification(seller_id, listing_id, title)
        
        return {
            "status": "success",
            "message": f"商品「{title}」审核通过"
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def reject_listing(listing_id: int, reviewer_id: str, reason: str) -> Dict[str, Any]:
    """
    审核拒绝商品
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 获取商品信息
        cursor.execute('''
            SELECT seller_id, title FROM listings WHERE id = ?
        ''', (listing_id,))
        
        listing_row = cursor.fetchone()
        if not listing_row:
            return {"status": "error", "message": "listing not found"}
        
        seller_id, title = listing_row
        
        # 更新商品状态
        cursor.execute('''
            UPDATE listings 
            SET status = 'rejected', review_status = 'rejected', updated_at = ?
            WHERE id = ?
        ''', (time.time(), listing_id))
        
        # 创建审核记录
        cursor.execute('''
            INSERT INTO listing_reviews (listing_id, reviewer_id, status, remark, reviewed_at)
            VALUES (?, ?, 'rejected', ?, ?)
        ''', (listing_id, reviewer_id, reason, time.time()))
        
        conn.commit()
        
        # 发送审核拒绝通知
        from .notify_service import send_listing_rejected_notification
        send_listing_rejected_notification(seller_id, listing_id, title, reason)
        
        return {
            "status": "success",
            "message": f"商品「{title}」审核拒绝"
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def deliver_order(order_id: int) -> Dict[str, Any]:
    """
    交付订单：为每个 order_item 在 user_purchases 中创建记录
    """
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 获取订单信息
        cursor.execute('''
            SELECT buyer_id FROM orders WHERE id = ?
        ''', (order_id,))
        
        buyer_row = cursor.fetchone()
        if not buyer_row:
            return {"status": "error", "message": "order not found"}
        
        buyer_id = buyer_row[0]
        
        # 获取订单项
        cursor.execute('''
            SELECT listing_id FROM order_items WHERE order_id = ?
        ''', (order_id,))
        
        order_items = cursor.fetchall()
        
        # 为每个商品创建购买记录
        delivered_count = 0
        for item_row in order_items:
            listing_id = item_row[0]
            
            # 获取商品文件列表
            cursor.execute('''
                SELECT file_path FROM listing_files WHERE listing_id = ?
            ''', (listing_id,))
            
            files = cursor.fetchall()
            
            # 为每个文件创建购买记录
            for file_row in files:
                file_path = file_row[0]
                
                cursor.execute('''
                    INSERT OR IGNORE INTO user_purchases 
                    (order_id, listing_id, buyer_id, file_path)
                    VALUES (?, ?, ?, ?)
                ''', (order_id, listing_id, buyer_id, file_path))
                
                delivered_count += 1
        
        # 更新订单项的交付时间
        cursor.execute('''
            UPDATE order_items SET delivered_at = ? WHERE order_id = ?
        ''', (time.time(), order_id))
        
        conn.commit()
        
        return {
            "status": "success",
            "message": f"delivered {delivered_count} files",
            "delivered_count": delivered_count
        }
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()
