#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
退款管理API
"""

from fastapi import APIRouter, Query, Path, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import sqlite3, time
from services.db import init_sync_db
from services.order_service import process_refund
from api.deps import get_current_user

router = APIRouter(prefix="/api/refund-requests", tags=["Refunds"])

@router.get("")
async def list_refund_requests(status: Optional[str] = Query(None), page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), user: Dict[str, Any] = Depends(get_current_user)):
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='forbidden')
    db_path = init_sync_db(); conn = sqlite3.connect(db_path); cursor = conn.cursor()
    try:
        where = []
        params = []
        if status:
            where.append("status = ?"); params.append(status)
        where_clause = (" WHERE "+" AND ".join(where)) if where else ""
        offset = (page-1)*size
        cursor.execute(f"SELECT id, order_id, buyer_id, seller_id, amount_cents, reason, status, created_at, processed_at, reviewer_id, remark FROM refund_requests{where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?", params+[size, offset])
        rows = cursor.fetchall()
        items = []
        for r in rows:
            items.append({
                "id": r[0], "order_id": r[1], "buyer_id": r[2], "seller_id": r[3],
                "amount_cents": r[4], "reason": r[5], "status": r[6],
                "created_at": r[7], "processed_at": r[8], "reviewer_id": r[9], "remark": r[10]
            })
        cursor.execute(f"SELECT COUNT(*) FROM refund_requests{where_clause}", params)
        total = cursor.fetchone()[0]
        return JSONResponse({"status":"success","items":items,"page":page,"size":size,"total":total})
    except Exception as e:
        return JSONResponse({"status":"error","message":str(e)}, status_code=500)
    finally:
        conn.close()

@router.post("/{refund_id}/process")
async def api_refund_process(refund_id: int = Path(...), payload: Dict[str, Any] = None, user: Dict[str, Any] = Depends(get_current_user)):
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='forbidden')
    operator_id = user.get('user_id') or 'admin'
    remark = (payload or {}).get("remark") or ""
    resp = process_refund(refund_id, operator_id, remark)
    return JSONResponse(resp, status_code=(200 if resp.get('status')=='success' else 400))


