#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品管理API路由
包含商品上架、审核、查询等功能
"""

import sqlite3
import os
import time
from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional

from services.db import init_sync_db
from services.notify_service import send_listing_approved_notification, send_listing_rejected_notification
from api.netdisk import move_files as _netdisk_move_files  # async
from api.netdisk import ensure_directory as _netdisk_ensure_directory  # async
from services.listing_service import create_listing, submit_listing_for_review
from api.deps import get_current_user

router = APIRouter(prefix="/api/listings", tags=["Listings"])

@router.post("")
async def api_listings_create(payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """创建商品上架"""
    seller_id = user.get("user_id")
    title = payload.get("title")
    price_cents = payload.get("price_cents")
    listing_type = payload.get("listing_type", "single")
    description = payload.get("description", "")
    files = payload.get("files", [])
    
    resp = create_listing(seller_id, title, price_cents, listing_type, description, files)
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

@router.post("/{listing_id}/submit")
async def api_listings_submit(listing_id: int):
    """提交商品审核"""
    resp = submit_listing_for_review(listing_id)
    status_code = 200 if resp.get("status") == "success" else 400
    return JSONResponse(resp, status_code=status_code)

@router.get("/mine")
async def api_listings_mine(status: Optional[str] = Query(None), user: Dict[str, Any] = Depends(get_current_user)):
    """查看卖家的商品列表"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        where_clause = "WHERE seller_id = ?"
        params = [user.get("user_id")]
        
        if status:
            where_clause += " AND status = ?"
            params.append(status)
        
        cursor.execute(f'''
            SELECT id, title, description, listing_type, price_cents, status, 
                   review_status, created_at, updated_at, published_at
            FROM listings
            {where_clause}
            ORDER BY created_at DESC
        ''', params)
        
        rows = cursor.fetchall()
        listings = []
        
        for row in rows:
            listing_id = row[0]
            
            # 获取文件列表
            cursor.execute('''
                SELECT file_path, file_name, file_size, file_md5
                FROM listing_files
                WHERE listing_id = ?
            ''', (listing_id,))
            
            files = []
            for file_row in cursor.fetchall():
                files.append({
                    "file_path": file_row[0],
                    "file_name": file_row[1],
                    "file_size": file_row[2],
                    "file_md5": file_row[3]
                })
            
            listings.append({
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "listing_type": row[3],
                "price_cents": row[4],
                "status": row[5],
                "review_status": row[6],
                "created_at": row[7],
                "updated_at": row[8],
                "published_at": row[9],
                "files": files
            })
        
        return JSONResponse({
            "status": "success",
            "listings": listings,
            "total": len(listings)
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.get("/review")
async def api_listings_review(status: str = Query("pending"), 
                             limit: int = Query(20, ge=1, le=200), 
                             offset: int = Query(0, ge=0)):
    """管理端查看上架审核队列"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT l.id, l.seller_id, l.title, l.description, l.listing_type, 
                   l.price_cents, l.status, l.review_status, l.created_at,
                   u.display_name
            FROM listings l
            LEFT JOIN users u ON l.seller_id = u.user_id
            WHERE l.review_status = ?
            ORDER BY l.created_at DESC
            LIMIT ? OFFSET ?
        ''', (status, limit, offset))
        
        rows = cursor.fetchall()
        listings = []
        
        for row in rows:
            listing_id = row[0]

            # 获取文件列表
            cursor.execute('''
                SELECT file_path, file_name, file_size
                FROM listing_files
                WHERE listing_id = ?
            ''', (listing_id,))

            files = []
            for file_row in cursor.fetchall():
                files.append({
                    "file_path": file_row[0],
                    "file_name": file_row[1],
                    "file_size": file_row[2]
                })

            # 获取最近一次审核记录
            cursor.execute('''
                SELECT status, remark, reviewer_id, reviewed_at
                FROM listing_reviews
                WHERE listing_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (listing_id,))
            
            review_row = cursor.fetchone()
            last_review = None
            if review_row:
                last_review = {
                    "status": review_row[0],
                    "remark": review_row[1],
                    "reviewer_id": review_row[2],
                    "reviewed_at": review_row[3]
                }

            # 统一返回结构，包含 seller 对象（供管理端使用）
            listings.append({
                "id": row[0],
                "seller_id": row[1],
                "title": row[2],
                "description": row[3],
                "listing_type": row[4],
                "price_cents": row[5],
                "status": row[6],
                "review_status": row[7],
                "created_at": row[8],
                "seller": {"user_id": row[1], "display_name": row[9]},
                "files": files,
                "last_review": last_review
            })
        
        # 获取总数
        cursor.execute('''
            SELECT COUNT(*) FROM listings WHERE review_status = ?
        ''', (status,))
        total = cursor.fetchone()[0]
        
        return JSONResponse({
            "status": "success",
            "listings": listings,
            "total": total
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.post("/{listing_id}/review")
async def api_listings_review_action(listing_id: int, payload: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """管理员提交审核结果"""
    status = payload.get("status")
    remark = payload.get("remark", "")
    reviewer_id = user.get("user_id") or "admin"
    # 允许的审核角色/用户可通过环境变量配置
    allowed_roles = [r.strip() for r in (os.getenv('REVIEWER_ROLES') or 'admin').split(',') if r.strip()]
    allowed_users = [u.strip() for u in (os.getenv('REVIEWER_USER_IDS') or '').split(',') if u.strip()]
    uid = user.get("user_id")
    urole = user.get("role")
    if (urole not in allowed_roles) and (uid not in allowed_users):
        raise HTTPException(status_code=403, detail="forbidden: reviewer not allowed")
    
    if not status or status not in ["approved", "rejected"]:
        return JSONResponse({"status": "error", "message": "invalid status"}, status_code=400)
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        # 检查商品是否存在且允许审核
        cursor.execute('''
            SELECT id, status FROM listings 
            WHERE id = ?
        ''', (listing_id,))
        
        listing_row = cursor.fetchone()
        if not listing_row:
            return JSONResponse({"status": "error", "message": "listing not found"}, status_code=404)
        
        current_status = listing_row[1]
        if current_status not in ["draft", "pending"]:
            return JSONResponse({"status": "error", "message": "listing not available for review"}, status_code=400)
        
        now = time.time()
        
        # 读取该 listing 的文件列表
        cursor.execute('''
            SELECT id, file_path, file_name
            FROM listing_files
            WHERE listing_id = ?
        ''', (listing_id,))
        file_rows = cursor.fetchall() or []

        # 目标目录（根据审核结果选择不同目录），并确保存在
        if status == 'approved':
            dst_dir = os.getenv('DEFAULT_DIR_MOVE_DST')
            if not dst_dir or not str(dst_dir).strip():
                dst_dir = '/商品市场/已上架文档'
        else:
            dst_dir = os.getenv('DEFAULT_DIR_REJECT_DST')
            if not dst_dir or not str(dst_dir).strip():
                dst_dir = '/商品市场/已驳回'

        # 确保网盘目录存在
        try:
            await _netdisk_ensure_directory(path=dst_dir)
        except Exception:
            # 不阻断事务，但会在最后统一反馈
            pass

        # 构造移动操作
        ops = []
        id_to_newpath = {}
        for fid, fpath, fname in file_rows:
            if not fpath:
                # 跳过空路径
                continue
            base = fname or (fpath.rsplit('/', 1)[-1] if '/' in fpath else fpath)
            new_path = (dst_dir.rstrip('/') + '/' + base)
            ops.append({"path": fpath, "dest": new_path})
            id_to_newpath[fid] = new_path

        # 调用网盘移动（按 fail 策略，避免覆盖）
        if ops:
            try:
                await _netdisk_move_files(ops, ondup='fail')
                # 网盘移动成功后，更新本地记录
                for fid, new_path in id_to_newpath.items():
                    cursor.execute('''
                        UPDATE listing_files SET file_path = ? WHERE id = ?
                    ''', (new_path, fid))
            except Exception:
                # 若网盘移动失败，不回滚审核结果，但不更新文件路径
                pass

        # 更新商品状态
        if status == "approved":
            cursor.execute('''
                UPDATE listings 
                SET status = 'live', review_status = 'approved', review_remark = ?, 
                    published_at = ?, updated_at = ?
                WHERE id = ?
            ''', (remark, now, now, listing_id))
            # 发送审核通过通知
            try:
                # 获取 seller_id 与 title
                cursor.execute('SELECT seller_id, title FROM listings WHERE id = ?', (listing_id,))
                _row = cursor.fetchone()
                if _row:
                    send_listing_approved_notification(_row[0], listing_id, _row[1])
            except Exception:
                pass
        else:
            cursor.execute('''
                UPDATE listings 
                SET status = 'rejected', review_status = 'rejected', review_remark = ?, 
                    updated_at = ?
                WHERE id = ?
            ''', (remark, now, listing_id))
            # 发送审核拒绝通知
            try:
                cursor.execute('SELECT seller_id, title FROM listings WHERE id = ?', (listing_id,))
                _row = cursor.fetchone()
                if _row:
                    send_listing_rejected_notification(_row[0], listing_id, _row[1], remark or '')
            except Exception:
                pass

        # 创建审核记录
        cursor.execute('''
            INSERT INTO listing_reviews (listing_id, reviewer_id, status, remark, reviewed_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (listing_id, reviewer_id, status, remark, now))
        
        conn.commit()
        
        return JSONResponse({
            "status": "success",
            "message": f"listing {status} successfully"
        })
        
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)
    finally:
        conn.close()

@router.get("/{listing_id}")
async def api_listings_detail(listing_id: int, seller_id: Optional[str] = Query(None)):
    """返回商品详情"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        where_clause = "WHERE l.id = ?"
        params = [listing_id]
        
        if seller_id:
            where_clause += " AND l.seller_id = ?"
            params.append(seller_id)
        
        cursor.execute(f'''
            SELECT l.id, l.seller_id, l.title, l.description, l.listing_type, 
                   l.price_cents, l.status, l.review_status, l.review_remark,
                   l.created_at, l.updated_at, l.published_at,
                   u.display_name
            FROM listings l
            LEFT JOIN users u ON l.seller_id = u.user_id
            {where_clause}
        ''', params)
        
        row = cursor.fetchone()
        if not row:
            return JSONResponse({"status": "error", "message": "listing not found"}, status_code=404)
        
        # 获取文件列表
        cursor.execute('''
            SELECT file_path, file_name, file_size, file_md5
            FROM listing_files
            WHERE listing_id = ?
        ''', (listing_id,))
        
        files = []
        for file_row in cursor.fetchall():
            files.append({
                "file_path": file_row[0],
                "file_name": file_row[1],
                "file_size": file_row[2],
                "file_md5": file_row[3]
            })
        
        # 获取审核记录
        cursor.execute('''
            SELECT status, remark, reviewer_id, reviewed_at, created_at
            FROM listing_reviews
            WHERE listing_id = ?
            ORDER BY created_at DESC
        ''', (listing_id,))
        
        reviews = []
        for review_row in cursor.fetchall():
            reviews.append({
                "status": review_row[0],
                "remark": review_row[1],
                "reviewer_id": review_row[2],
                "reviewed_at": review_row[3],
                "created_at": review_row[4]
            })
        
        return JSONResponse({
            "status": "success",
            "listing": {
                "id": row[0],
                "seller_id": row[1],
                "seller_name": row[12],
                "seller": {"user_id": row[1], "display_name": row[12]},
                "title": row[2],
                "description": row[3],
                "listing_type": row[4],
                "price_cents": row[5],
                "status": row[6],
                "review_status": row[7],
                "review_remark": row[8],
                "created_at": row[9],
                "updated_at": row[10],
                "published_at": row[11],
                "files": files,
                "reviews": reviews
            }
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()

@router.get("/public")
async def api_listings_public(keyword: Optional[str] = None,
                             listing_type: Optional[str] = None,
                             limit: int = 20,
                             offset: int = 0):
    """买家浏览上架中的商品"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        where_clause = "WHERE l.status = 'live' AND l.review_status = 'approved'"
        params = []
        
        if keyword:
            where_clause += " AND (l.title LIKE ? OR l.description LIKE ?)"
            kw = f"%{keyword}%"
            params.extend([kw, kw])
        
        if listing_type:
            where_clause += " AND l.listing_type = ?"
            params.append(listing_type)
        
        cursor.execute(f'''
            SELECT l.id, l.seller_id, l.title, l.description, l.listing_type, 
                   l.price_cents, l.created_at, l.published_at,
                   u.display_name, u.avatar_url,
                   COUNT(lf.id) as file_count
            FROM listings l
            LEFT JOIN users u ON l.seller_id = u.user_id
            LEFT JOIN listing_files lf ON l.id = lf.listing_id
            {where_clause}
            GROUP BY l.id
            ORDER BY l.published_at DESC
            LIMIT ? OFFSET ?
        ''', (*params, limit, offset))
        
        rows = cursor.fetchall()
        listings = []
        
        for row in rows:
            listings.append({
                "id": row[0],
                "seller_id": row[1],
                "seller_name": row[8],
                "seller_avatar": row[9],
                "title": row[2],
                "description": row[3],
                "listing_type": row[4],
                "price_cents": row[5],
                "created_at": row[6],
                "published_at": row[7],
                "file_count": row[10]
            })
        
        # 获取总数
        cursor.execute(f'''
            SELECT COUNT(DISTINCT l.id)
            FROM listings l
            {where_clause}
        ''', params)
        total = cursor.fetchone()[0]
        
        return JSONResponse({
            "status": "success",
            "listings": listings,
            "total": total
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()
