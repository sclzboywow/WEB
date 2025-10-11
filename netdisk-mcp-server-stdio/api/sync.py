#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步/运维相关简单统计 API
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import sqlite3
from typing import Dict, Any, List, Tuple
import time
import os
import json
import threading
import asyncio
import re


from services.db import init_sync_db, get_db_connection
from api.netdisk import ensure_directory, move_files

router = APIRouter(prefix="/api/sync", tags=["Sync"]) 


@router.get("/db-stats")
async def api_db_stats():
    """返回数据库关键表的基础统计信息，供前端仪表盘使用。"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    def count(table: str) -> int:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return int(cur.fetchone()[0])
        except Exception:
            return 0
    def count_where(sql: str, params: tuple = ()) -> int:
        try:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row[0] if row and row[0] is not None else 0)
        except Exception:
            return 0
    try:
        stats: Dict[str, Any] = {
            "users": count("users"),
            "listings": count("listings"),
            "orders": count("orders"),
            "order_items": count("order_items"),
            "order_payments": count("order_payments"),
            "notifications": count("notifications"),
            "refund_requests": count("refund_requests"),
            "payout_requests": count("payout_requests"),
            "wallet_logs": count("wallet_logs"),
            "risk_events": count("risk_events"),
        }
        # 同步与文件索引相关统计
        stats["sync_tasks_total"] = count("sync_tasks")
        stats["file_records_total"] = count("file_records")
        # 分类维度（仅统计文件，不含目录）
        stats["file_images"] = count_where("SELECT COUNT(1) FROM file_records WHERE isdir=0 AND category=3")
        stats["file_videos"] = count_where("SELECT COUNT(1) FROM file_records WHERE isdir=0 AND category=1")
        stats["file_docs"] = count_where("SELECT COUNT(1) FROM file_records WHERE isdir=0 AND category=4")
        stats["file_audio"] = count_where("SELECT COUNT(1) FROM file_records WHERE isdir=0 AND category=2")
        stats["file_others"] = count_where("SELECT COUNT(1) FROM file_records WHERE isdir=0 AND (category NOT IN (1,2,3,4,7) OR category IS NULL)")
        return JSONResponse({"status": "success", "stats": stats})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        conn.close()


@router.get("/status")
async def api_sync_status():
    """返回当前同步状态"""
    # 这里可以添加实际的同步状态检查逻辑
    # 目前返回一个简单的状态
    return JSONResponse({
        "status": "idle",
        "message": "暂无同步任务",
        "timestamp": None
    })


@router.post("/dir-scan")
async def api_dir_scan(payload: Dict[str, Any]):
    """触发一次基于 HTTP 的目录扫描，同步缓存（示例实现：仅统计，不落库）。"""
    from api.netdisk import list_files  # 复用 HTTP 列表
    path = payload.get('path') or '/'
    limit = int(payload.get('limit') or 200)
    start = int(payload.get('start') or 0)
    scanned: List[Dict[str, Any]] = []
    has_more = True
    try:
        while has_more:
            result = await list_files(path=path, start=start, limit=limit)
            files = result.get('files') or []
            scanned.extend(files)
            has_more = bool(result.get('has_more')) and len(files) > 0
            start += limit
            if len(scanned) >= 2000:
                break
        return JSONResponse({
            "status": "success",
            "path": path,
            "scanned": len(scanned),
            "sample": scanned[:10],
            "has_more": has_more
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)


# ============== 增量同步（基于本地 JSON 索引/状态） ==============

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.sync_state.json')
SHARED_GALLERY_ROOT = os.getenv('SHARED_GALLERY_ROOT', '/共享图集')
SHARED_GALLERY_BUCKET_SIZE = int(os.getenv('SHARED_GALLERY_BUCKET_SIZE', '1000'))
SHARED_GALLERY_MAX_FILES = int(os.getenv('SHARED_GALLERY_MAX_FILES', '100000'))
SHARED_GALLERY_SHARD_PREFIX = os.getenv('SHARED_GALLERY_SHARD_PREFIX', 'batch_')
_SHARED_GALLERY_LOCK = asyncio.Lock()

# 轻量内存任务管理（仅为旧前端的同步 UI 提供兼容态）
_TASKS: Dict[int, Dict[str, Any]] = {}
_BG_THREADS: Dict[int, threading.Thread] = {}
_BG_LOCK = threading.Lock()

def _gen_sync_id() -> int:
    # 简单按秒生成，避免过长
    return int(time.time() * 1000) % 10_000_000

def _sleep_s(seconds: float):
    try:
        time.sleep(seconds)
    except Exception:
        pass

def _bg_sync_loop(sync_id: int, path: str, max_pages: int, page_limit: int, delay_s: float):
    """后台线程：逐页调用 step，直至完成或被取消。"""
    pages_done = 0
    try:
        # 先确保已启动增量状态
        try:
            import asyncio
            asyncio.run(api_incr_start({'path': path, 'limit': page_limit, 'max_pages': max_pages}))
        except Exception:
            pass
        while True:
            with _BG_LOCK:
                t = _TASKS.get(sync_id)
                if not t or t.get('status') != 'running':
                    break
            try:
                import asyncio
                step_res = asyncio.run(api_incr_step({'path': path, 'limit': page_limit}))
                # 解析 has_more
                try:
                    data = json.loads(step_res.body.decode('utf-8')) if hasattr(step_res, 'body') else {}
                except Exception:
                    data = {}
                pages_done += 1
                if max_pages and pages_done >= max_pages:
                    break
                if not data.get('has_more'):
                    break
            except Exception:
                # 轻微退避后继续
                _sleep_s(1.0)
            # 限速，避免阻塞其他 API
            _sleep_s(delay_s)
        # 完成阶段
        try:
            import asyncio
            asyncio.run(api_incr_finish({'path': path}))
        except Exception:
            pass
    finally:
        with _BG_LOCK:
            if sync_id in _TASKS:
                _TASKS[sync_id]['status'] = 'completed'
                _TASKS[sync_id]['finished_at'] = int(time.time())
            _BG_THREADS.pop(sync_id, None)

def _load_state() -> Dict[str, Any]:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

def _save_state(data: Dict[str, Any]):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _path_key(path: str) -> str:
    return path if path and path.startswith('/') else f"/{path or ''}"

async def _rebalance_shared_gallery_if_needed(path: str, items: List[Dict[str, Any]]) -> None:
    """将直接位于 /共享图集 根下的文件搬入分片子目录。
    - 仅在 path == SHARED_GALLERY_ROOT 时运行
    - 读取 DB 统计分片现有数量
    - 使用官方 move_files & ensure_directory 搬运，ondup='fail'
    """
    if _path_key(path) != _path_key(SHARED_GALLERY_ROOT):
        return
    if not items:
        return
    # 仅挑选当前页直接位于根下的文件
    root_prefix = _path_key(SHARED_GALLERY_ROOT) + '/'
    direct_files: List[Dict[str, Any]] = []
    for it in items:
        try:
            if int(it.get('isdir') or 0) != 0:
                continue
            p = it.get('path') or ''
            if not p.startswith(root_prefix):
                continue
            # 直接子项：只包含一个 '/'
            if p.count('/') == root_prefix.count('/'):
                # 极端情况下 path 可能含重复斜杠，降级判定
                pass
            # 更稳健：去除前缀后的余部不含 '/'
            rest = p[len(root_prefix):]
            if '/' in rest:
                continue
            direct_files.append(it)
        except Exception:
            continue
    if not direct_files:
        return

    async with _SHARED_GALLERY_LOCK:
        # 统计当前库内 /共享图集/ 下的各分片目录文件数
        shard_counts: Dict[str, int] = {}
        total_files = 0
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT file_path FROM file_records WHERE isdir=0 AND file_path LIKE ?", (f"{root_prefix}%",))
            rows = cur.fetchall()
            for (fp,) in rows:
                total_files += 1
                # 提取第一层子目录名
                try:
                    rel = fp[len(root_prefix):]
                    first = rel.split('/', 1)[0]
                    # 仅统计符合 batch_ 命名的子目录
                    if first and first.startswith(SHARED_GALLERY_SHARD_PREFIX):
                        shard_counts[first] = shard_counts.get(first, 0) + 1
                except Exception:
                    continue
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

        # 总量上限检查
        if total_files >= SHARED_GALLERY_MAX_FILES:
            try:
                print(f"shared-gallery.limit-hit total={total_files} max={SHARED_GALLERY_MAX_FILES}")
            except Exception:
                pass
            return

        # 计算可用 shard；寻找第一个计数 < BUCKET_SIZE 的分片
        max_shards = SHARED_GALLERY_MAX_FILES // SHARED_GALLERY_BUCKET_SIZE
        def _format_shard(idx: int) -> str:
            return f"{SHARED_GALLERY_SHARD_PREFIX}{idx:03d}"

        target_shard = None
        # 先按序查找已有 shard 是否有空位
        for i in range(1, max_shards + 1):
            name = _format_shard(i)
            if shard_counts.get(name, 0) < SHARED_GALLERY_BUCKET_SIZE:
                target_shard = name
                break
        if target_shard is None:
            # 没有空位：如还能新建，则创建下一号；否则返回
            existing = 0
            for k in shard_counts.keys():
                if k.startswith(SHARED_GALLERY_SHARD_PREFIX):
                    existing += 1
            if existing >= max_shards:
                try:
                    print(f"shared-gallery.no-slot existing={existing} max_shards={max_shards}")
                except Exception:
                    pass
                return
            target_shard = _format_shard(existing + 1)

        # 确保目标目录存在
        target_dir = f"{_path_key(SHARED_GALLERY_ROOT)}/{target_shard}"
        try:
            _ = await ensure_directory(target_dir)
        except Exception:
            # 目录存在或创建失败都不中断主流程
            pass

        # 组装 move 操作：每批 20 条
        ops: List[Dict[str, Any]] = []
        moved = 0
        for it in direct_files:
            src = it.get('path') or ''
            name = it.get('server_filename') or os.path.basename(src)
            dst = f"{target_dir}/{name}"
            ops.append({'path': src, 'dest': dst})
            if len(ops) >= 20:
                try:
                    res = await move_files(ops, ondup='fail')
                    moved += len(ops)
                except Exception:
                    pass
                ops = []
        if ops:
            try:
                res = await move_files(ops, ondup='fail')
                moved += len(ops)
            except Exception:
                pass

        # 更新 DB 中这些文件的路径
        if moved:
            try:
                conn = get_db_connection(); cur = conn.cursor()
                for it in direct_files:
                    old_p = it.get('path') or ''
                    name = it.get('server_filename') or os.path.basename(old_p)
                    new_p = f"{target_dir}/{name}"
                    cur.execute(
                        "UPDATE file_records SET file_path=?, file_name=? WHERE file_path=? AND isdir=0",
                        (new_p, name, old_p)
                    )
                conn.commit()
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        try:
            print(f"shared-gallery.rebalance shard={target_shard} moved={moved} path={path}")
        except Exception:
            pass

@router.get('/incremental/status')
async def api_incr_status(path: str = '/'):
    state = _load_state()
    key = _path_key(path)
    ps = state.get('paths', {}).get(key, {})
    return JSONResponse({
        'status': 'success',
        'path': key,
        'state': {
            'since_mtime': ps.get('since_mtime', 0),
            'last_start': ps.get('last_start', 0),
            'page_limit': ps.get('page_limit', 200),
            'in_pass_seen': len(ps.get('pass_seen', [])),
            'indexed_total': len((ps.get('index') or {}).get('items', {})),
            'last_run': ps.get('last_run'),
        }
    })

@router.post('/incremental/start')
async def api_incr_start(payload: Dict[str, Any]):
    path = _path_key(payload.get('path') or '/')
    page_limit = int(payload.get('limit') or 200)
    since_mtime = payload.get('since_mtime')
    state = _load_state()
    paths = state.setdefault('paths', {})
    ps = paths.setdefault(path, {})
    # 初始化/重置本次扫描状态
    if since_mtime is None:
        # 如未指定，从已有索引的最大 mtime 继续
        items = (ps.get('index') or {}).get('items', {})
        max_mtime = 0
        for it in items.values():
            try:
                mt = int(it.get('server_mtime') or 0)
                if mt > max_mtime:
                    max_mtime = mt
            except Exception:
                pass
        since_mtime = max_mtime
    ps['since_mtime'] = int(since_mtime or 0)
    ps['last_start'] = 0
    ps['page_limit'] = page_limit
    ps['pass_seen'] = []
    ps.setdefault('index', {}).setdefault('items', {})
    ps['last_run'] = int(time.time())
    _save_state(state)
    # 写入/更新 SQLite 任务行
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sync_tasks (sync_id, path, status, max_pages, current_page, processed_files, start_time, last_update, client_id, is_resume)
            VALUES (?, ?, 'running', ?, 0, 0, ?, ?, ?, ?)
            ON CONFLICT(sync_id) DO UPDATE SET
                path=excluded.path,
                status='running',
                max_pages=excluded.max_pages,
                last_update=excluded.last_update,
                is_resume=excluded.is_resume
            """,
            (
                str(int(time.time()*1000)),  # 这里留一个冗余占位以兼容旧库，实际 start API 会再写入
                path,
                int(payload.get('max_pages') or 0),
                time.time(),
                time.time(),
                (payload.get('client_id') or ''),
                1 if payload.get('is_resume') else 0,
            )
        )
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return JSONResponse({'status': 'success', 'path': path, 'since_mtime': ps['since_mtime'], 'page_limit': page_limit})

