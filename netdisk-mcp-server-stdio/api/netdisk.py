#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网盘API路由
提供百度网盘文件管理功能的RESTful接口
"""

from fastapi import APIRouter, HTTPException, Query, Path, UploadFile, File
from typing import List, Optional, Dict, Any
import os
import sys
import hashlib
import json
import time
import random
import threading
from collections import defaultdict, deque
import datetime

# 添加当前目录到系统路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

router = APIRouter(prefix="/api/netdisk", tags=["netdisk"])

# 延迟导入，避免模块加载时的阻塞
def get_netdisk_config():
    """获取网盘配置"""
    return {
        'access_token': os.getenv('BAIDU_NETDISK_ACCESS_TOKEN'),
        'app_key': os.getenv('BAIDU_NETDISK_APP_KEY'),
        'refresh_token': os.getenv('BAIDU_NETDISK_REFRESH_TOKEN'),
        'secret_key': os.getenv('BAIDU_NETDISK_SECRET_KEY')
    }

# SDK 优先，HTTP 作为后备：尽量使用 openapi_client 提供的 SDK；当 SDK 缺失或调用异常时，回退到 HTTP

def _get_sdk_clients():
    """尝试创建 SDK 客户端集合，失败则抛 ImportError。"""
    from openapi_client import ApiClient, Configuration
    from openapi_client.api.userinfo_api import UserinfoApi
    from openapi_client.api.fileinfo_api import FileinfoApi
    from openapi_client.api.filemanager_api import FilemanagerApi
    from openapi_client.api.multimediafile_api import MultimediafileApi
    from openapi_client.api.fileupload_api import FileuploadApi
    cfg = Configuration()
    cfg.connection_pool_maxsize = 10
    cfg.retries = 3
    api_client = ApiClient(cfg)
    return {
        'client': api_client,
        'userinfo': UserinfoApi(api_client),
        'fileinfo': FileinfoApi(api_client),
        'filemanager': FilemanagerApi(api_client),
        'multimedia': MultimediafileApi(api_client),
        'upload': FileuploadApi(api_client),
    }

def get_requests_session():
    """延迟导入requests相关模块"""
    try:
        from urllib3.util.retry import Retry
        from requests.adapters import HTTPAdapter
        import requests
        return requests, Retry, HTTPAdapter
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"网络库导入失败: {str(e)}")

# 定义分片大小为4MB
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
# 定义重试次数和超时时间
MAX_RETRIES = 3
RETRY_BACKOFF = 2
TIMEOUT = 30

# 频率控制配置
RATE_LIMITS = {
    'search': {'daily': 2000, 'per_minute': 20},  # 搜索接口：每日2000次，每分钟20次
    'listall': {'per_minute': 8},  # listall接口：每分钟8次
    'fileinfo': {'per_minute': 30},  # 文件信息接口：每分钟30次
    'filemanager': {'per_minute': 20},  # 文件管理接口：每分钟20次
    'userinfo': {'per_minute': 10},  # 用户信息接口：每分钟10次
    'multimedia': {'per_minute': 15},  # 多媒体接口：每分钟15次
    'share': {'per_minute': 10},  # 分享接口：每分钟10次
    'upload': {'per_minute': 5},  # 上传接口：每分钟5次
    'download': {'per_minute': 10},  # 下载接口：每分钟10次
    'default': {'per_minute': 20}  # 默认限制：每分钟20次
}

class RateLimiter:
    """API调用频率限制器"""
    
    def __init__(self):
        self.locks = defaultdict(threading.Lock)
        self.call_times = defaultdict(lambda: defaultdict(deque))
        self.daily_counts = defaultdict(int)
        self.last_reset_date = datetime.date.today()
    
    def _reset_daily_counts(self):
        """重置每日计数"""
        today = datetime.date.today()
        if today != self.last_reset_date:
            self.daily_counts.clear()
            self.last_reset_date = today
    
    def _clean_old_calls(self, api_type: str, window: str):
        """清理过期的调用记录"""
        current_time = time.time()
        window_seconds = 60 if window == 'per_minute' else 86400  # 1分钟或1天
        
        while (self.call_times[api_type][window] and 
               current_time - self.call_times[api_type][window][0] > window_seconds):
            self.call_times[api_type][window].popleft()
    
    def can_make_call(self, api_type: str):
        """
        检查是否可以发起API调用
        
        返回:
        - (是否可以调用, 错误信息)
        """
        self._reset_daily_counts()
        
        # 获取该API类型的限制配置
        limits = RATE_LIMITS.get(api_type, RATE_LIMITS['default'])
        
        with self.locks[api_type]:
            # 检查每分钟限制
            if 'per_minute' in limits:
                self._clean_old_calls(api_type, 'per_minute')
                per_minute_limit = limits['per_minute']
                current_calls = len(self.call_times[api_type]['per_minute'])
                
                if current_calls >= per_minute_limit:
                    wait_time = 60 - (time.time() - self.call_times[api_type]['per_minute'][0])
                    return False, f"API调用频率超限，每分钟最多{per_minute_limit}次，请等待{wait_time:.1f}秒"
            
            # 检查每日限制
            if 'daily' in limits:
                daily_limit = limits['daily']
                if self.daily_counts[api_type] >= daily_limit:
                    return False, f"API调用频率超限，每日最多{daily_limit}次，请明天再试"
            
            return True, ""
    
    def record_call(self, api_type: str):
        """记录API调用"""
        current_time = time.time()
        
        with self.locks[api_type]:
            # 记录每分钟调用
            if 'per_minute' in RATE_LIMITS.get(api_type, RATE_LIMITS['default']):
                self.call_times[api_type]['per_minute'].append(current_time)
            
            # 记录每日调用
            if 'daily' in RATE_LIMITS.get(api_type, RATE_LIMITS['default']):
                self.daily_counts[api_type] += 1

# 创建全局频率限制器
rate_limiter = RateLimiter()

def check_rate_limit(api_type: str):
    """检查API调用频率限制"""
    return rate_limiter.can_make_call(api_type)

def record_api_call(api_type: str):
    """记录API调用"""
    rate_limiter.record_call(api_type)

def _ensure_access_token() -> str:
    """优先从环境变量读取，其次从 auth_result.json 读取 access_token。"""
    token = os.getenv('BAIDU_NETDISK_ACCESS_TOKEN')
    if token:
        return token
    try:
        auth_file = os.path.join(BASE_DIR, 'auth_result.json')
        if os.path.exists(auth_file):
            with open(auth_file, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
            t = (data.get('token') or {}).get('access_token')
            if t:
                return t
    except Exception:
        pass
    return ""

def _refresh_access_token_if_possible() -> Optional[str]:
    """使用刷新令牌尝试刷新 access_token（如 .env 提供 client_id/secret/refresh_token）。"""
    refresh_token = os.getenv('BAIDU_NETDISK_REFRESH_TOKEN')
    client_id = os.getenv('BAIDU_NETDISK_APP_KEY') or os.getenv('BAIDU_NETDISK_CLIENT_ID')
    client_secret = os.getenv('BAIDU_NETDISK_SECRET_KEY') or os.getenv('BAIDU_NETDISK_CLIENT_SECRET')
    if not refresh_token or not client_id or not client_secret:
        return None
    try:
        requests, _, _ = get_requests_session()
        resp = requests.get(
            'https://openapi.baidu.com/oauth/2.0/token',
            params={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': client_id,
                'client_secret': client_secret,
            },
            timeout=10
        )
        if not resp.ok:
            return None
        data = resp.json()
        new_token = data.get('access_token')
        if new_token:
            os.environ['BAIDU_NETDISK_ACCESS_TOKEN'] = new_token
            # 尝试写回 auth_result.json 以便下次启动使用
            try:
                auth_file = os.path.join(BASE_DIR, 'auth_result.json')
                old = {}
                if os.path.exists(auth_file):
                    with open(auth_file, 'r', encoding='utf-8') as f:
                        old = json.load(f) or {}
                old.setdefault('token', {})['access_token'] = new_token
                with open(auth_file, 'w', encoding='utf-8') as f:
                    json.dump(old, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return new_token
    except Exception:
        return None
    return None

def _request_pan_api(base: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """通用HTTP请求封装，自动附带 access_token、web=1，统一错误与刷新逻辑。"""
    requests, _, _ = get_requests_session()
    token = _ensure_access_token()
    if not token:
        return {"status": "error", "errno": -1, "error_code": "missing_access_token", "message": "missing access_token"}
    q = dict(params)
    q.setdefault('web', 1)
    q['access_token'] = token
    try:
        r = requests.get(base, params=q, timeout=TIMEOUT, headers={'User-Agent': 'pan.baidu.com'})
        if r.status_code in (401, 403):
            # 尝试刷新 token 一次
            nt = _refresh_access_token_if_possible()
            if nt:
                q['access_token'] = nt
                r = requests.get(base, params=q, timeout=TIMEOUT, headers={'User-Agent': 'pan.baidu.com'})
        if not r.ok:
            # 尝试解析错误体
            try:
                err_json = r.json()
                return {
                    "status": "error",
                    "errno": err_json.get('errno') or -2,
                    "error_code": err_json.get('error_code') or f"http_{r.status_code}",
                    "message": err_json.get('error_msg') or err_json.get('errmsg') or r.text,
                    "raw": err_json
                }
            except Exception:
                return {"status": "error", "errno": -2, "error_code": f"http_{r.status_code}", "message": r.text}
        data = r.json()
        # errno 非 0 也返回完整体，调用方据此决定
        if isinstance(data, dict) and data.get('errno', 0) != 0:
            return {"status": "error", "errno": data.get('errno'), "error_code": data.get('error_code'), "message": data.get('error_msg') or data.get('errmsg') or data.get('msg') or "pan api error", "raw": data}
        return data
    except Exception as e:
        return {"status": "error", "errno": -3, "error_code": "exception", "message": str(e)}

def configure_session():
    """配置带有重试机制的会话"""
    requests, Retry, HTTPAdapter = get_requests_session()
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

@router.get("/files")
async def list_files(
    path: str = Query("/", description="网盘路径，默认为根目录"),
    start: int = Query(0, ge=0, description="起始位置"),
    limit: int = Query(100, ge=1, le=200, description="返回数量限制")
):
    """
    列出指定路径下的文件和文件夹
    
    调用百度网盘开放平台 xpanfilelist 接口
    """
    try:
        # 检查频率限制
        can_call, error_msg = check_rate_limit('fileinfo')
        if not can_call:
            raise HTTPException(status_code=429, detail=error_msg)
        
        access_token = _ensure_access_token()
        safe_limit = min(limit, 200)
        # 1) SDK 优先
        try:
            sdks = _get_sdk_clients()
            resp = sdks['fileinfo'].xpanfilelist(
                access_token=access_token,
                dir=path,
                start=str(start),
                limit=safe_limit,
                order='name',
                desc=0,
                web='1'
            )
            response = resp
        except Exception:
            # 2) HTTP 回退
            response = _request_pan_api(
                'https://pan.baidu.com/rest/2.0/xpan/file',
                {
                    'method': 'list',
                    'dir': path,
                    'start': start,
                    'limit': safe_limit,
                    'order': 'name',
                    'desc': 0,
                }
            )
            if response.get('status') == 'error':
                raise HTTPException(status_code=400, detail=response.get('message', 'pan api error'))
        # 记录API调用
        record_api_call('fileinfo')
        if 'errno' in response and response['errno'] != 0:
            raise HTTPException(status_code=400, detail=f"获取文件列表失败: {response['errno']}")
        # 处理文件列表
        files = []
        if 'list' in response:
            for item in response['list']:
                    # 修复编码问题：UTF-8被GBK解码导致的乱码
                    def fix_encoding(text):
                        if not text or not isinstance(text, str):
                            return text
                        try:
                            # 尝试将乱码的UTF-8字符串重新编码为正确的UTF-8
                            return text.encode('latin-1').decode('utf-8')
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            # 如果修复失败，返回原字符串
                            return text
                    file_info = {
                        "name": fix_encoding(item.get('server_filename', '')),
                        "path": fix_encoding(item.get('path', '')),
                        "size": item.get('size', 0),
                        "isdir": item.get('isdir', 0),
                        "fs_id": item.get('fs_id', ''),
                        "create_time": item.get('server_ctime', 0),
                        "modify_time": item.get('server_mtime', 0),
                        "md5": item.get('md5', ''),
                        "category": item.get('category', '')
                    }
                    files.append(file_info)
        return {
            "status": "success",
            "message": "获取文件列表成功",
            "path": path,
            "total": len(files),
            "files": files,
            "has_more": response.get('has_more', False),
            "page_info": {
                "start": start,
                "limit": safe_limit,
                "page_full": len(files) >= safe_limit
            }
        }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表时发生错误: {str(e)}")

@router.get("/directories")
async def list_directories(
    path: str = Query("/", description="网盘路径，默认为根目录"),
    start: int = Query(0, ge=0, description="起始位置"),
    limit: int = Query(100, ge=1, le=200, description="返回数量限制")
):
    """
    获取指定路径下的子目录列表
    
    仅返回目录，不包含文件
    """
    try:
        result = await list_files(path=path, start=start, limit=limit)
        if result.get('status') != 'success':
            return result
        
        dirs = [f for f in result.get('files', []) if f.get('isdir') == 1]
        return {
            "status": "success",
            "message": "获取目录列表成功",
            "path": path,
            "total": len(dirs),
            "directories": dirs,
            "has_more": result.get('has_more', False)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取目录列表时发生错误: {str(e)}")

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    remote_path: Optional[str] = Query(None, description="网盘存储路径，如不指定将使用默认路径"),
    ondup: str = Query("ask", description="重名处理：ask|overwrite|rename|skip")
):
    """
    上传文件到网盘（支持多分片）：precreate -> superfile2 (N 分片) -> create
    分片大小：4MB，与 CHUNK_SIZE 保持一致
    """
    try:
        # 规范远程路径
        if not remote_path or remote_path.strip() == "":
            remote_path = f"/来自：mcp_server/{file.filename}"
        else:
            if remote_path.endswith('/'):
                remote_path = f"{remote_path}{file.filename}"
            elif not remote_path.startswith('/'):
                remote_path = f"/{remote_path}"
        # 检查频率限制
        can_call, error_msg = check_rate_limit('upload')
        if not can_call:
            raise HTTPException(status_code=429, detail=error_msg)

        # 在上传前检查目标目录是否已存在同名文件
        try:
            parent_dir = remote_path.rsplit('/', 1)[0] or '/'
            base_name = remote_path.rsplit('/', 1)[1]
        except Exception:
            parent_dir = '/'
            base_name = file.filename

        # 列出父目录，查找同名项
        conflict_item: Optional[Dict[str, Any]] = None
        try:
            # 优先 SDK，其次 HTTP
            try:
                sdks = _get_sdk_clients()
                access_token = _ensure_access_token()
                resp = sdks['fileinfo'].xpanfilelist(
                    access_token=access_token,
                    dir=parent_dir,
                    start='0',
                    limit=1000,
                    order='name',
                    desc=0,
                    web='1'
                )
                items = resp.get('list', []) if isinstance(resp, dict) else []
            except Exception:
                resp = _request_pan_api(
                    'https://pan.baidu.com/rest/2.0/xpan/file',
                    {
                        'method': 'list',
                        'dir': parent_dir,
                        'start': 0,
                        'limit': 1000,
                        'order': 'name',
                        'desc': 0,
                    }
                )
                items = resp.get('list', []) if isinstance(resp, dict) else []
            for it in items:
                name = it.get('server_filename') or it.get('name') or ''
                if name == base_name and it.get('isdir', 0) == 0:
                    conflict_item = it
                    break
        except Exception:
            conflict_item = None

        if conflict_item is not None:
            # 根据 ondup 策略处理
            if ondup == 'skip':
                raise HTTPException(status_code=409, detail={
                    'status': 'conflict',
                    'action': 'skip',
                    'message': '检测到同名文件，已按 skip 策略跳过',
                    'existing': {
                        'name': base_name,
                        'size': conflict_item.get('size'),
                        'md5': conflict_item.get('md5'),
                        'path': conflict_item.get('path')
                    }
                })
            if ondup == 'ask':
                # 返回 409，请前端提示用户选择 overwrite/rename/skip
                raise HTTPException(status_code=409, detail={
                    'status': 'conflict',
                    'action': 'ask',
                    'message': '目标目录存在同名文件',
                    'choices': ['overwrite', 'rename', 'skip'],
                    'existing': {
                        'name': base_name,
                        'size': conflict_item.get('size'),
                        'md5': conflict_item.get('md5'),
                        'path': conflict_item.get('path')
                    }
                })
            if ondup == 'rename':
                # 在文件名后追加时间后缀
                import datetime as _dt
                ts = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
                if '.' in base_name:
                    stem = base_name.rsplit('.', 1)[0]
                    ext = base_name.rsplit('.', 1)[1]
                    base_name = f"{stem} ({ts}).{ext}"
                else:
                    base_name = f"{base_name} ({ts})"
                remote_path = f"{parent_dir.rstrip('/')}/{base_name}"
            # ondup == 'overwrite' 则继续后续流程（create 时 rtype=3 覆盖/新副本）

        # 读取文件内容（一次内存读取，适合中等大小文件）；如需超大文件可改为流式双遍历
        content = await file.read()
        file_size = len(content)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="空文件不可上传")

        # 切分分片并计算每片 MD5
        chunks: list[bytes] = []
        md5_list: list[str] = []
        for start in range(0, file_size, CHUNK_SIZE):
            part = content[start:start + CHUNK_SIZE]
            chunks.append(part)
            md5_list.append(hashlib.md5(part).hexdigest())
        block_list_str = json.dumps(md5_list)

        # 1) precreate（SDK 优先）
        uploadid = None
        try:
            sdks = _get_sdk_clients()
            token = _ensure_access_token()
            pre = sdks['upload'].xpanfileprecreate(
                access_token=token,
                path=remote_path,
                isdir=0,
                size=file_size,
                autoinit=1,
                block_list=block_list_str,
                rtype=3
            )
            uploadid = pre.get('uploadid') if isinstance(pre, dict) else (getattr(pre, 'uploadid', None))
        except Exception:
            pre = _request_pan_api(
                'https://pan.baidu.com/rest/2.0/xpan/file',
                {
                    'method': 'precreate',
                    'path': remote_path,
                    'size': file_size,
                    'isdir': 0,
                    'autoinit': 1,
                    'rtype': 3,
                    'block_list': block_list_str,
                }
            )
            if pre.get('status') == 'error' or pre.get('errno', 0) != 0:
                raise HTTPException(status_code=400, detail=f"预创建失败: {pre.get('message') or pre.get('errno')}")
            uploadid = pre.get('uploadid')
        if not uploadid:
            raise HTTPException(status_code=400, detail="预创建失败：缺少 uploadid")

        # 2) superfile2 按分片上传
        requests, _, _ = get_requests_session()
        token = _ensure_access_token()
        if not token:
            raise HTTPException(status_code=400, detail="missing access_token")
        try:
            sdks = _get_sdk_clients()
            for idx, part in enumerate(chunks):
                sdks['upload'].pcssuperfile2(
                    access_token=token,
                    partseq=str(idx),
                    path=remote_path,
                    uploadid=uploadid,
                    type='tmpfile',
                    file=part
                )
        except Exception:
            up_url = 'https://d.pcs.baidu.com/rest/2.0/pcs/superfile2'
            for idx, part in enumerate(chunks):
                up_params = {
                    'method': 'upload',
                    'access_token': token,
                    'type': 'tmpfile',
                    'path': remote_path,
                    'uploadid': uploadid,
                    'partseq': idx,
                }
                files_map = {'file': (file.filename, part)}
                up_resp = requests.post(up_url, params=up_params, files=files_map, timeout=TIMEOUT)
                if not up_resp.ok:
                    raise HTTPException(status_code=400, detail=f"上传分片 {idx} 失败: {up_resp.text}")
                # 有些返回含 md5 字段，但无需强校验（不同接口字段差异）

        # 3) create 完成
        try:
            sdks = _get_sdk_clients()
            created = sdks['upload'].xpanfilecreate(
                access_token=token,
                path=remote_path,
                isdir=0,
                size=file_size,
                uploadid=uploadid,
                block_list=block_list_str,
                rtype=3  # 3 表示覆盖/重命名策略（与 openapi 行为一致）
            )
            if isinstance(created, dict) and created.get('errno', 0) != 0:
                raise HTTPException(status_code=400, detail=f"创建文件失败: {created.get('errno')}")
        except Exception:
            created = _request_pan_api(
                'https://pan.baidu.com/rest/2.0/xpan/file',
                {
                    'method': 'create',
                    'path': remote_path,
                    'size': file_size,
                    'isdir': 0,
                    'rtype': 3,
                    'uploadid': uploadid,
                    'block_list': block_list_str,
                }
            )
            if created.get('status') == 'error' or created.get('errno', 0) != 0:
                raise HTTPException(status_code=400, detail=f"创建文件失败: {created.get('message') or created.get('errno')}")

        record_api_call('upload')
        return {
            "status": "success",
            "message": "文件上传成功",
            "filename": file.filename,
            "size": file_size,
            "remote_path": remote_path,
            "blocks": len(md5_list),
            "result": created
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传文件时发生错误: {str(e)}")

@router.get("/search")
async def search_files(
    keyword: str = Query(..., description="搜索关键词"),
    path: str = Query("/", description="搜索路径，默认为根目录"),
    start: int = Query(0, ge=0, description="起始位置"),
    limit: int = Query(100, ge=1, le=200, description="返回数量限制")
):
    """
    搜索网盘文件
    
    支持按关键词搜索文件
    """
    try:
        # 检查频率限制
        can_call, error_msg = check_rate_limit('search')
        if not can_call:
            raise HTTPException(status_code=429, detail=error_msg)
        
        access_token = _ensure_access_token()
        try:
            sdks = _get_sdk_clients()
            # SDK 的 search 接口使用分页页码(page)与每页条数(num)，page 从 1 起
            page_num = int(start // max(1, limit)) + 1
            resp = sdks['fileinfo'].xpanfilesearch(
                access_token=access_token,
                key=keyword,
                dir=path,
                recursion='1',
                page=str(page_num),
                num=str(limit),
                web='1'
            )
            response = resp
        except Exception:
            # HTTP 回退
            response = _request_pan_api(
                'https://pan.baidu.com/rest/2.0/xpan/file',
                {
                    'method': 'search',
                    'key': keyword,
                    'dir': path,
                    'recursion': 1,
                    'start': start,
                    'limit': limit,
                }
            )
            if response.get('status') == 'error':
                raise HTTPException(status_code=400, detail=response.get('message', 'pan api error'))
        # 记录API调用
        record_api_call('search')
        if 'errno' in response and response['errno'] != 0:
            msg = response.get('error_msg') or response.get('errmsg') or str(response['errno'])
            raise HTTPException(status_code=400, detail=f"搜索文件失败: {msg}")
        # 处理搜索结果
        files = []
        if 'list' in response:
            for item in response['list']:
                    file_info = {
                        "name": item.get('server_filename', ''),
                        "path": item.get('path', ''),
                        "size": item.get('size', 0),
                        "isdir": item.get('isdir', 0),
                        "fs_id": item.get('fs_id', ''),
                        "create_time": item.get('server_ctime', 0),
                        "modify_time": item.get('server_mtime', 0),
                        "md5": item.get('md5', ''),
                        "category": item.get('category', '')
                    }
                    files.append(file_info)
        return {
            "status": "success",
            "message": "文件搜索成功",
            "keyword": keyword,
            "search_path": path,
            "total": len(files),
            "files": files,
            "has_more": response.get('has_more', False)
        }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索文件时发生错误: {str(e)}")

@router.get("/user/info")
async def get_user_info():
    """
    获取用户信息
    
    返回用户基本信息（用户名、头像、VIP等级等）
    """
    try:
        access_token = _ensure_access_token()
        try:
            sdks = _get_sdk_clients()
            response = sdks['userinfo'].xpannasuinfo(access_token=access_token)
        except Exception:
            response = _request_pan_api(
                'https://pan.baidu.com/rest/2.0/xpan/nas',
                { 'method': 'uinfo' }
            )
            if response.get('status') == 'error':
                raise HTTPException(status_code=400, detail=response.get('message', 'pan api error'))
        if 'errno' in response and response['errno'] != 0:
            raise HTTPException(status_code=400, detail=f"获取用户信息失败: {response['errno']}")
        return {
            "status": "success",
            "message": "获取用户信息成功",
            "user_info": {
                "baidu_name": response.get('baidu_name', ''),
                "netdisk_name": response.get('netdisk_name', ''),
                "avatar_url": response.get('avatar_url', ''),
                "vip_type": response.get('vip_type', 0),
                "vip_level": response.get('vip_level', 0),
                "uk": response.get('uk', 0)
            }
        }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户信息时发生错误: {str(e)}")

@router.get("/user/quota")
async def get_quota_info():
    """
    获取用户配额信息（存储空间使用情况）
    
    返回存储空间使用情况（总容量、已用、剩余、使用率等）
    """
    try:
        access_token = _ensure_access_token()
        try:
            sdks = _get_sdk_clients()
            response = sdks['userinfo'].xpannasquota(access_token=access_token)
        except Exception:
            response = _request_pan_api(
                'https://pan.baidu.com/rest/2.0/xpan/nas',
                { 'method': 'quota' }
            )
            if response.get('status') == 'error':
                raise HTTPException(status_code=400, detail=response.get('message', 'pan api error'))
        if 'errno' in response and response['errno'] != 0:
            raise HTTPException(status_code=400, detail=f"获取配额信息失败: {response['errno']}")
        # 计算使用率
        total = response.get('total', 0)
        used = response.get('used', 0)
        usage_percent = (used / total * 100) if total > 0 else 0
        return {
            "status": "success",
            "message": "获取配额信息成功",
            "quota_info": {
                "total": total,
                "used": used,
                "free": total - used,
                "usage_percent": round(usage_percent, 2),
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round((total - used) / (1024**3), 2)
            }
        }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配额信息时发生错误: {str(e)}")

@router.get("/multimedia")
async def list_multimedia_files(
    path: str = Query("/", description="搜索路径，默认为根目录"),
    recursion: int = Query(1, description="是否递归搜索，1为是，0为否"),
    start: int = Query(0, ge=0, description="起始位置"),
    limit: int = Query(100, ge=1, le=200, description="返回数量限制"),
    order: str = Query("time", description="排序字段，可选值：time（时间）、name（名称）、size（大小）"),
    desc: int = Query(1, description="是否降序排列，1为是，0为否"),
    category: Optional[int] = Query(None, description="文件类型：1视频、2音频、3图片、4文档、5应用、6其他、7种子")
):
    """
    列出多媒体文件（图片、视频、音频等）
    
    支持按类型筛选和排序
    """
    try:
        # 检查频率限制
        can_call, error_msg = check_rate_limit('multimedia')
        if not can_call:
            raise HTTPException(status_code=429, detail=error_msg)
        
        session = configure_session()
        base_url = 'https://pan.baidu.com/rest/2.0/xpan/file'
        headers = {'User-Agent': 'pan.baidu.com'}

        # 根据类型选择专用接口
        use_method = None
        params: Dict[str, Any] = {
            'web': 1,
        }

        if category == 3:
            use_method = 'imagelist'
            params.update({
                'method': use_method,
                'parent_path': path,
                'recursion': recursion,
                'start': start,
                'limit': limit,
                'order': order,
                'desc': desc,
            })
        elif category == 1:
            use_method = 'videolist'
            params.update({
                'method': use_method,
                'parent_path': path,
                'recursion': recursion,
                'start': start,
                'limit': limit,
                'order': order,
                'desc': desc,
            })
        elif category == 4:
            use_method = 'doclist'
            params.update({
                'method': use_method,
                'parent_path': path,
                'recursion': recursion,
                'start': start,
                'limit': limit,
                'order': order,
                'desc': desc,
            })
        elif category == 2:
            use_method = 'audiolist'
            params.update({
                'method': use_method,
                'parent_path': path,
                'recursion': recursion,
                'start': start,
                'limit': limit,
                'order': order,
                'desc': desc,
            })
        elif category == 7:
            use_method = 'btlist'
            params.update({
                'method': use_method,
                'parent_path': path,
                'recursion': recursion,
                'start': start,
                'limit': limit,
                'order': order,
                'desc': desc,
            })
        else:
            use_method = 'listall'
            params.update({
                'method': use_method,
                'path': path,
                'recursion': recursion,
                'start': start,
                'limit': limit,
                'order': order,
                'desc': desc,
            })
            if category is not None:
                params['category'] = category

        access_token = _ensure_access_token()
        # 1) SDK 优先（仅当使用 listall/imagelist/videolist/doclist/audiolist/btlist 这些 SDK 暴露的方法时）
        try:
            sdks = _get_sdk_clients()
            if use_method == 'imagelist':
                page_num = int(start // max(1, limit)) + 1
                response = sdks['fileinfo'].xpanfileimagelist(access_token=access_token, parent_path=path, recursion=str(recursion), page=page_num, num=limit, order=order, desc=str(desc), web='1')
            elif use_method == 'videolist':
                # fileinfo_api 未必包含 videolist，若无则走 HTTP
                raise Exception('no sdk videolist')
            elif use_method == 'doclist':
                page_num = int(start // max(1, limit)) + 1
                response = sdks['fileinfo'].xpanfiledoclist(access_token=access_token, parent_path=path, recursion=str(recursion), page=page_num, num=limit, order=order, desc=str(desc), web='1')
            else:
                # listall 也常用 HTTP 参数
                raise Exception('prefer http for listall')
        except Exception:
            r = session.get(base_url, params=params, timeout=TIMEOUT, headers=headers)
            r.raise_for_status()
            response = r.json()
        
        if 'errno' in response and response['errno'] != 0:
            msg = response.get('error_msg') or response.get('errmsg') or str(response['errno'])
            raise HTTPException(status_code=400, detail=f"获取多媒体文件列表失败: {msg}")

        # 根据接口类型获取数据
        raw_items = response.get('info') if use_method in ('imagelist', 'videolist', 'doclist', 'audiolist', 'btlist') else response.get('list')
        files = []
        for item in raw_items or []:
            # 修复编码问题
            def fix_encoding(text):
                if not text or not isinstance(text, str):
                    return text
                try:
                    return text.encode('latin-1').decode('utf-8')
                except (UnicodeEncodeError, UnicodeDecodeError):
                    return text
            
            file_info = {
                "fs_id": item.get('fs_id', 0),
                "path": fix_encoding(item.get('path', '')),
                "server_filename": fix_encoding(item.get('server_filename', '')),
                "size": item.get('size', 0),
                "server_mtime": item.get('server_mtime', item.get('server_mtime', 0)),
                "server_ctime": item.get('server_ctime', item.get('server_ctime', 0)),
                "local_mtime": item.get('local_mtime', 0),
                "local_ctime": item.get('local_ctime', 0),
                "isdir": item.get('isdir', 0),
                "category": item.get('category', 0),
                "md5": item.get('md5', ''),
                "thumbs": item.get('thumbs', {}),
                "media_type": item.get('media_type', 0),
                "width": item.get('width', 0),
                "height": item.get('height', 0),
                "duration": item.get('duration', 0)
            }
            files.append(file_info)

        # 记录API调用
        record_api_call('multimedia')

        return {
            "status": "success",
            "message": "获取多媒体文件列表成功",
            "path": path,
            "total": len(files),
            "files": files,
            "has_more": response.get('has_more', False),
            "routed_method": use_method,
            "selected_category": category
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取多媒体文件列表时发生错误: {str(e)}")

@router.get("/rate-limit/status")
async def get_rate_limit_status():
    """
    获取API调用频率限制状态
    
    返回所有API类型的频率限制状态
    """
    try:
        all_status = {}
        for api_type in RATE_LIMITS.keys():
            all_status[api_type] = rate_limiter.get_status(api_type)
        
        return {
            "status": "success",
            "message": "获取频率限制状态成功",
            "rate_limit_status": all_status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取频率限制状态时发生错误: {str(e)}")

@router.get("/auth/status")
async def check_auth_status():
    """
    检查授权状态
    
    返回当前授权状态和用户信息
    """
    try:
        if not access_token:
            return {
                "status": "error",
                "message": "未找到访问令牌，请先进行授权",
                "auth_status": "not_authorized",
                "next_step": "请运行 get_token.py 进行授权"
            }
        
        # 尝试获取用户信息来验证token是否有效
        try:
            user_result = await get_user_info()
            if user_result.get('status') == 'success':
                return {
                    "status": "success",
                    "message": "授权状态正常",
                    "auth_status": "authorized",
                    "access_token": access_token[:20] + "...",
                    "app_key": app_key,
                    "user_info": user_result.get('user_info', {})
                }
            else:
                return {
                    "status": "error",
                    "message": "访问令牌无效或已过期",
                    "auth_status": "expired",
                    "next_step": "请运行 get_token.py 重新授权"
                }
        except:
            return {
                "status": "error",
                "message": "访问令牌无效或已过期",
                "auth_status": "expired",
                "next_step": "请运行 get_token.py 重新授权"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查授权状态时发生错误: {str(e)}")

@router.get("/help")
async def get_netdisk_help():
    """
    获取网盘API帮助信息
    
    返回详细的API使用说明和示例
    """
    return {
        "status": "success",
        "message": "网盘API帮助信息",
        "api_endpoints": {
            "GET /api/netdisk/files": "列出指定路径下的文件和文件夹",
            "GET /api/netdisk/directories": "获取指定路径下的子目录列表",
            "POST /api/netdisk/upload": "上传文件到网盘",
            "GET /api/netdisk/search": "搜索网盘文件",
            "GET /api/netdisk/user/info": "获取用户信息",
            "GET /api/netdisk/user/quota": "获取用户配额信息",
            "GET /api/netdisk/multimedia": "列出多媒体文件",
            "GET /api/netdisk/rate-limit/status": "获取API调用频率限制状态",
            "GET /api/netdisk/auth/status": "检查授权状态",
            "GET /api/netdisk/help": "获取API帮助信息"
        },
        "features": [
            "文件上传下载",
            "文件搜索",
            "目录浏览",
            "多媒体文件管理",
            "用户信息查询",
            "配额信息查询",
            "频率限制管理",
            "授权状态检查"
        ],
        "rate_limits": RATE_LIMITS,
        "usage_examples": {
            "list_files": "GET /api/netdisk/files?path=/&start=0&limit=100",
            "search_files": "GET /api/netdisk/search?keyword=test&path=/&limit=50",
            "upload_file": "POST /api/netdisk/upload (multipart/form-data)",
            "get_user_info": "GET /api/netdisk/user/info",
            "get_quota": "GET /api/netdisk/user/quota",
            "list_multimedia": "GET /api/netdisk/multimedia?category=3&path=/&limit=100"
        }
    }

# ============== 额外HTTP实现（供兼容层或他处调用）==============

async def _filemanager_operate(opera: str, filelist: List[Dict[str, Any]], ondup: str = "fail"):
    can_call, error_msg = check_rate_limit('filemanager')
    if not can_call:
        raise HTTPException(status_code=429, detail=error_msg)
    try:
        payload = json.dumps(filelist, ensure_ascii=False)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 filelist 参数")
    try:
        sdks = _get_sdk_clients()
        access_token = _ensure_access_token()
        if opera == 'copy':
            resp = sdks['filemanager'].filemanagercopy(access_token=access_token, _async=0, filelist=payload, ondup=ondup)
        elif opera == 'move':
            resp = sdks['filemanager'].filemanagermove(access_token=access_token, _async=0, filelist=payload, ondup=ondup)
        elif opera == 'delete':
            resp = sdks['filemanager'].filemanagerdelete(access_token=access_token, _async=0, filelist=payload)
        elif opera == 'rename':
            # SDK 无 ondup 参数时，重名策略可能固定；HTTP 回退会带上 ondup
            try:
                resp = sdks['filemanager'].filemanagerrename(access_token=access_token, _async=0, filelist=payload)
            except Exception:
                raise
        else:
            raise Exception('unsupported opera')
    except Exception:
        resp = _request_pan_api(
            'https://pan.baidu.com/rest/2.0/xpan/file',
            {
                'method': 'filemanager',
                'opera': opera,
                'filelist': payload,
                **({'ondup': ondup} if opera in ('copy','move','rename') else {}),
                'async': 0,
            }
        )
    if resp.get('status') == 'error':
        raise HTTPException(status_code=400, detail=resp.get('message', 'filemanager 调用失败'))
    record_api_call('filemanager')
    if resp.get('errno', 0) != 0:
        raise HTTPException(status_code=400, detail=f"操作失败: {resp.get('errno')}")
    return {"status": "success", "result": resp}

async def copy_files(operations: List[Dict[str, Any]], ondup: str = "newcopy"):
    return await _filemanager_operate('copy', operations, ondup)

async def move_files(operations: List[Dict[str, Any]], ondup: str = "fail"):
    return await _filemanager_operate('move', operations, ondup)

async def delete_files(paths: List[str]):
    ops = [{"path": p} for p in paths]
    return await _filemanager_operate('delete', ops)

async def rename_file(path: str, newname: str):
    ops = [{"path": path, "newname": newname}]
    return await _filemanager_operate('rename', ops)

async def get_download_url(fs_id: int):
    access_token = _ensure_access_token()
    try:
        sdks = _get_sdk_clients()
        resp = sdks['multimedia'].xpanmultimediafilemetas(access_token=access_token, fsids=json.dumps([fs_id]), dlink=1)
    except Exception:
        resp = _request_pan_api(
            'https://pan.baidu.com/rest/2.0/xpan/multimedia',
            {
                'method': 'filemetas',
                'fsids': json.dumps([fs_id]),
                'dlink': 1,
            }
        )
    if resp.get('status') == 'error':
        raise HTTPException(status_code=400, detail=resp.get('message', 'filemetas 调用失败'))
    infos = (resp.get('list') or resp.get('info') or [])
    if not infos:
        raise HTTPException(status_code=404, detail="未找到文件")
    return {"status": "success", "fs_id": fs_id, "dlink": infos[0].get('dlink')}

async def get_downloads(fs_ids: List[int]):
    access_token = _ensure_access_token()
    try:
        sdks = _get_sdk_clients()
        resp = sdks['multimedia'].xpanmultimediafilemetas(access_token=access_token, fsids=json.dumps(fs_ids), dlink=1)
    except Exception:
        resp = _request_pan_api(
            'https://pan.baidu.com/rest/2.0/xpan/multimedia',
            {
                'method': 'filemetas',
                'fsids': json.dumps(fs_ids),
                'dlink': 1,
            }
        )
    if resp.get('status') == 'error':
        raise HTTPException(status_code=400, detail=resp.get('message', 'filemetas 调用失败'))
    infos = (resp.get('list') or resp.get('info') or [])
    out = []
    for it in infos:
        out.append({"fs_id": it.get('fs_id'), "dlink": it.get('dlink'), "size": it.get('size')})
    return {"status": "success", "downloads": out}

async def probe_download(url: str):
    requests, _, _ = get_requests_session()
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return {
            "status": "success",
            "headers": dict(r.headers),
            "code": r.status_code,
            "final_url": r.url,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def get_categoryinfo(category: int, start: int = 0, limit: int = 100, order: str = 'time', desc: int = 1):
    can_call, error_msg = check_rate_limit('fileinfo')
    if not can_call:
        raise HTTPException(status_code=429, detail=error_msg)
    resp = _request_pan_api(
        'https://pan.baidu.com/rest/2.0/xpan/file',
        {
            'method': 'categorylist',
            'category': category,
            'start': start,
            'limit': limit,
            'order': order,
            'desc': desc,
        }
    )
    if resp.get('status') == 'error':
        raise HTTPException(status_code=400, detail=resp.get('message', 'categorylist 调用失败'))
    record_api_call('fileinfo')
    items = resp.get('list') or []
    return {"status": "success", "total": len(items), "files": items, "has_more": resp.get('has_more', False)}

async def get_multimedia_metas(fs_ids: List[int], dlink: int = 0, thumbs: int = 0):
    access_token = _ensure_access_token()
    try:
        sdks = _get_sdk_clients()
        resp = sdks['multimedia'].xpanmultimediafilemetas(access_token=access_token, fsids=json.dumps(fs_ids), dlink=dlink, thumb=thumbs)
    except Exception:
        resp = _request_pan_api(
            'https://pan.baidu.com/rest/2.0/xpan/multimedia',
            {
                'method': 'filemetas',
                'fsids': json.dumps(fs_ids),
                'dlink': dlink,
                'thumb': thumbs,
            }
        )
    if resp.get('status') == 'error':
        raise HTTPException(status_code=400, detail=resp.get('message', 'filemetas 调用失败'))
    infos = resp.get('list') or resp.get('info') or []
    return {"status": "success", "count": len(infos), "metas": infos}
