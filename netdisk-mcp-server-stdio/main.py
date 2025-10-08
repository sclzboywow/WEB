#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主应用入口
FastAPI应用配置和路由挂载
"""

import os
from fastapi import FastAPI, APIRouter
import logging
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi import Body
from dotenv import load_dotenv

# 加载环境变量
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# 创建FastAPI应用实例
app = FastAPI(
    title="Baidu Netdisk MCP Server",
    description="百度网盘MCP服务器 - 支持文件管理、用户管理、商品交易、网盘操作等功能",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 精简访问日志：屏蔽 /api/notify 与 /api/sync/status 的访问日志
class _AccessPathFilter(logging.Filter):
    def filter(self, record):
        try:
            args = getattr(record, 'args', ()) or ()
            # uvicorn.access 默认 msg: '%s - "%s" %d', args: (client_addr, request_line, status_code)
            request_line = args[1] if len(args) > 1 else ''
            if isinstance(request_line, bytes):
                try:
                    request_line = request_line.decode('utf-8', errors='ignore')
                except Exception:
                    request_line = str(request_line)
            request_line = str(request_line)
            # 形如: 'GET /api/notify?since=0&limit=50 HTTP/1.1'
            parts = request_line.split(' ')
            path = parts[1] if len(parts) >= 2 else request_line
            if path.startswith('/api/notify') or path.startswith('/api/sync/status'):
                return False
        except Exception:
            pass
        return True

logging.getLogger('uvicorn.access').addFilter(_AccessPathFilter())

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态资源挂载
# src目录在上级目录
src_dir = os.path.join(os.path.dirname(BASE_DIR), "src")
if os.path.exists(src_dir):
    # 将 /assets 映射到根 src 下的 assets 目录，确保 /assets/js/common.js 等可用
    assets_dir = os.path.join(src_dir, "assets")
    mount_dir = assets_dir if os.path.exists(assets_dir) else src_dir
    app.mount("/assets", StaticFiles(directory=mount_dir), name="assets")
    
    # 挂载整个src目录，提供HTML页面访问
    app.mount("/src", StaticFiles(directory=src_dir), name="src")

# 导入并注册API路由
from api.auth import router as auth_router
from api.users import router as users_router
from api.payments import router as payments_router
from api.listings import router as listings_router
from api.orders import router as orders_router
from api.wallet import router as wallet_router
from api.notify import router as notify_router
from api.notifications import router as notifications_router
from api.refunds import router as refunds_router
from api.netdisk import router as netdisk_router
from api import netdisk as legacy_netdisk
try:
    from api import netdisk_full as legacy_netdisk_full
except Exception:
    legacy_netdisk_full = None
from api.reports import router as reports_router
from api.sync import router as sync_router
from api.purchases import router as purchases_alias_router


@app.get("/auth/result")
async def auth_result_compat():
    """兼容前端的 OAuth 结果接口：优先用 access_token 实时查询百度用户信息。"""
    try:
        import json, requests
        auth_file = os.path.join(BASE_DIR, "auth_result.json")
        if not os.path.exists(auth_file):
            return JSONResponse({"status": "error", "message": "auth_result.json not found"}, status_code=404)
        with open(auth_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 实时刷新用户信息（若有 access_token）
        token = (data or {}).get("token", {})
        access_token = token.get("access_token") or os.getenv("BAIDU_NETDISK_ACCESS_TOKEN")
        live_user_info = None
        if access_token:
            try:
                resp = requests.get(
                    "https://pan.baidu.com/rest/2.0/xpan/nas",
                    params={"method": "uinfo", "access_token": access_token},
                    timeout=10
                )
                if resp.ok:
                    live_user_info = resp.json()
            except Exception:
                live_user_info = None

        if live_user_info:
            data["user_info"] = live_user_info

        return JSONResponse({"status": "success", "result": data})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/user/info")
async def user_info_compat():
    """兼容前端的用户信息接口 - 从百度网盘API获取真实用户信息"""
    try:
        # 从环境变量获取百度网盘访问令牌
        access_token = os.getenv('BAIDU_NETDISK_ACCESS_TOKEN')
        if not access_token:
            return {
                "status": "error", 
                "message": "未配置百度网盘访问令牌",
                "user_info": None
            }
        
        # 使用百度网盘SDK获取用户信息
        try:
            from openapi_client.api.userinfo_api import UserinfoApi
            from openapi_client import ApiClient, Configuration
            
            # 配置API客户端
            configuration = Configuration()
            configuration.connection_pool_maxsize = 10
            configuration.retries = 3
            
            with ApiClient(configuration) as api_client:
                api_instance = UserinfoApi(api_client)
                
                # 调用用户信息API
                response = api_instance.xpannasuinfo(
                    access_token=access_token
                )
                
                if 'errno' in response and response['errno'] != 0:
                    return {
                        "status": "error",
                        "message": f"百度网盘API错误: {response['errno']}",
                        "user_info": None
                    }
                
                return {
                    "status": "success",
                    "message": "用户信息获取成功",
                    "user_info": {
                        "baidu_name": response.get('baidu_name', ''),
                        "netdisk_name": response.get('netdisk_name', ''),
                        "avatar_url": response.get('avatar_url', ''),
                        "vip_type": response.get('vip_type', 0),
                        "vip_level": response.get('vip_level', 0),
                        "uk": response.get('uk', 0)
                    }
                }
                
        except ImportError:
            # 如果SDK不可用，回退到演示数据
            return {
                "status": "success",
                "message": "用户信息查询功能已就绪（演示模式）",
                "user_info": {
                    "baidu_name": "演示用户",
                    "netdisk_name": "演示网盘用户",
                    "avatar_url": "",
                    "vip_type": 0,
                    "vip_level": 0,
                    "uk": 0
                },
                "note": "百度网盘SDK未安装，显示演示数据"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"获取用户信息时发生错误: {str(e)}",
            "user_info": None
        }

# 配置默认目录（来自 .env，未配置则使用 /共享图集）
@app.get("/api/config/defaults")
async def get_config_defaults():
    try:
        def _val(name: str, fallback: str) -> str:
            v = os.getenv(name)
            return v if isinstance(v, str) and v.strip() else fallback
        default_dir = _val('DEFAULT_DIR', '/共享图集')
        default_upload = _val('DEFAULT_DIR_UPLOAD', default_dir)
        if not default_upload:
            default_upload = '/来自：mcp_server/'
        # ondup 策略默认值（允许全局覆盖 + 各操作独立覆盖）
        ondup_global = _val('DEFAULT_ONDUP', '')
        def _ondup(name: str, fallback: str) -> str:
            base = ondup_global if ondup_global else fallback
            return _val(name, base)
        ondup_copy = _ondup('DEFAULT_ONDUP_COPY', 'newcopy')
        ondup_move = _ondup('DEFAULT_ONDUP_MOVE', 'fail')
        ondup_rename = _ondup('DEFAULT_ONDUP_RENAME', 'overwrite')
        ondup_upload = _ondup('DEFAULT_ONDUP_UPLOAD', 'ask')
        # C2C 相关：为复制/移动/删除分别提供默认目录（可分别指定源/目标）
        copy_src = _val('DEFAULT_DIR_COPY_SRC', default_dir)
        copy_dst = _val('DEFAULT_DIR_COPY_DST', default_dir)
        move_src = _val('DEFAULT_DIR_MOVE_SRC', default_dir)
        move_dst = _val('DEFAULT_DIR_MOVE_DST', default_dir)
        delete_dir = _val('DEFAULT_DIR_DELETE', default_dir)
        return {
            "status": "success",
            "defaults": {
                "files_dir": _val('DEFAULT_DIR_FILES', default_dir),
                "search_dir": _val('DEFAULT_DIR_SEARCH', default_dir),
                "media_dir": _val('DEFAULT_DIR_MEDIA', default_dir),
                "upload_dir": default_upload,
                "ondup": {
                    "global": ondup_global or None,
                    "copy": ondup_copy,
                    "move": ondup_move,
                    "rename": ondup_rename,
                    "upload": ondup_upload
                },
                "c2c_dirs": {
                    "copy": {"src": copy_src, "dst": copy_dst},
                    "move": {"src": move_src, "dst": move_dst},
                    "delete": {"src": delete_dir}
                }
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

"""显式旧接口兼容路由：直接调用 legacy_netdisk，保证不 404。"""
compat_router = APIRouter(prefix="/api", tags=["compatibility"], include_in_schema=False)

@compat_router.get("/files")
async def compat_files(path: str = "/", start: int = 0, limit: int = 100, client_id: str = None):
    try:
        return await legacy_netdisk.list_files(path=path, start=start, limit=limit)
    except Exception as e:
        # 统一错误结构并透传状态码
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.get("/dirs")
async def compat_dirs(path: str = "/", start: int = 0, limit: int = 100):
    try:
        return await legacy_netdisk.list_directories(path=path, start=start, limit=limit)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.get("/search")
async def compat_search(keyword: str, path: str = "/", start: int = 0, limit: int = 100, client_id: str = None):
    try:
        return await legacy_netdisk.search_files(keyword=keyword, path=path, start=start, limit=limit)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.get("/multimedia/list")
async def compat_multimedia_list(path: str = "/", recursion: int = 1, start: int = 0, limit: int = 100, order: str = "time", desc: int = 1, category: Optional[int] = None):
    # 旧实现统一走 list_multimedia_files（legacy_netdisk 与 legacy_netdisk_full 都使用该名）
    try:
        if hasattr(legacy_netdisk, "list_multimedia_files"):
            return await legacy_netdisk.list_multimedia_files(path=path, recursion=recursion, start=start, limit=limit, order=order, desc=desc, category=category)
        if legacy_netdisk_full and hasattr(legacy_netdisk_full, "list_multimedia_files"):
            return await legacy_netdisk_full.list_multimedia_files(path=path, recursion=recursion, start=start, limit=limit, order=order, desc=desc, category=category)
        return JSONResponse({"status": "error", "message": "multimedia list not supported"}, status_code=501)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.post("/multimedia/metas")
async def compat_multimedia_metas(payload: dict = Body(default=None)):
    try:
        fs_ids = []
        dlink = int(payload.get('dlink', 0)) if isinstance(payload, dict) else 0
        thumbs = int(payload.get('thumb', 0)) if isinstance(payload, dict) else 0
        if isinstance(payload, dict):
            fs_ids = payload.get("fs_ids") or payload.get("ids") or []
        if not fs_ids:
            return JSONResponse({"status": "error", "message": "缺少 fs_ids"}, status_code=400)
        if hasattr(legacy_netdisk, "get_multimedia_metas"):
            return await legacy_netdisk.get_multimedia_metas(fs_ids, dlink, thumbs)
        if legacy_netdisk_full and hasattr(legacy_netdisk_full, "get_multimedia_metas"):
            return await legacy_netdisk_full.get_multimedia_metas(fs_ids, dlink, thumbs)
        return JSONResponse({"status": "error", "message": "get_multimedia_metas 未实现"}, status_code=501)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.post("/copy")
async def compat_copy(body: dict = Body(...)):
    try:
        ops = body.get('operations') or body.get('filelist') or []
        ondup = body.get('ondup', 'newcopy')
        return await legacy_netdisk.copy_files(ops, ondup)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.post("/move")
async def compat_move(body: dict = Body(...)):
    try:
        ops = body.get('operations') or body.get('filelist') or []
        ondup = body.get('ondup', 'fail')
        return await legacy_netdisk.move_files(ops, ondup)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.post("/delete")
async def compat_delete(body: dict = Body(...)):
    try:
        paths = body.get('paths') or body.get('filelist') or []
        if isinstance(paths, list) and paths and isinstance(paths[0], dict):
            paths = [p.get('path') for p in paths if isinstance(p, dict)]
        return await legacy_netdisk.delete_files(paths or [])
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.post("/rename")
async def compat_rename(body: dict = Body(...)):
    try:
        path = body.get('path')
        newname = body.get('newname') or body.get('new_name')
        return await legacy_netdisk.rename_file(path, newname)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.get("/download_url")
async def compat_download_url(fs_id: int):
    try:
        return await legacy_netdisk.get_download_url(fs_id)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.get("/download")
async def compat_download(fs_id: Optional[int] = None, path: Optional[str] = None, redirect: int = 0):
    """返回下载直链，或在 redirect=1 时 302 重定向。支持 fs_id 或 path。"""
    try:
        # 优先使用 fs_id 获取 dlink
        if fs_id is not None:
            result = await legacy_netdisk.get_download_url(fs_id)
            dlink = (result or {}).get('dlink')
            if not dlink:
                return JSONResponse({"status": "error", "message": "未获取到下载链接"}, status_code=404)
            if redirect == 1:
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=dlink, status_code=302)
            return JSONResponse({"status": "success", "fs_id": fs_id, "dlink": dlink})

        # 其次使用 path 构造官方下载URL（无需列目录/搜索）
        if path:
            from urllib.parse import quote
            import os as _os
            access_token = _os.getenv('BAIDU_NETDISK_ACCESS_TOKEN')
            if not access_token:
                return JSONResponse({"status": "error", "message": "未配置 access_token"}, status_code=400)
            p = path if path.startswith('/') else f"/{path}"
            url = f"https://pan.baidu.com/rest/2.0/xpan/file?method=download&access_token={quote(access_token)}&path={quote(p)}"
            if redirect == 1:
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=url, status_code=302)
            return JSONResponse({"status": "success", "path": p, "dlink": url})

        return JSONResponse({"status": "error", "message": "缺少 fs_id 或 path"}, status_code=400)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.post("/downloads")
async def compat_downloads(body: dict = Body(...)):
    try:
        fs_ids = body.get('fs_ids') or body.get('ids') or []
        return await legacy_netdisk.get_downloads(fs_ids)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.get("/download_probe")
async def compat_download_probe(url: Optional[str] = None, path: Optional[str] = None):
    try:
        # 1) 若传入完整 URL，直接探测
        if url:
            return await legacy_netdisk.probe_download(url)
        # 2) 若传入网盘路径，解析并换取 dlink 后探测
        if path:
            # 规范化路径
            from urllib.parse import unquote
            def _norm(s: str) -> str:
                try:
                    return unquote(s or '')
                except Exception:
                    return s or ''
            p = path if path.startswith('/') else f"/{path}"
            p = _norm(p)
            # 拆分父目录与文件名
            if p == '/':
                return JSONResponse({"status": "error", "message": "根路径不可探测"}, status_code=400)
            parent = p.rsplit('/', 1)[0] or '/'
            filename = p.rsplit('/', 1)[1]
            # 列出父目录查找目标文件
            try:
                start_idx = 0
                target = None
                while True:
                    listing = await legacy_netdisk.list_files(path=parent, start=start_idx, limit=1000)
                    files = (listing or {}).get('files') or []
                    for it in files:
                        name = _norm(it.get('name') or it.get('server_filename') or '')
                        ipath = _norm(it.get('path') or '')
                        if ipath == p or name == filename:
                            target = it; break
                    if target:
                        break
                    if not listing.get('has_more') or not files:
                        break
                    start_idx += 1000
            except Exception as _e:
                # 目录列举失败，尝试精确搜索
                try:
                    search_res = await legacy_netdisk.search_files(keyword=filename, path=parent, start=0, limit=100)
                    files = (search_res or {}).get('files') or []
                    target = None
                    for it in files:
                        if it.get('path') == p or it.get('name') == filename:
                            target = it; break
                    if not target:
                        return JSONResponse({"status": "error", "message": f"列目录失败且未搜到目标: {str(_e)}"}, status_code=502)
                    fs_id = target.get('fs_id') or target.get('fsid')
                    if not fs_id:
                        return JSONResponse({"status": "error", "message": "缺少 fs_id"}, status_code=400)
                    d = await legacy_netdisk.get_download_url(int(fs_id))
                    dlink = (d or {}).get('dlink')
                    if not dlink:
                        return JSONResponse({"status": "error", "message": "未获取到下载链接"}, status_code=404)
                    return await legacy_netdisk.probe_download(dlink)
                except Exception as _e2:
                    return JSONResponse({"status": "error", "message": f"列目录失败: {str(_e)}; 搜索失败: {str(_e2)}"}, status_code=502)
            if not target:
                # 若分页扫描未命中，进一步使用搜索作为补充
                try:
                    search_res = await legacy_netdisk.search_files(keyword=filename, path=parent, start=0, limit=200)
                    sfiles = (search_res or {}).get('files') or []
                    for it in sfiles:
                        name = _norm(it.get('name') or '')
                        ipath = _norm(it.get('path') or '')
                        if ipath == p or name == filename:
                            target = it; break
                except Exception:
                    pass
            if not target:
                return JSONResponse({"status": "error", "message": "未在父目录找到目标文件"}, status_code=404)
            fs_id = target.get('fs_id') or target.get('fsid')
            if not fs_id:
                return JSONResponse({"status": "error", "message": "缺少 fs_id"}, status_code=400)
            # 获取直链并探测
            try:
                d = await legacy_netdisk.get_download_url(int(fs_id))
                dlink = (d or {}).get('dlink')
                if not dlink:
                    return JSONResponse({"status": "error", "message": "未获取到下载链接"}, status_code=404)
                return await legacy_netdisk.probe_download(dlink)
            except Exception as _e:
                from fastapi import HTTPException as _HTTPException
                if isinstance(_e, _HTTPException):
                    return JSONResponse({"status": "error", "message": getattr(_e, 'detail', str(_e))}, status_code=_e.status_code or 502)
                return JSONResponse({"status": "error", "message": str(_e)}, status_code=502)
        # 两者都未提供
        return JSONResponse({"status": "error", "message": "缺少 url 或 path"}, status_code=400)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

@compat_router.get("/categoryinfo")
async def compat_categoryinfo(category: int, start: int = 0, limit: int = 100, order: str = 'time', desc: int = 1):
    try:
        return await legacy_netdisk.get_categoryinfo(category, start, limit, order, desc)
    except Exception as e:
        from fastapi import HTTPException as _HTTPException
        if isinstance(e, _HTTPException):
            return JSONResponse({"status": "error", "message": getattr(e, 'detail', str(e))}, status_code=e.status_code or 502)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=502)

# 占位：分享相关老接口，暂未实现时返回明确错误
@compat_router.post("/share/create")
async def compat_share_create():
    return JSONResponse({"status": "error", "message": "share create 未实现"}, status_code=501)

@compat_router.get("/share/info")
async def compat_share_info():
    return JSONResponse({"status": "error", "message": "share info 未实现"}, status_code=501)

@compat_router.post("/share/transfer")
async def compat_share_transfer():
    return JSONResponse({"status": "error", "message": "share transfer 未实现"}, status_code=501)

@compat_router.get("/share/dlink")
async def compat_share_dlink():
    return JSONResponse({"status": "error", "message": "share dlink 未实现"}, status_code=501)

# 注册路由
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(payments_router)
app.include_router(listings_router)
app.include_router(orders_router)
app.include_router(wallet_router)
app.include_router(notify_router)
app.include_router(notifications_router)
app.include_router(netdisk_router)
app.include_router(reports_router)
app.include_router(sync_router)
app.include_router(purchases_alias_router)
app.include_router(refunds_router)

# 注册兼容性路由器（放在最后，确保优先级）
if compat_router:
    app.include_router(compat_router)

# 根路由
@app.get("/")
async def root():
    return {"message": "MCP Server is running", "version": "2.0.0"}

# 健康检查路由
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mcp-server"}

# HTML页面路由
@app.get("/admin")
async def admin_page():
    """管理后台页面"""
    admin_file = os.path.join(src_dir, "admin.html")
    if os.path.exists(admin_file):
        return FileResponse(admin_file)
    return {"error": "Admin page not found"}

@app.get("/login")
async def login_page():
    """登录页面"""
    login_file = os.path.join(src_dir, "login.html")
    if os.path.exists(login_file):
        return FileResponse(login_file)
    return {"error": "Login page not found"}

@app.get("/market.html")
async def market_page():
    """商品市场页面"""
    market_file = os.path.join(src_dir, "market.html")
    if os.path.exists(market_file):
        return FileResponse(market_file)
    return {"error": "Market page not found"}

@app.get("/market")
async def market_page_short():
    """商品市场页面（短路径）"""
    market_file = os.path.join(src_dir, "market.html")
    if os.path.exists(market_file):
        return FileResponse(market_file)
    return {"error": "Market page not found"}

@app.get("/user.html")
async def user_page():
    """用户页面"""
    user_file = os.path.join(src_dir, "user.html")
    if os.path.exists(user_file):
        return FileResponse(user_file)
    return {"error": "User page not found"}

@app.get("/seller.html")
async def seller_page():
    """卖家中心页面"""
    seller_file = os.path.join(src_dir, "seller.html")
    if os.path.exists(seller_file):
        return FileResponse(seller_file)
    return {"error": "Seller page not found"}

@app.get("/seller")
async def seller_page_short():
    """卖家中心页面（短路径）"""
    seller_file = os.path.join(src_dir, "seller.html")
    if os.path.exists(seller_file):
        return FileResponse(seller_file)
    return {"error": "Seller page not found"}

@app.get("/status.html")
async def status_page():
    """系统状态页面"""
    status_file = os.path.join(src_dir, "status.html")
    if os.path.exists(status_file):
        return FileResponse(status_file)
    return {"error": "Status page not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1
    )