#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财务对账报告 API
"""

from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any

from api.deps import get_current_user

router = APIRouter(prefix="/api/reports", tags=["Reports"]) 

@router.get("/finance/reconcile")
async def api_finance_reconcile(start: float = Query(None), end: float = Query(None), user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    from scripts.reconcile_finance import reconcile
    import time
    end_ts = end or time.time()
    start_ts = start or (end_ts - 24*3600)
    try:
        summary, anomalies = reconcile(start_ts, end_ts)
        return JSONResponse({"status":"success","summary":summary,"anomalies":anomalies})
    except Exception as e:
        return JSONResponse({"status":"error","message":str(e)}, status_code=500)