@router.post('/incremental/step')
async def api_incr_step(payload: Dict[str, Any]):
    """按时间倒序分页拉取，识别新增/更新；删除在 finish 阶段统一计算。"""
    from api.netdisk import _request_pan_api  # 直接调用底层 HTTP
    path = _path_key(payload.get('path') or '/')
    state = _load_state(); paths = state.setdefault('paths', {}); ps = paths.setdefault(path, {})
    start = int(payload.get('start') if payload.get('start') is not None else ps.get('last_start', 0))
    limit = int(payload.get('limit') or ps.get('page_limit') or 200)
    since_mtime = int(ps.get('since_mtime') or 0)
    # 拉取一页（按时间）；若 errno=1，保持相同分页尺寸重试一次（轻微退避），不降级 page size
    def _list_with_limit(lim: int) -> Dict[str, Any]:
        return _request_pan_api('https://pan.baidu.com/rest/2.0/xpan/file', {
            'method': 'list',
            'dir': path,
            'start': start,
            'limit': lim,
            'order': 'time',
            'desc': 1,
        })
    resp = _list_with_limit(limit)
    effective_limit = limit
    if resp.get('status') == 'error' and int(resp.get('errno') or 0) == 1:
        try:
            print(f"sync.step retry(dir={path} start={start} limit={limit}) errno=1 backoff 0.8s")
        except Exception:
            pass
        try:
            time.sleep(0.8)
        except Exception:
            pass
        resp = _list_with_limit(limit)
    if resp.get('status') == 'error':
        # 打印详细错误，便于定位（无 emoji，兼容 Windows 控制台）
        try:
            print(f"sync.step error dir={path} start={start} limit={limit} errno={resp.get('errno')} msg={resp.get('message')}")
        except Exception:
            pass
        return JSONResponse({'status': 'error', 'message': resp.get('message'), 'errno': resp.get('errno')}, status_code=502)
    items = resp.get('list') or []
    index_items = ps.setdefault('index', {}).setdefault('items', {})
    pass_seen: List[str] = ps.setdefault('pass_seen', [])
    added = 0; updated = 0
    for it in items:
        fs_id = str(it.get('fs_id'))
        if not fs_id:
            continue
        server_mtime = int(it.get('server_mtime') or 0)
        if since_mtime and server_mtime <= since_mtime:
            # 本页以及后续页均早于 since，停止
            ps['last_start'] = start + len(items)
            state['paths'][path] = ps; _save_state(state)
            try:
                print(f"sync.step boundary dir={path} start={start} limit={limit} since={since_mtime} added={added} updated={updated}")
            except Exception:
                pass
            return JSONResponse({'status': 'success', 'path': path, 'added': added, 'updated': updated, 'has_more': False, 'hit_since_boundary': True, 'next_start': ps['last_start']})
        prev = index_items.get(fs_id)
        if not prev:
            index_items[fs_id] = {
                'fs_id': it.get('fs_id'),
                'path': it.get('path'),
                'server_filename': it.get('server_filename'),
                'size': it.get('size'),
                'server_mtime': server_mtime,
                'isdir': it.get('isdir'),
                'category': it.get('category'),
                'md5': it.get('md5'),
            }
            added += 1
        else:
            # 如有变更（mtime/size/md5），视为更新
            if int(prev.get('server_mtime') or 0) != server_mtime or (prev.get('size') != it.get('size')) or (prev.get('md5') != it.get('md5')):
                prev.update({
                    'path': it.get('path'),
                    'server_filename': it.get('server_filename'),
                    'size': it.get('size'),
                    'server_mtime': server_mtime,
                    'isdir': it.get('isdir'),
                    'category': it.get('category'),
                    'md5': it.get('md5'),
                })
                updated += 1
        if fs_id not in pass_seen:
            pass_seen.append(fs_id)
    # has_more 兼容 1/0 与 true/false；若接口未给出但本页条数达到上限，也认为可能还有下一页
    rhm = resp.get('has_more')
    try:
        has_more_flag = (int(rhm) == 1)
    except Exception:
        has_more_flag = bool(rhm)
    has_more = (has_more_flag and len(items) > 0) or (len(items) >= effective_limit and not (since_mtime and len(items) > 0 and int(items[-1].get('server_mtime') or 0) <= since_mtime))
    ps['last_start'] = start + len(items)
    ps['last_run'] = int(time.time())
    state['paths'][path] = ps; _save_state(state)
    try:
        print(f"sync.step ok dir={path} start={start} limit={limit} count={len(items)} added={added} updated={updated} has_more={has_more}")
    except Exception:
        pass
    # 返回当页必要字段，便于调用方直接入库，避免二次拉取
    slim_items = []
    for it in items:
        slim_items.append({
            'fs_id': it.get('fs_id'),
            'path': it.get('path'),
            'server_filename': it.get('server_filename'),
            'size': it.get('size'),
            'server_mtime': it.get('server_mtime'),
            'server_ctime': it.get('server_ctime'),
            'category': it.get('category'),
            'isdir': it.get('isdir'),
            'md5': it.get('md5'),
        })
    return JSONResponse({'status': 'success', 'path': path, 'added': added, 'updated': updated, 'has_more': has_more, 'next_start': ps['last_start'], 'items': slim_items})

