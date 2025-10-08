#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
购买记录别名路由（兼容旧路径 /api/purchases/mine）
"""

import sqlite3
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Optional
from services.db import init_sync_db

router = APIRouter(prefix="/api/purchases", tags=["Purchases(Alias)"])


@router.get("/mine")
async def api_purchases_mine_alias(buyer_id: str = Query(...)):
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT up.id, up.order_id, up.listing_id, up.file_path, 
                   up.download_count, up.last_accessed_at, up.created_at,
                   l.title, l.description, l.listing_type,
                   o.order_no, o.status as order_status
            FROM user_purchases up
            LEFT JOIN listings l ON up.listing_id = l.id
            LEFT JOIN orders o ON up.order_id = o.id
            WHERE up.buyer_id = ?
            ORDER BY up.created_at DESC
        ''', (buyer_id,))
        rows = cursor.fetchall()
        purchases = []
        for row in rows:
            purchases.append({
                "id": row[0],
                "order_id": row[1],
                "order_no": row[10],
                "listing_id": row[2],
                "title": row[7],
                "description": row[8],
                "listing_type": row[9],
                "file_path": row[3],
                "download_count": row[4],
                "last_accessed_at": row[5],
                "created_at": row[6],
                "order_status": row[11]
            })
        return JSONResponse({"status":"success","purchases":purchases,"total":len(purchases)})
    except Exception as e:
        return JSONResponse({"status":"error","message":str(e)}, status_code=500)
    finally:
        conn.close()