@router.post('/incremental/finish')
async def api_incr_finish(payload: Dict[str, Any]):
    path = _path_key(payload.get('path') or '/')
    state = _load_state(); paths = state.setdefault('paths', {}); ps = paths.setdefault(path, {})
    index_items: Dict[str, Any] = ps.get('index', {}).get('items', {})
    pass_seen: List[str] = ps.get('pass_seen') or []
    # 识别删除（仅限本路径已收录但本次扫描未见）
    deleted = []
    for fs_id in list(index_items.keys()):
        if fs_id not in pass_seen:
            deleted.append(fs_id)
    for fs_id in deleted:
        index_items.pop(fs_id, None)
    # 完成本次扫描：提升 since_mtime 为 pass 中最大值，重置状态
    max_mtime = 0
    for it in index_items.values():
        try:
            mt = int(it.get('server_mtime') or 0)
            if mt > max_mtime:
                max_mtime = mt
        except Exception:
            pass
    ps['since_mtime'] = max_mtime
    ps['last_start'] = 0
    ps['pass_seen'] = []
    ps['last_run'] = int(time.time())
    state['paths'][path] = ps; _save_state(state)
    return JSONResponse({'status': 'success', 'path': path, 'deleted': len(deleted), 'since_mtime': ps['since_mtime']})

@router.post('/incremental/reset')
async def api_incr_reset(payload: Dict[str, Any]):
    """清空某个目录在 .sync_state.json 中的增量状态，便于全新同步。"""
    path = _path_key(payload.get('path') or '/')
    state = _load_state()
    try:
        if 'paths' in state and path in state['paths']:
            state['paths'].pop(path, None)
            _save_state(state)
            return JSONResponse({'status': 'success', 'message': 'state cleared', 'path': path})
        return JSONResponse({'status': 'success', 'message': 'no state to clear', 'path': path})
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)

# ====== 兼容老路径：/api/sync/start|step|finish|progress ======

@router.post('/start')
async def api_sync_start(payload: Dict[str, Any]):
    # 兼容前端：分配 sync_id，并驱动一次增量启动
    sync_id = _gen_sync_id()
    path = _path_key((payload or {}).get('path') or '/')
    max_pages = int((payload or {}).get('max_pages') or 0)
    _TASKS[sync_id] = {
        'id': sync_id,
        'path': path,
        'status': 'running',
        'started_at': int(time.time()),
        'is_resume': bool((payload or {}).get('is_resume')),
        'is_unlimited': (max_pages == 0),
        'max_pages': max_pages,
        'progress': { 'added': 0, 'updated': 0, 'deleted': 0, 'pages': 0 }
    }
    _ = await api_incr_start(payload)
    # 将任务写入 SQLite
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sync_tasks (sync_id, path, status, max_pages, current_page, processed_files, start_time, last_update, client_id, is_resume)
            VALUES (?, ?, 'running', ?, 0, 0, ?, ?, ?, ?)
            ON CONFLICT(sync_id) DO UPDATE SET
                status='running',
                path=excluded.path,
                max_pages=excluded.max_pages,
                last_update=excluded.last_update,
                is_resume=excluded.is_resume
            """,
            (
                str(sync_id),
                path,
                max_pages,
                time.time(),
                time.time(),
                (payload.get('client_id') or ''),
                1 if _TASKS[sync_id]['is_resume'] else 0,
            )
        )
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return JSONResponse({
        'status': 'success',
        'message': '同步任务已启动',
        'sync_id': sync_id,
        'is_resume': _TASKS[sync_id]['is_resume']
    })

@router.post('/start_background')
async def api_sync_start_background(payload: Dict[str, Any]):
    """在后台线程中发起全量/增量同步，不阻塞请求线程。"""
    path = _path_key((payload or {}).get('path') or '/')
    max_pages = int((payload or {}).get('max_pages') or 0)
    # 将默认页大小降到 200，支持通过 .env 或参数覆盖；默认延迟提升到 0.4s
    page_limit = int((payload or {}).get('limit') or int(os.getenv('SYNC_PAGE_LIMIT', '200')))
    delay_s = float((payload or {}).get('delay_s') or float(os.getenv('SYNC_DELAY_S', '0.4')))
    sync_id = _gen_sync_id()
    with _BG_LOCK:
        if any(t.get('status') == 'running' and t.get('path') == path for t in _TASKS.values()):
            return JSONResponse({'status': 'error', 'message': '该路径已有同步任务在运行'}, status_code=409)
        _TASKS[sync_id] = {
            'id': sync_id,
            'path': path,
            'status': 'running',
            'started_at': int(time.time()),
            'is_resume': bool((payload or {}).get('is_resume')),
            'is_unlimited': (max_pages == 0),
            'max_pages': max_pages,
            'progress': { 'added': 0, 'updated': 0, 'deleted': 0, 'pages': 0 }
        }
        th = threading.Thread(target=_bg_sync_loop, args=(sync_id, path, max_pages, page_limit, delay_s), daemon=True)
        _BG_THREADS[sync_id] = th
        th.start()
    return JSONResponse({'status': 'success', 'message': '后台同步已启动', 'sync_id': sync_id})

@router.post('/cancel')
async def api_sync_cancel(payload: Dict[str, Any]):
    """请求取消后台任务（标记为取消；线程检查到状态变化后结束）。"""
    sync_id = int((payload or {}).get('sync_id') or 0)
    if not sync_id:
        return JSONResponse({'status': 'error', 'message': 'missing sync_id'}, status_code=400)
    with _BG_LOCK:
        t = _TASKS.get(sync_id)
        if not t:
            return JSONResponse({'status': 'error', 'message': 'task not found'}, status_code=404)
        if t.get('status') != 'running':
            return JSONResponse({'status': 'success', 'message': 'task not running'})
        t['status'] = 'cancelling'
    return JSONResponse({'status': 'success', 'message': 'cancel requested'})

@router.post('/step')
async def api_sync_step(payload: Dict[str, Any]):
    res = await api_incr_step(payload)
    # 采集一次统计，便于前端显示
    try:
        data = json.loads(res.body.decode('utf-8')) if hasattr(res, 'body') else {}
        path = _path_key((payload or {}).get('path') or '/')
        # 找到该 path 的任务并更新进度
        for t in _TASKS.values():
            if t.get('path') == path and t.get('status') == 'running':
                pg = t.get('progress') or {}
                added_cnt = int(data.get('added') or 0)
                updated_cnt = int(data.get('updated') or 0)
                pg['added'] = (pg.get('added') or 0) + added_cnt
                pg['updated'] = (pg.get('updated') or 0) + updated_cnt
                pg['pages'] = (pg.get('pages') or 0) + 1
                t['progress'] = pg
                # 同步写 DB：使用本次返回 items 直接 upsert，避免二次请求
                try:
                    conn = get_db_connection(); cur = conn.cursor()
                    state_items = data.get('items') or []
                    sync_id_row = None
                    for sid, tv in _TASKS.items():
                        if tv is t:
                            sync_id_row = sid; break
                    # upsert 每条记录（以 sync_id+fs_id 组合）
                    for it in state_items:
                        cur.execute(
                            """
                            UPDATE file_records
                               SET file_path=?, file_name=?, file_size=?, file_md5=?, modify_time=?, create_time=?, category=?, isdir=?, status='indexed'
                             WHERE sync_id=? AND fs_id=?
                            """,
                            (
                                it.get('path') or '',
                                it.get('server_filename') or '',
                                int(it.get('size') or 0),
                                it.get('md5') or '',
                                int(it.get('server_mtime') or 0),
                                int(it.get('server_ctime') or 0),
                                int(it.get('category') or 0),
                                int(it.get('isdir') or 0),
                                str(sync_id_row or ''),
                                int(it.get('fs_id') or 0),
                            )
                        )
                        if cur.rowcount == 0:
                            cur.execute(
                                """
                                INSERT INTO file_records (sync_id, file_path, file_name, file_size, file_md5, modify_time, create_time, category, isdir, fs_id, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed')
                                """,
                                (
                                    str(sync_id_row or ''),
                                    it.get('path') or '',
                                    it.get('server_filename') or '',
                                    int(it.get('size') or 0),
                                    it.get('md5') or '',
                                    int(it.get('server_mtime') or 0),
                                    int(it.get('server_ctime') or 0),
                                    int(it.get('category') or 0),
                                    int(it.get('isdir') or 0),
                                    int(it.get('fs_id') or 0),
                                )
                            )
                    # 更新任务统计
                    cur.execute(
                        """
                        UPDATE sync_tasks
                           SET processed_files = processed_files + ?,
                               current_page = current_page + 1,
                               last_update = ?
                         WHERE sync_id = ?
                        """,
                        (
                            added_cnt + updated_cnt,
                            time.time(),
                            str(sync_id_row or ''),
                        )
                    )
                    conn.commit()
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
                # 分片搬运：仅在 /共享图集 根路径且本页包含直接子项文件时执行
                try:
                    await _rebalance_shared_gallery_if_needed(path, state_items)
                except Exception:
                    try:
                        print("shared-gallery.rebalance.error")
                    except Exception:
                        pass
                break
        # 在 upsert 完成后，尝试对 /共享图集 根下的文件做分片搬运
        try:
            state_items = data.get('items') or []
            await _rebalance_shared_gallery_if_needed(path, state_items)
        except Exception:
            # 不阻断原有流程
            pass
    except Exception:
        pass
    return res

@router.post('/finish')
async def api_sync_finish(payload: Dict[str, Any]):
    res = await api_incr_finish(payload)
    try:
        data = json.loads(res.body.decode('utf-8')) if hasattr(res, 'body') else {}
        path = _path_key((payload or {}).get('path') or '/')
        for t in _TASKS.values():
            if t.get('path') == path and t.get('status') == 'running':
                pg = t.get('progress') or {}
                pg['deleted'] = int(data.get('deleted') or 0)
                t['progress'] = pg
                t['status'] = 'completed'
                t['finished_at'] = int(time.time())
                # 写 DB 标记完成与删除状态
                try:
                    conn = get_db_connection(); cur = conn.cursor()
                    # 标记删除的文件
                    deleted_cnt = int(data.get('deleted') or 0)
                    if deleted_cnt > 0:
                        # 无具体 fs_id 列表在响应体中，这里从 JSON state 计算一遍即可；为了简单，此处仅更新任务统计
                        pass
                    # 读取当前 processed_files 作为 total_files 回填
                    cur.execute("SELECT processed_files FROM sync_tasks WHERE sync_id=?", (str(t.get('id') or ''),))
                    row = cur.fetchone(); total_files = int(row[0]) if row else 0
                    cur.execute(
                        """
                        UPDATE sync_tasks
                           SET status='completed',
                               total_files = ?,
                               last_update = ?
                         WHERE sync_id = ?
                        """,
                        (total_files, time.time(), str(t.get('id') or ''))
                    )
                    conn.commit()
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
                break
    except Exception:
        pass
    return res

@router.get('/progress')
async def api_sync_progress(path: str = '/'):
    # 返回最新任务状态（若存在）
    key = _path_key(path)
    latest = None
    for t in _TASKS.values():
        if t.get('path') == key:
            if (not latest) or (t.get('started_at', 0) > latest.get('started_at', 0)):
                latest = t
    base = await api_incr_status(key)
    try:
        base_data = json.loads(base.body.decode('utf-8')) if hasattr(base, 'body') else {}
    except Exception:
        base_data = {}
    if latest:
        base_data['task'] = latest
    return JSONResponse(base_data)

# ====== 旧前端轮询所需：按 sync_id 查询状态与统计 ======
@router.get('/status/{sync_id}')
async def api_sync_status_by_id(sync_id: int):
    t = _TASKS.get(int(sync_id))
    if not t:
        return JSONResponse({"status": "error", "message": "sync task not found"}, status_code=404)
    # 结合路径状态，拼出前端期望字段
    base = await api_incr_status(t.get('path') or '/')
    try:
        base_data = json.loads(base.body.decode('utf-8')) if hasattr(base, 'body') else {}
    except Exception:
        base_data = {}
    prog = t.get('progress') or {}
    # 粗略进度估计：页数推进 1%/页，上限 95%，完成后置 100%
    pct = min(95, (prog.get('pages') or 0))
    if t.get('status') == 'completed':
        pct = 100
    return JSONResponse({
        'status': t.get('status', 'running'),
        'progress': pct/100.0,
        'processed_files': (prog.get('added',0) + prog.get('updated',0) + prog.get('deleted',0)),
        'total_files': (base_data.get('state') or {}).get('indexed_total') or 0,
        'current_page': prog.get('pages') or 0,
        'max_pages': t.get('max_pages') or 0,
        'is_unlimited': bool(t.get('is_unlimited')),
        'is_resume': bool(t.get('is_resume')),
    })

@router.get('/stats/{sync_id}')
async def api_sync_stats_by_id(sync_id: int):
    t = _TASKS.get(int(sync_id))
    if not t:
        return JSONResponse({"status": "error", "message": "sync task not found"}, status_code=404)
    prog = t.get('progress') or {}
    return JSONResponse({
        'status': 'success',
        'stats': {
            'new': prog.get('added', 0),
            'updated': prog.get('updated', 0),
            'skipped': 0
        },
        'total_files': (prog.get('added',0) + prog.get('updated',0) + prog.get('deleted',0))
    })

