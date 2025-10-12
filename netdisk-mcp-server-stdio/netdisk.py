#!/usr/bin/env python3
"""
网盘MCP服务器
包含用户配额和用户信息查询工具，以及文件上传下载功能
"""
import os
import sys
from typing import Dict, Any, Optional
import hashlib
import requests
import datetime
import json
import io
import time
import random
import threading
from collections import defaultdict, deque

# 添加当前目录到系统路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# 导入MCP相关库
from mcp.server.fastmcp import FastMCP, Context

# 导入网盘SDK相关库
import openapi_client
from openapi_client.api import fileupload_api, fileinfo_api, filemanager_api, userinfo_api, multimediafile_api
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

access_token = os.getenv('BAIDU_NETDISK_ACCESS_TOKEN')
app_key = os.getenv('BAIDU_NETDISK_APP_KEY')
refresh_token = os.getenv('BAIDU_NETDISK_REFRESH_TOKEN')
secret_key = os.getenv('BAIDU_NETDISK_SECRET_KEY')

# 创建MCP服务器
mcp = FastMCP("网盘服务")

# 认证令牌（可选）
AUTH_TOKEN = os.getenv('MCP_AUTH_TOKEN')

def check_auth_token(func):
    """认证装饰器（可选，用于TCP模式）"""
    def wrapper(*args, **kwargs):
        if AUTH_TOKEN:
            # 这里可以添加token验证逻辑
            # 目前MCP库可能不直接支持token验证，需要根据实际MCP库API调整
            pass
        return func(*args, **kwargs)
    return wrapper

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
    
    def can_make_call(self, api_type: str) -> tuple[bool, str]:
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
    
    def get_status(self, api_type: str) -> Dict[str, Any]:
        """获取API调用状态"""
        self._reset_daily_counts()
        
        limits = RATE_LIMITS.get(api_type, RATE_LIMITS['default'])
        status = {
            'api_type': api_type,
            'limits': limits,
            'current_usage': {}
        }
        
        with self.locks[api_type]:
            # 每分钟使用情况
            if 'per_minute' in limits:
                self._clean_old_calls(api_type, 'per_minute')
                status['current_usage']['per_minute'] = {
                    'used': len(self.call_times[api_type]['per_minute']),
                    'limit': limits['per_minute'],
                    'remaining': limits['per_minute'] - len(self.call_times[api_type]['per_minute'])
                }
            
            # 每日使用情况
            if 'daily' in limits:
                status['current_usage']['daily'] = {
                    'used': self.daily_counts[api_type],
                    'limit': limits['daily'],
                    'remaining': limits['daily'] - self.daily_counts[api_type]
                }
        
        return status

# 创建全局频率限制器
rate_limiter = RateLimiter()

def check_rate_limit(api_type: str) -> tuple[bool, str]:
    """检查API调用频率限制"""
    return rate_limiter.can_make_call(api_type)

def get_dynamic_delay(api_type: str) -> float:
    """
    获取动态延迟时间（基于当前调用频率）
    
    频控策略说明:
    - 基于百度网盘API xpanfilelist接口
    - 官方文档未明确说明具体限制
    - 社区经验：建议每分钟不超过5次调用
    - 错误码 errno=-9 通常表示频率限制
    
    当前延迟策略:
    - 0-2次调用: 2秒延迟
    - 3-4次调用: 6秒延迟  
    - 5次及以上: 12秒延迟
    - 全量同步时延迟翻倍
    
    咨询官方时需要确认的问题:
    1. xpanfilelist接口的具体频率限制是多少？
    2. limit参数的最大值是否有限制？
    3. errno=-9错误码的具体含义和触发条件？
    4. 是否有官方推荐的调用频率和延迟策略？
    """
    # 先清理过期记录
    rate_limiter._clean_old_calls(api_type, 'per_minute')
    
    # 获取当前分钟内的调用次数
    minute_calls = rate_limiter.call_times[api_type]['per_minute']
    call_count = len(minute_calls)
    
    # 调试模式下才打印频控信息
    import os
    if os.getenv('DEBUG_RATE_LIMIT', 'false').lower() == 'true':
        print(f"频控检查: {api_type} 当前分钟调用次数: {call_count}")
    
    if call_count >= 5:  # 接近限制时增加延迟
        return 12.0  # 12秒延迟
    elif call_count >= 3:  # 中等频率
        return 6.0   # 6秒延迟
    else:  # 低频率
        return 2.0   # 2秒延迟

def record_api_call(api_type: str):
    """记录API调用"""
    rate_limiter.record_call(api_type)

from contextlib import contextmanager

@contextmanager
def configure_session():
    """配置带有重试机制的会话（上下文管理器）"""
    session = requests.Session()
    try:
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        yield session
    finally:
        session.close()

@mcp.tool()
def upload_file(local_file_path: str, remote_path: str = None) -> Dict[str, Any]:
    """
    上传本地文件到网盘指定路径
    
    参数:
    - local_file_path: 本地文件路径
    - remote_path: 网盘存储路径，必须以/开头。如不指定，将默认上传到"/来自：mcp_server"目录下，这个前缀不能修改
    
    返回:
    - 上传结果信息的字典
    """
    try:
        # 1. 检查文件是否存在
        if not os.path.isfile(local_file_path):
            return {"status": "error", "message": f"本地文件不存在: {local_file_path}"}
        
        # 规范远程路径：允许传入目录或完整路径
        filename = os.path.basename(local_file_path)
        if not remote_path or remote_path.strip() == "":
            remote_path = f"/来自：mcp_server/{filename}"
        else:
            # 如果 remote_path 以 / 结尾或是已有目录，则拼上文件名；否则认为已包含文件名
            if remote_path.endswith('/'):
                remote_path = f"{remote_path}{filename}"
            elif os.path.basename(remote_path) == "":
                remote_path = f"{remote_path}/{filename}"
            elif not remote_path.startswith('/'):
                # 防御：确保以 / 开头
                remote_path = f"/{remote_path}"
        
        # 获取文件大小
        file_size = os.path.getsize(local_file_path)
        
        # 目标目录重复检测：同名或同MD5则跳过
        try:
            target_dir = os.path.dirname(remote_path) or "/"
            existing = list_files(path=target_dir, start=0, limit=1000)
            if existing.get('status') == 'success':
                local_md5 = None
                try:
                    with open(local_file_path, 'rb') as f:
                        local_md5 = hashlib.md5(f.read()).hexdigest()
                except Exception:
                    local_md5 = None

                for item in existing.get('files', []):
                    if item.get('path') == remote_path:
                        return {
                            "status": "skipped",
                            "message": "目标目录已存在同名文件，跳过上传",
                            "remote_path": remote_path,
                            "existing_file": item
                        }
                    if local_md5 and item.get('md5') and item.get('md5') == local_md5:
                        return {
                            "status": "skipped",
                            "message": "目标目录已存在相同内容文件（MD5相同），跳过上传",
                            "remote_path": item.get('path'),
                            "existing_file": item
                        }
        except Exception:
            pass

        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        configuration.socket_options = None  # 使用默认值
        
        # 决定是否需要分片上传
        if file_size <= CHUNK_SIZE:
            # 小文件，直接上传
            return upload_small_file(local_file_path, remote_path, file_size, access_token, configuration)
        else:
            # 大文件，分片上传
            return upload_large_file(local_file_path, remote_path, file_size, access_token, configuration)
                
    except Exception as e:
        return {"status": "error", "message": f"上传文件过程发生错误: {str(e)}"}


def upload_small_file(local_file_path, remote_path, file_size, access_token, configuration=None):
    """处理小文件上传，不需要分片"""
    # 读取文件内容并计算MD5
    with open(local_file_path, 'rb') as f:
        file_content = f.read()
    
    file_md5 = hashlib.md5(file_content).hexdigest()
    block_list = f'["{file_md5}"]'
    
    with openapi_client.ApiClient(configuration) as api_client:
        api_instance = fileupload_api.FileuploadApi(api_client)
        
        # 预创建文件
        try:
            precreate_response = api_instance.xpanfileprecreate(
                access_token=access_token,
                path=remote_path,
                isdir=0,
                size=file_size,
                autoinit=1,
                block_list=block_list,
                rtype=3
            )
            
            if 'errno' in precreate_response and precreate_response['errno'] != 0:
                return {"status": "error", "message": f"预创建文件失败: {precreate_response['errno']}"}
            
            uploadid = precreate_response['uploadid']
            
        except openapi_client.ApiException as e:
            return {"status": "error", "message": f"预创建文件失败: {str(e)}"}
        
        # 上传文件，添加重试逻辑
        for attempt in range(MAX_RETRIES):
            try:
                with open(local_file_path, 'rb') as file:
                    upload_response = api_instance.pcssuperfile2(
                        access_token=access_token,
                        partseq="0",
                        path=remote_path,
                        uploadid=uploadid,
                        type="tmpfile",
                        file=file
                    )
                
                if 'md5' not in upload_response or not upload_response['md5']:
                    return {"status": "error", "message": "文件上传失败: 未返回MD5"}
                
                # 上传成功，跳出重试循环
                break
                    
            except openapi_client.ApiException as e:
                if attempt < MAX_RETRIES - 1:
                    # 计算退避时间
                    sleep_time = RETRY_BACKOFF * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                    continue
                return {"status": "error", "message": f"文件上传失败: {str(e)}"}
        
        # 创建文件（完成上传）
        try:
            create_response = api_instance.xpanfilecreate(
                access_token=access_token,
                path=remote_path,
                isdir=0,
                size=file_size,
                uploadid=uploadid,
                block_list=block_list,
                rtype=3
            )
            
            if 'errno' in create_response and create_response['errno'] != 0:
                return {"status": "error", "message": f"创建文件失败: {create_response['errno']}"}
            
            # 构造返回结果，不包含敏感信息
            return {
                "status": "success",
                "message": "文件上传成功",
                "filename": os.path.basename(remote_path),
                "size": file_size,
                "remote_path": remote_path,
                "fs_id": create_response['fs_id'] if 'fs_id' in create_response else None
            }
            
        except openapi_client.ApiException as e:
            return {"status": "error", "message": f"创建文件失败: {str(e)}"}


def upload_large_file(local_file_path, remote_path, file_size, access_token, configuration=None):
    """处理大文件上传，需要分片"""
    # 计算需要的分片数量
    chunk_count = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    # 准备存储每个分片的MD5
    md5_list = []
    
    # 计算每个分片的MD5
    with open(local_file_path, 'rb') as f:
        for i in range(chunk_count):
            chunk_data = f.read(CHUNK_SIZE)
            chunk_md5 = hashlib.md5(chunk_data).hexdigest()
            md5_list.append(chunk_md5)
    
    # 构建block_list字符串
    block_list = json.dumps(md5_list)
    
    with openapi_client.ApiClient(configuration) as api_client:
        api_instance = fileupload_api.FileuploadApi(api_client)
        
        # 预创建文件
        try:
            precreate_response = api_instance.xpanfileprecreate(
                access_token=access_token,
                path=remote_path,
                isdir=0,
                size=file_size,
                autoinit=1,
                block_list=block_list,
                rtype=3
            )
            
            if 'errno' in precreate_response and precreate_response['errno'] != 0:
                return {"status": "error", "message": f"预创建文件失败: {precreate_response['errno']}"}
            
            uploadid = precreate_response['uploadid']
            
        except openapi_client.ApiException as e:
            return {"status": "error", "message": f"预创建文件失败: {str(e)}"}
        
        # 分片上传，添加重试逻辑
        with open(local_file_path, 'rb') as f:
            for i in range(chunk_count):
                # 读取当前分片
                chunk_data = f.read(CHUNK_SIZE)
                
                # 重试逻辑
                for attempt in range(MAX_RETRIES):
                    try:
                        # 创建文件对象以进行上传
                        file_obj = io.BytesIO(chunk_data)
                        file_obj.name = os.path.basename(local_file_path)
                        
                        # 上传分片
                        upload_response = api_instance.pcssuperfile2(
                            access_token=access_token,
                            partseq=str(i),
                            path=remote_path,
                            uploadid=uploadid,
                            type="tmpfile",
                            file=file_obj
                        )
                        
                        if 'md5' not in upload_response or not upload_response['md5']:
                            if attempt < MAX_RETRIES - 1:
                                # 计算退避时间
                                sleep_time = RETRY_BACKOFF * (2 ** attempt) + random.uniform(0, 1)
                                time.sleep(sleep_time)
                                continue
                            return {"status": "error", "message": f"分片 {i} 上传失败: 未返回MD5"}
                        
                        # 上传成功，跳出重试循环
                        break
                    
                    except openapi_client.ApiException as e:
                        if attempt < MAX_RETRIES - 1:
                            # 计算退避时间
                            sleep_time = RETRY_BACKOFF * (2 ** attempt) + random.uniform(0, 1)
                            time.sleep(sleep_time)
                            continue
                        return {"status": "error", "message": f"分片 {i} 上传失败: {str(e)}"}
        
        # 创建文件（合并分片完成上传）
        try:
            create_response = api_instance.xpanfilecreate(
                access_token=access_token,
                path=remote_path,
                isdir=0,
                size=file_size,
                uploadid=uploadid,
                block_list=block_list,
                rtype=3
            )
            
            if 'errno' in create_response and create_response['errno'] != 0:
                return {"status": "error", "message": f"创建文件失败: {create_response['errno']}"}
            
            return {
                "status": "success",
                "message": "文件分片上传成功",
                "filename": os.path.basename(remote_path),
                "size": file_size,
                "chunks": chunk_count,
                "remote_path": remote_path,
                "fs_id": create_response['fs_id'] if 'fs_id' in create_response else None
            }
            
        except openapi_client.ApiException as e:
            return {"status": "error", "message": f"创建文件失败: {str(e)}"}


@mcp.tool()
def list_files(path: str = "/", start: int = 0, limit: int = 100) -> Dict[str, Any]:
    """
    列出指定路径下的文件和文件夹
    
    调用接口: 百度网盘开放平台 xpanfilelist
    接口URL: https://pan.baidu.com/rest/2.0/xpan/file?method=list&openapi=xpansdk
    HTTP方法: GET
    
    接口参数:
    - access_token: 访问令牌
    - dir: 目录路径
    - start: 起始位置（分页用）
    - limit: 返回数量限制
    - order: 排序方式（name）
    - desc: 是否降序（0=升序）
    
    参数:
    - path: 网盘路径，默认为根目录"/"
    - start: 起始位置，默认为0
    - limit: 返回数量限制，默认为100
    
    返回:
    - 包含文件列表信息的字典
    
    频控说明:
    - 官方文档未明确说明具体限制
    - 社区经验：建议每分钟不超过5次调用
    - 错误码 errno=-9 通常表示频率限制
    - 当前配置：每分钟5次，延迟2-12秒
    """
    try:
        # 检查频率限制
        can_call, error_msg = check_rate_limit('fileinfo')
        if not can_call:
            return {"status": "error", "message": error_msg}
        
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = fileinfo_api.FileinfoApi(api_client)
            
            # 调用文件列表API - 限制limit不超过200（百度API上限）
            safe_limit = min(limit, 200)
            try:
                response = api_instance.xpanfilelist(
                    access_token=access_token,
                    dir=path,
                    start=str(start),
                    limit=safe_limit,
                    order="name",
                    desc=0
                )
            except Exception as api_error:
                print(f"API调用异常: {api_error}")
                return {"status": "error", "message": f"API调用失败: {str(api_error)}"}
            
            # 记录API调用
            record_api_call('fileinfo')
            
            # 检查响应类型
            if not isinstance(response, dict):
                print(f"API响应不是字典类型: {type(response)}")
                print(f"响应内容: {repr(response)}")
                return {"status": "error", "message": f"API响应格式错误: {type(response)}"}
            
            if 'errno' in response and response['errno'] != 0:
                return {"status": "error", "message": f"获取文件列表失败: {response['errno']}"}
            
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
                            # 如果已经是正确编码，不会改变
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
                "has_more_raw": response.get('has_more'),  # 原始响应
                "page_full": len(files) >= safe_limit,  # 是否满页
                "safe_limit": safe_limit  # 安全限制值
            }
            
    except Exception as e:
        return {"status": "error", "message": f"获取文件列表时发生错误: {str(e)}"}


@mcp.tool()
def list_directories(path: str = "/", start: int = 0, limit: int = 100) -> Dict[str, Any]:
    """
    获取指定路径下的子目录列表
    
    参数:
    - path: 网盘路径，默认为根目录"/"
    - start: 起始位置，默认为0
    - limit: 返回数量限制，默认为100
    
    返回:
    - 仅包含目录的列表信息
    """
    try:
        result = list_files(path=path, start=start, limit=limit)
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
        return {"status": "error", "message": f"获取目录列表时发生错误: {str(e)}"}

@mcp.tool()
def download_file(remote_path: str, local_path: str = None, progress_cb=None) -> Dict[str, Any]:
    """
    下载单个网盘文件到本地
    
    参数:
    - remote_path: 网盘文件路径
    - local_path: 本地保存路径，如不指定则保存到当前目录
    
    返回:
    - 下载结果信息的字典
    """
    try:
        # 规范本地输出路径：支持传入目录
        filename = os.path.basename(remote_path)
        if not local_path:
            local_path = os.path.join(BASE_DIR, filename)
        else:
            # 若传入的是目录或以分隔符结尾，则拼接文件名
            if local_path.endswith(os.sep) or os.path.isdir(local_path):
                local_path = os.path.join(local_path, filename)
        
        # 确保本地目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        # 尝试使用requests直接下载
        import requests
        
        # 构建下载URL（这是百度网盘的标准下载方式）
        download_url = f"https://pan.baidu.com/rest/2.0/xpan/file?method=download&access_token={access_token}&path={remote_path}"
        
        print(f"正在下载文件: {remote_path}")
        print(f"保存到: {local_path}")
        
        # 下载文件（分块读取，上报进度）
        with requests.get(download_url, stream=True, timeout=TIMEOUT) as response:
            if response.status_code == 200:
                # 获取文件大小
                total_size = int(response.headers.get('content-length', 0))

                # 写入文件
                with open(local_path, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=256*1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            # 打印与回调
                            try:
                                print(f"\r下载进度: {progress:.1f}%", end='', flush=True)
                            except Exception:
                                pass
                            if callable(progress_cb):
                                try:
                                    progress_cb(progress)
                                except Exception:
                                    pass
                
                try:
                    print(f"\n下载完成!")
                except Exception:
                    pass
                
                # 获取文件信息
                file_size = os.path.getsize(local_path)
                
                result = {
                    "status": "success",
                    "message": "文件下载成功",
                    "remote_path": remote_path,
                    "local_path": local_path,
                    "file_size": file_size,
                    "downloaded_size": downloaded
                }
                if callable(progress_cb):
                    try:
                        progress_cb(100.0)
                    except Exception:
                        pass
                return result
            else:
                return {
                    "status": "error", 
                    "message": f"下载失败，HTTP状态码: {response.status_code}",
                    "response": response.text[:200]
                }
            
    except Exception as e:
        return {"status": "error", "message": f"下载文件时发生错误: {str(e)}"}


@mcp.tool()
def download_files(remote_paths: list, local_dir: str = None) -> Dict[str, Any]:
    """
    批量下载网盘文件到本地
    
    参数:
    - remote_paths: 网盘文件路径列表
    - local_dir: 本地保存目录，如不指定则保存到当前目录
    
    返回:
    - 批量下载结果信息的字典
    """
    try:
        if not remote_paths:
            return {"status": "error", "message": "文件路径列表不能为空"}
        
        # 如果没有指定本地目录，使用当前目录
        if not local_dir:
            local_dir = BASE_DIR
        
        # 确保本地目录存在
        if not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        results = []
        success_count = 0
        error_count = 0
        total_size = 0
        
        print(f"开始批量下载 {len(remote_paths)} 个文件...")
        print(f"保存目录: {local_dir}")
        
        for i, remote_path in enumerate(remote_paths, 1):
            print(f"\n[{i}/{len(remote_paths)}] 正在下载: {remote_path}")
            
            # 生成本地文件路径
            filename = os.path.basename(remote_path)
            local_path = os.path.join(local_dir, filename)
            
            # 如果文件已存在，添加序号
            counter = 1
            original_local_path = local_path
            while os.path.exists(local_path):
                name, ext = os.path.splitext(original_local_path)
                local_path = f"{name}_{counter}{ext}"
                counter += 1
            
            # 下载单个文件
            result = download_file(remote_path, local_path)
            
            if result.get('status') == 'success':
                success_count += 1
                total_size += result.get('file_size', 0)
                print(f"[OK] 下载成功: {filename}")
            else:
                error_count += 1
                print(f"[ERROR] 下载失败: {result.get('message', 'unknown error')}")
            
            results.append({
                "remote_path": remote_path,
                "local_path": local_path,
                "result": result
            })
        
        print(f"\n批量下载完成!")
        print(f"成功: {success_count} 个文件")
        print(f"失败: {error_count} 个文件")
        print(f"总大小: {total_size} 字节")
        
        return {
            "status": "success" if error_count == 0 else "partial_success",
            "message": f"批量下载完成，成功 {success_count} 个，失败 {error_count} 个",
            "total_files": len(remote_paths),
            "success_count": success_count,
            "error_count": error_count,
            "total_size": total_size,
            "local_dir": local_dir,
            "results": results
        }
        
    except Exception as e:
        return {"status": "error", "message": f"批量下载时发生错误: {str(e)}"}


@mcp.tool()
def copy_file(source_path: str, dest_path: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    复制网盘文件或文件夹
    
    参数:
    - source_path: 源文件路径
    - dest_path: 目标文件路径
    - overwrite: 是否覆盖已存在的文件，默认为False
    
    返回:
    - 复制结果信息的字典
    """
    try:
        # 检查源文件是否存在
        source_check = list_files(path=os.path.dirname(source_path), start=0, limit=1000)
        if source_check.get('status') != 'success':
            return {"status": "error", "message": "无法检查源文件是否存在"}
        
        source_exists = False
        source_file_info = None
        for file_info in source_check.get('files', []):
            if file_info.get('path') == source_path:
                source_exists = True
                source_file_info = file_info
                break
        
        if not source_exists:
            return {"status": "error", "message": f"源文件不存在: {source_path}"}
        
        # 检查目标文件是否已存在
        dest_dir = os.path.dirname(dest_path)
        dest_filename = os.path.basename(dest_path)
        
        if not overwrite:
            dest_check = list_files(path=dest_dir, start=0, limit=1000)
            if dest_check.get('status') == 'success':
                for file_info in dest_check.get('files', []):
                    if file_info.get('server_filename') == dest_filename:
                        return {
                            "status": "error", 
                            "message": f"目标文件已存在: {dest_path}。请使用 overwrite=True 参数覆盖，或选择不同的目标路径",
                            "existing_file": file_info
                        }
        
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = filemanager_api.FilemanagerApi(api_client)
            
            # 构建文件列表，按照文档要求使用JSON格式
            filelist = [{"path": source_path, "dest": dest_path}]
            filelist_str = json.dumps(filelist)
            
            # 调用文件复制API
            response = api_instance.filemanagercopy(
                access_token=access_token,
                _async=0,
                filelist=filelist_str
            )
            
            if 'errno' in response and response['errno'] != 0:
                error_msg = f"复制文件失败: {response['errno']}"
                if 'info' in response and response['info']:
                    error_info = response['info'][0]
                    if 'errno' in error_info:
                        error_msg += f" - {error_info['errno']}"
                return {"status": "error", "message": error_msg, "response": response}
            
            # 解析复制结果
            result_info = response.get('info', [{}])[0] if response.get('info') else {}
            
            return {
                "status": "success",
                "message": "文件复制成功",
                "source_path": source_path,
                "dest_path": dest_path,
                "source_file_info": source_file_info,
                "new_fs_id": result_info.get('to_fs_id'),
                "new_path": result_info.get('to_path'),
                "response": response
            }
            
    except Exception as e:
        return {"status": "error", "message": f"复制文件时发生错误: {str(e)}"}


@mcp.tool()
def move_file(source_path: str, dest_path: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    移动网盘文件或文件夹
    
    参数:
    - source_path: 源文件路径
    - dest_path: 目标文件路径
    - overwrite: 是否覆盖已存在的文件，默认为False
    
    返回:
    - 移动结果信息的字典
    """
    try:
        # 检查源文件是否存在
        source_check = list_files(path=os.path.dirname(source_path), start=0, limit=1000)
        if source_check.get('status') != 'success':
            return {"status": "error", "message": "无法检查源文件是否存在"}
        
        source_exists = False
        source_file_info = None
        for file_info in source_check.get('files', []):
            if file_info.get('path') == source_path:
                source_exists = True
                source_file_info = file_info
                break
        
        if not source_exists:
            return {"status": "error", "message": f"源文件不存在: {source_path}"}
        
        # 检查目标文件是否已存在
        dest_dir = os.path.dirname(dest_path)
        dest_filename = os.path.basename(dest_path)
        
        if not overwrite:
            dest_check = list_files(path=dest_dir, start=0, limit=1000)
            if dest_check.get('status') == 'success':
                for file_info in dest_check.get('files', []):
                    if file_info.get('server_filename') == dest_filename:
                        return {
                            "status": "error", 
                            "message": f"目标文件已存在: {dest_path}。请使用 overwrite=True 参数覆盖，或选择不同的目标路径",
                            "existing_file": file_info
                        }
        
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = filemanager_api.FilemanagerApi(api_client)
            
            # 构建文件列表，按照文档要求使用JSON格式
            filelist = [{"path": source_path, "dest": dest_path}]
            filelist_str = json.dumps(filelist)
            
            # 调用文件移动API
            response = api_instance.filemanagermove(
                access_token=access_token,
                _async=0,
                filelist=filelist_str
            )
            
            if 'errno' in response and response['errno'] != 0:
                error_msg = f"移动文件失败: {response['errno']}"
                if 'info' in response and response['info']:
                    error_info = response['info'][0]
                    if 'errno' in error_info:
                        error_msg += f" - {error_info['errno']}"
                return {"status": "error", "message": error_msg, "response": response}
            
            # 解析移动结果
            result_info = response.get('info', [{}])[0] if response.get('info') else {}
            
            return {
                "status": "success",
                "message": "文件移动成功",
                "source_path": source_path,
                "dest_path": dest_path,
                "source_file_info": source_file_info,
                "new_fs_id": result_info.get('to_fs_id'),
                "new_path": result_info.get('to_path'),
                "response": response
            }
            
    except Exception as e:
        return {"status": "error", "message": f"移动文件时发生错误: {str(e)}"}


@mcp.tool()
def delete_file(file_path: str, confirm: bool = False) -> Dict[str, Any]:
    """
    删除网盘文件或文件夹
    
    参数:
    - file_path: 要删除的文件路径
    - confirm: 确认删除，默认为False（安全措施）
    
    返回:
    - 删除结果信息的字典
    """
    try:
        # 检查文件是否存在
        file_dir = os.path.dirname(file_path)
        file_check = list_files(path=file_dir, start=0, limit=1000)
        if file_check.get('status') != 'success':
            return {"status": "error", "message": "无法检查文件是否存在"}
        
        file_exists = False
        file_info = None
        for item in file_check.get('files', []):
            if item.get('path') == file_path:
                file_exists = True
                file_info = item
                break
        
        if not file_exists:
            return {"status": "error", "message": f"文件不存在: {file_path}"}
        
        # 安全检查：需要确认参数
        if not confirm:
            return {
                "status": "error", 
                "message": f"删除操作需要确认。请使用 confirm=True 参数确认删除文件: {file_path}",
                "file_info": file_info,
                "warning": "此操作不可逆，文件将被移动到回收站"
            }
        
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = filemanager_api.FilemanagerApi(api_client)
            
            # 构建文件列表，按照文档要求使用JSON格式
            filelist = [{"path": file_path}]
            filelist_str = json.dumps(filelist)
            
            # 调用文件删除API
            response = api_instance.filemanagerdelete(
                access_token=access_token,
                _async=0,
                filelist=filelist_str
            )
            
            if 'errno' in response and response['errno'] != 0:
                error_msg = f"删除文件失败: {response['errno']}"
                if 'info' in response and response['info']:
                    error_info = response['info'][0]
                    if 'errno' in error_info:
                        error_msg += f" - {error_info['errno']}"
                return {"status": "error", "message": error_msg, "response": response}
            
            return {
                "status": "success",
                "message": "文件删除成功，已移动到回收站",
                "file_path": file_path,
                "deleted_file_info": file_info,
                "response": response
            }
            
    except Exception as e:
        return {"status": "error", "message": f"删除文件时发生错误: {str(e)}"}


@mcp.tool()
def rename_file(file_path: str, new_name: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    重命名网盘文件或文件夹
    
    参数:
    - file_path: 原文件路径
    - new_name: 新文件名
    - overwrite: 是否覆盖已存在的文件，默认为False
    
    返回:
    - 重命名结果信息的字典
    """
    try:
        # 检查原文件是否存在
        file_dir = os.path.dirname(file_path)
        file_check = list_files(path=file_dir, start=0, limit=1000)
        if file_check.get('status') != 'success':
            return {"status": "error", "message": "无法检查原文件是否存在"}
        
        file_exists = False
        file_info = None
        for item in file_check.get('files', []):
            if item.get('path') == file_path:
                file_exists = True
                file_info = item
                break
        
        if not file_exists:
            return {"status": "error", "message": f"原文件不存在: {file_path}"}
        
        # 构建新文件路径
        new_path = os.path.join(file_dir, new_name)
        
        # 检查新文件名是否已存在
        if not overwrite:
            for item in file_check.get('files', []):
                if item.get('server_filename') == new_name and item.get('path') != file_path:
                    return {
                        "status": "error", 
                        "message": f"新文件名已存在: {new_name}。请使用 overwrite=True 参数覆盖，或选择不同的文件名",
                        "existing_file": item
                    }
        
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = filemanager_api.FilemanagerApi(api_client)
            
            # 构建文件列表，按照文档要求使用JSON格式
            filelist = [{"path": file_path, "newname": new_name}]
            filelist_str = json.dumps(filelist)
            
            # 调用文件重命名API
            response = api_instance.filemanagerrename(
                access_token=access_token,
                _async=0,
                filelist=filelist_str
            )
            
            if 'errno' in response and response['errno'] != 0:
                error_msg = f"重命名文件失败: {response['errno']}"
                if 'info' in response and response['info']:
                    error_info = response['info'][0]
                    if 'errno' in error_info:
                        error_msg += f" - {error_info['errno']}"
                return {"status": "error", "message": error_msg, "response": response}
            
            # 解析重命名结果
            result_info = response.get('info', [{}])[0] if response.get('info') else {}
            
            return {
                "status": "success",
                "message": "文件重命名成功",
                "old_path": file_path,
                "new_name": new_name,
                "new_path": result_info.get('to_path'),
                "original_file_info": file_info,
                "response": response
            }
            
    except Exception as e:
        return {"status": "error", "message": f"重命名文件时发生错误: {str(e)}"}


@mcp.tool()
def search_files(keyword: str, path: str = "/", start: int = 0, limit: int = 100) -> Dict[str, Any]:
    """
    搜索网盘文件
    
    参数:
    - keyword: 搜索关键词
    - path: 搜索路径，默认为根目录
    - start: 起始位置，默认为0
    - limit: 返回数量限制，默认为100
    
    返回:
    - 搜索结果信息的字典
    """
    try:
        # 检查频率限制
        can_call, error_msg = check_rate_limit('search')
        if not can_call:
            return {"status": "error", "message": error_msg}
        
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = fileinfo_api.FileinfoApi(api_client)
            
            # 调用文件搜索API
            response = api_instance.xpanfilesearch(
                access_token=access_token,
                key=keyword,
                dir=path,
                page=str(start // limit + 1) if limit > 0 else "1",
                num=str(limit)
            )
            
            # 记录API调用
            record_api_call('search')
            
            if 'errno' in response and response['errno'] != 0:
                return {"status": "error", "message": f"搜索文件失败: {response['errno']}"}
            
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
            
    except Exception as e:
        return {"status": "error", "message": f"搜索文件时发生错误: {str(e)}"}


@mcp.tool()
def get_user_info() -> Dict[str, Any]:
    """
    获取用户信息
    
    返回:
    - 用户信息字典
    """
    try:
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = userinfo_api.UserinfoApi(api_client)
            
            # 调用用户信息API
            response = api_instance.xpannasuinfo(
                access_token=access_token
            )
            
            if 'errno' in response and response['errno'] != 0:
                return {"status": "error", "message": f"获取用户信息失败: {response['errno']}"}
            
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
            
    except Exception as e:
        return {"status": "error", "message": f"获取用户信息时发生错误: {str(e)}"}


@mcp.tool()
def get_quota_info() -> Dict[str, Any]:
    """
    获取用户配额信息（存储空间使用情况）
    
    返回:
    - 配额信息字典
    """
    try:
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = userinfo_api.UserinfoApi(api_client)
            
            # 调用配额信息API
            response = api_instance.apiquota(
                access_token=access_token
            )
            
            if 'errno' in response and response['errno'] != 0:
                return {"status": "error", "message": f"获取配额信息失败: {response['errno']}"}
            
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
            
    except Exception as e:
        return {"status": "error", "message": f"获取配额信息时发生错误: {str(e)}"}


@mcp.tool()
def list_multimedia_files(path: str = "/", recursion: int = 1, start: int = 0, limit: int = 100, order: str = "time", desc: int = 1, category: Optional[int] = None, web: int = 1) -> Dict[str, Any]:
    """
    列出多媒体文件（图片、视频、音频等）
    
    参数:
    - path: 搜索路径，默认为根目录
    - recursion: 是否递归搜索，1为是，0为否
    - start: 起始位置，默认为0
    - limit: 返回数量限制，默认为100
    - order: 排序字段，可选值：time（时间）、name（名称）、size（大小）
    - desc: 是否降序排列，1为是，0为否
    
    返回:
    - 多媒体文件列表
    """
    try:
        with configure_session() as session:
            base_url = 'https://pan.baidu.com/rest/2.0/xpan/file'
            headers = {'User-Agent': 'pan.baidu.com'}

            # Route to dedicated endpoints when possible per official docs:
            # - imagelist (category=3) requires parent_path and returns info array including thumbs when web=1
            # - videolist (category=1), doclist (category=4) similarly
            use_method = None
            params: Dict[str, Any] = {
                'access_token': access_token,
                'web': web,
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
                # 音频
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
                # BT/种子
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
                # Fallback to listall + category filter for other types (audio/apps/other/bt)
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

            r = session.get(base_url, params=params, timeout=TIMEOUT, headers=headers)
            r.raise_for_status()
            response = r.json()
            if 'errno' in response and response['errno'] != 0:
                return {"status": "error", "message": f"获取多媒体文件列表失败: {response['errno']}"}

            # imagelist/videolist/doclist return array field name 'info'; listall returns 'list'
            raw_items = response.get('info') if use_method in ('imagelist', 'videolist', 'doclist') else response.get('list')
            files = []
            for item in raw_items or []:
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
    except Exception as e:
        return {"status": "error", "message": f"获取多媒体文件列表时发生错误: {str(e)}"}


@mcp.tool()
def get_category_info(parent_path: str = "/", category: int = 3, recursion: int = 1) -> Dict[str, Any]:
    """
    获取分类文件总个数（官方 /api/categoryinfo）。
    参数:
    - parent_path: 目录路径
    - category: 1视频、2音频、3图片、4文档、5应用、6其他、7种子
    - recursion: 是否递归（0/1）
    """
    try:
        with configure_session() as session:
            url = 'https://pan.baidu.com/api/categoryinfo'
            params = {
                'access_token': access_token,
                'category': int(category),
                'parent_path': parent_path,
                'recursion': int(recursion),
            }
            headers = {'User-Agent': 'pan.baidu.com'}
            r = session.get(url, params=params, timeout=TIMEOUT, headers=headers)
            r.raise_for_status()
            data = r.json()
            if data.get('errno') != 0:
                return { 'status': 'error', 'message': f"获取分类文件总数失败: {data.get('errno')}", 'response': data }
            # 官方返回 info:{"<category>": { total, size, count }}
            info = data.get('info') or {}
            key = str(int(category))
            detail = info.get(key) or {}
            return {
                'status': 'success',
                'message': '获取分类文件总数成功',
                'parent_path': parent_path,
                'category': int(category),
                'recursion': int(recursion),
                'total': detail.get('total'),
                'count': detail.get('count'),
                'size': detail.get('size'),
                'raw': data,
            }
    except Exception as e:
        return { 'status': 'error', 'message': f"获取分类文件总数时发生错误: {str(e)}" }

@mcp.tool()
def get_multimedia_metas(fsids: list, thumb: int = 1, extra: int = 1, dlink: int = 1, needmedia: int = 1) -> Dict[str, Any]:
    """
    获取多媒体文件元数据信息
    
    参数:
    - fsids: 文件ID列表
    - thumb: 是否返回缩略图，1为是，0为否
    - extra: 是否返回额外信息，1为是，0为否
    - dlink: 是否返回下载链接，1为是，0为否
    - needmedia: 是否返回媒体信息，1为是，0为否
    
    返回:
    - 多媒体文件元数据信息
    """
    try:
        # 配置API客户端
        configuration = openapi_client.Configuration()
        configuration.connection_pool_maxsize = 10
        configuration.retries = MAX_RETRIES
        
        with openapi_client.ApiClient(configuration) as api_client:
            api_instance = multimediafile_api.MultimediafileApi(api_client)
            
            # 将fsids列表转换为JSON字符串（按文档要求）
            fsids_str = json.dumps([int(x) for x in fsids])
            
            # 调用多媒体文件元数据API
            response = api_instance.xpanmultimediafilemetas(
                access_token=access_token,
                fsids=fsids_str,
                thumb=str(thumb),
                extra=str(extra),
                dlink=str(dlink),
                needmedia=needmedia
            )
            
            if 'errno' in response and response['errno'] != 0:
                return {"status": "error", "message": f"获取多媒体文件元数据失败: {response['errno']}"}
            
            # 解析文件元数据
            files = []
            for item in response.get('list', []):
                file_info = {
                    "fs_id": item.get('fs_id', 0),
                    "path": item.get('path', ''),
                    "server_filename": item.get('server_filename', ''),
                    "size": item.get('size', 0),
                    "server_mtime": item.get('server_mtime', 0),
                    "server_ctime": item.get('server_ctime', 0),
                    "local_mtime": item.get('local_mtime', 0),
                    "local_ctime": item.get('local_ctime', 0),
                    "isdir": item.get('isdir', 0),
                    "category": item.get('category', 0),
                    "md5": item.get('md5', ''),
                    "thumbs": item.get('thumbs', {}),
                    "media_type": item.get('media_type', 0),
                    "width": item.get('width', 0),
                    "height": item.get('height', 0),
                    "duration": item.get('duration', 0),
                    "dlink": item.get('dlink', ''),
                    "extra": item.get('extra', {})
                }
                files.append(file_info)
            
            return {
                "status": "success",
                "message": "获取多媒体文件元数据成功",
                "total": len(files),
                "files": files
            }
            
    except Exception as e:
        return {"status": "error", "message": f"获取多媒体文件元数据时发生错误: {str(e)}"}


@mcp.tool()
def create_share_link(fsids: list, period: int = 7, pwd: str = None, remark: str = "") -> Dict[str, Any]:
    """
    创建分享链接
    
    参数:
    - fsids: 分享文件ID列表
    - period: 分享有效期，单位天，默认为7天
    - pwd: 分享密码，4位数字+小写字母组成，如果不提供则自动生成
    - remark: 分享备注，可选
    
    返回:
    - 分享链接信息
    """
    try:
        # 如果没有提供密码，自动生成一个4位密码
        if not pwd:
            import random
            import string
            pwd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        
        # 构建请求URL
        url = f"https://pan.baidu.com/apaas/1.0/share/set"
        
        # 构建请求参数
        params = {
            'product': 'netdisk',
            'appid': app_key,
            'access_token': access_token
        }
        
        # 构建请求体
        data = {
            'fsid_list': json.dumps(fsids),
            'period': str(period),
            'pwd': pwd,
            'remark': remark
        }
        
        # 发送请求
        response = requests.post(url, params=params, data=data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('errno') != 0:
            return {"status": "error", "message": f"创建分享链接失败: {result.get('show_msg', '未知错误')}"}
        
        share_data = result.get('data', {})
        return {
            "status": "success",
            "message": "创建分享链接成功",
            "share_info": {
                "share_id": share_data.get('share_id'),
                "short_url": share_data.get('short_url'),
                "link": share_data.get('link'),
                "period": share_data.get('period'),
                "pwd": share_data.get('pwd'),
                "remark": share_data.get('remark')
            }
        }
        
    except Exception as e:
        return {"status": "error", "message": f"创建分享链接时发生错误: {str(e)}"}


@mcp.tool()
def get_share_info(share_id: int) -> Dict[str, Any]:
    """
    查询分享详情
    
    参数:
    - share_id: 分享ID
    
    返回:
    - 分享详情信息
    """
    try:
        # 构建请求URL
        url = f"https://pan.baidu.com/apaas/1.0/share/query"
        
        # 构建请求参数
        params = {
            'product': 'netdisk',
            'appid': app_key,
            'access_token': access_token,
            'share_id': str(share_id)
        }
        
        # 发送请求
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('errno') != 0:
            return {"status": "error", "message": f"查询分享详情失败: {result.get('show_msg', '未知错误')}"}
        
        share_data = result.get('data', {})
        return {
            "status": "success",
            "message": "查询分享详情成功",
            "share_info": {
                "share_id": share_data.get('share_id'),
                "short_url": share_data.get('short_url'),
                "link": share_data.get('link'),
                "period": share_data.get('period'),
                "pwd": share_data.get('pwd'),
                "remark": share_data.get('remark'),
                "create_time": share_data.get('create_time'),
                "expire_time": share_data.get('expire_time'),
                "file_count": share_data.get('file_count'),
                "file_list": share_data.get('file_list', [])
            }
        }
        
    except Exception as e:
        return {"status": "error", "message": f"查询分享详情时发生错误: {str(e)}"}


@mcp.tool()
def transfer_share_files(share_id: int, pwd: str, fsids: list, dest_path: str = "/") -> Dict[str, Any]:
    """
    分享文件转存
    
    参数:
    - share_id: 分享ID
    - pwd: 分享密码
    - fsids: 要转存的文件ID列表
    - dest_path: 转存目标路径，默认为根目录
    
    返回:
    - 转存任务信息
    """
    try:
        # 构建请求URL
        url = f"https://pan.baidu.com/apaas/1.0/share/transfer"
        
        # 构建请求参数
        params = {
            'product': 'netdisk',
            'appid': app_key,
            'access_token': access_token
        }
        
        # 构建请求体
        data = {
            'share_id': str(share_id),
            'pwd': pwd,
            'fsids': json.dumps(fsids),
            'dest_path': dest_path
        }
        
        # 发送请求
        response = requests.post(url, params=params, data=data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('errno') != 0:
            return {"status": "error", "message": f"转存分享文件失败: {result.get('show_msg', '未知错误')}"}
        
        transfer_data = result.get('data', {})
        return {
            "status": "success",
            "message": "转存分享文件成功",
            "transfer_info": {
                "task_id": transfer_data.get('task_id'),
                "status": transfer_data.get('status'),
                "file_count": transfer_data.get('file_count'),
                "success_count": transfer_data.get('success_count'),
                "fail_count": transfer_data.get('fail_count')
            }
        }
        
    except Exception as e:
        return {"status": "error", "message": f"转存分享文件时发生错误: {str(e)}"}


@mcp.tool()
def get_share_download_url(share_id: int, pwd: str, fsid: int) -> Dict[str, Any]:
    """
    获取分享文件下载地址
    
    参数:
    - share_id: 分享ID
    - pwd: 分享密码
    - fsid: 文件ID
    
    返回:
    - 下载地址信息
    """
    try:
        # 构建请求URL
        url = f"https://pan.baidu.com/apaas/1.0/share/download"
        
        # 构建请求参数
        params = {
            'product': 'netdisk',
            'appid': app_key,
            'access_token': access_token,
            'share_id': str(share_id),
            'pwd': pwd,
            'fsid': str(fsid)
        }
        
        # 发送请求
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('errno') != 0:
            return {"status": "error", "message": f"获取分享下载地址失败: {result.get('show_msg', '未知错误')}"}
        
        download_data = result.get('data', {})
        return {
            "status": "success",
            "message": "获取分享下载地址成功",
            "download_info": {
                "dlink": download_data.get('dlink'),
                "file_name": download_data.get('file_name'),
                "file_size": download_data.get('file_size'),
                "expire_time": download_data.get('expire_time')
            }
        }
        
    except Exception as e:
        return {"status": "error", "message": f"获取分享下载地址时发生错误: {str(e)}"}


@mcp.tool()
def check_auth_status() -> Dict[str, Any]:
    """
    检查授权状态
    
    返回:
    - 授权状态信息
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
        user_result = get_user_info()
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
            
    except Exception as e:
        return {"status": "error", "message": f"检查授权状态时发生错误: {str(e)}"}


@mcp.tool()
def refresh_access_token() -> Dict[str, Any]:
    """
    刷新访问令牌
    
    返回:
    - 刷新结果信息
    """
    try:
        if not refresh_token or not app_key or not secret_key:
            return {
                "status": "error",
                "message": "缺少必要的授权信息，请重新进行完整授权",
                "missing": {
                    "refresh_token": bool(refresh_token),
                    "app_key": bool(app_key),
                    "secret_key": bool(secret_key)
                }
            }
        
        # 构建刷新token的请求
        url = "https://openapi.baidu.com/oauth/2.0/token"
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': app_key,
            'client_secret': secret_key
        }
        
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if 'error' in result:
            return {
                "status": "error",
                "message": f"刷新令牌失败: {result.get('error_description', result.get('error'))}",
                "error_code": result.get('error')
            }
        
        # 更新环境变量
        new_access_token = result.get('access_token')
        new_refresh_token = result.get('refresh_token')
        expires_in = result.get('expires_in')
        scope = result.get('scope')
        
        # 更新.env文件
        env_file = os.path.join(BASE_DIR, '.env')
        env_content = []
        
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                env_content = f.readlines()
        
        # 更新或添加token信息
        updated = False
        for i, line in enumerate(env_content):
            if line.startswith('BAIDU_NETDISK_ACCESS_TOKEN='):
                env_content[i] = f'BAIDU_NETDISK_ACCESS_TOKEN={new_access_token}\n'
                updated = True
            elif line.startswith('BAIDU_NETDISK_REFRESH_TOKEN=') and new_refresh_token:
                env_content[i] = f'BAIDU_NETDISK_REFRESH_TOKEN={new_refresh_token}\n'
        
        if not updated:
            env_content.append(f'BAIDU_NETDISK_ACCESS_TOKEN={new_access_token}\n')
            if new_refresh_token:
                env_content.append(f'BAIDU_NETDISK_REFRESH_TOKEN={new_refresh_token}\n')
        
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(env_content)
        
        # 更新全局变量
        global access_token
        access_token = new_access_token
        
        return {
            "status": "success",
            "message": "访问令牌刷新成功",
            "new_access_token": new_access_token[:20] + "...",
            "expires_in": expires_in,
            "scope": scope,
            "refresh_token_updated": bool(new_refresh_token)
        }
        
    except Exception as e:
        return {"status": "error", "message": f"刷新访问令牌时发生错误: {str(e)}"}


@mcp.tool()
def get_auth_help() -> Dict[str, Any]:
    """
    获取授权帮助信息
    
    返回:
    - 授权帮助信息
    """
    return {
        "status": "success",
        "message": "百度网盘授权帮助信息",
        "auth_steps": [
            "1. 访问百度网盘开放平台: https://pan.baidu.com/union/",
            "2. 注册并创建应用，获取 App Key 和 Secret Key",
            "3. 在 .env 文件中配置以下信息:",
            "   - BAIDU_NETDISK_APP_KEY=你的应用密钥",
            "   - BAIDU_NETDISK_SECRET_KEY=你的应用密钥",
            "4. 运行 python get_token.py 进行授权",
            "5. 授权成功后会自动保存访问令牌到 .env 文件"
        ],
        "required_env_vars": [
            "BAIDU_NETDISK_APP_KEY",
            "BAIDU_NETDISK_SECRET_KEY",
            "BAIDU_NETDISK_ACCESS_TOKEN",
            "BAIDU_NETDISK_REFRESH_TOKEN"
        ],
        "current_status": {
            "app_key": bool(app_key),
            "secret_key": bool(secret_key),
            "access_token": bool(access_token),
            "refresh_token": bool(refresh_token)
        },
        "troubleshooting": [
            "如果授权失败，请检查:",
            "- App Key 和 Secret Key 是否正确",
            "- 应用是否已通过审核",
            "- 网络连接是否正常",
            "- 授权回调地址是否正确配置"
        ]
    }


@mcp.tool()
def get_rate_limit_status(api_type: str = None) -> Dict[str, Any]:
    """
    获取API调用频率限制状态
    
    参数:
    - api_type: API类型，如果为None则返回所有API的状态
    
    返回:
    - 频率限制状态信息
    """
    try:
        if api_type:
            # 返回指定API类型的状态
            if api_type not in RATE_LIMITS:
                return {
                    "status": "error",
                    "message": f"未知的API类型: {api_type}",
                    "available_types": list(RATE_LIMITS.keys())
                }
            
            status = rate_limiter.get_status(api_type)
            return {
                "status": "success",
                "message": f"获取{api_type}API频率限制状态成功",
                "rate_limit_status": status
            }
        else:
            # 返回所有API类型的状态
            all_status = {}
            for api_type in RATE_LIMITS.keys():
                all_status[api_type] = rate_limiter.get_status(api_type)
            
            return {
                "status": "success",
                "message": "获取所有API频率限制状态成功",
                "rate_limit_status": all_status
            }
            
    except Exception as e:
        return {"status": "error", "message": f"获取频率限制状态时发生错误: {str(e)}"}


@mcp.tool()
def wait_for_rate_limit(api_type: str, max_wait_time: int = 300) -> Dict[str, Any]:
    """
    等待API调用频率限制解除
    
    参数:
    - api_type: API类型
    - max_wait_time: 最大等待时间（秒），默认为300秒
    
    返回:
    - 等待结果信息
    """
    try:
        if api_type not in RATE_LIMITS:
            return {
                "status": "error",
                "message": f"未知的API类型: {api_type}",
                "available_types": list(RATE_LIMITS.keys())
            }
        
        start_time = time.time()
        wait_count = 0
        
        while time.time() - start_time < max_wait_time:
            can_call, error_msg = check_rate_limit(api_type)
            if can_call:
                return {
                    "status": "success",
                    "message": f"{api_type}API频率限制已解除，可以调用",
                    "wait_time": time.time() - start_time,
                    "wait_count": wait_count
                }
            
            wait_count += 1
            time.sleep(1)  # 等待1秒后重试
        
        return {
            "status": "error",
            "message": f"等待{api_type}API频率限制解除超时（{max_wait_time}秒）",
            "wait_time": time.time() - start_time,
            "wait_count": wait_count
        }
        
    except Exception as e:
        return {"status": "error", "message": f"等待频率限制解除时发生错误: {str(e)}"}


@mcp.resource("netdisk://help")
def get_help() -> str:
    """提供网盘工具的帮助信息"""
    return """
    网盘MCP服务帮助:
    
    本服务提供以下工具:
    1. upload_file - 上传本地文件到网盘
       参数: local_file_path, [remote_path]
       如不指定remote_path，将默认上传到"/来自：mcp_server"目录下
       说明: remote_path 可传目录或完整路径；上传前会在目标目录做同名/同MD5检测，存在则跳过
       
    2. list_files - 列出指定路径下的文件和文件夹
       参数: path (可选，默认为根目录), start (可选，默认为0), limit (可选，默认为100)
       说明: 用于列出目录下内容，可配合上传前重复检测
       
    3. download_file - 下载单个网盘文件到本地
       参数: remote_path, [local_path]
       如不指定local_path，将保存到当前目录
       
    4. download_files - 批量下载网盘文件到本地
       参数: remote_paths (文件路径列表), [local_dir] (本地保存目录)
       如不指定local_dir，将保存到当前目录
       
    5. copy_file - 复制网盘文件或文件夹
       参数: source_path, dest_path
       
    6. move_file - 移动网盘文件或文件夹
       参数: source_path, dest_path
       
    7. delete_file - 删除网盘文件或文件夹
       参数: file_path
       
    8. rename_file - 重命名网盘文件或文件夹
       参数: file_path, new_name
       
    9. search_files - 搜索网盘文件
       参数: keyword, [path] (可选，默认为根目录), [start] (可选，默认为0), [limit] (可选，默认为100)
       
    10. get_user_info - 获取用户信息
       参数: 无
       返回: 用户基本信息（用户名、头像、VIP等级等）
       
    11. get_quota_info - 获取用户配额信息（存储空间使用情况）
       参数: 无
       返回: 存储空间使用情况（总容量、已用、剩余、使用率等）
       
    12. list_multimedia_files - 列出多媒体文件（图片、视频、音频等）
       参数: [path] (可选，默认为根目录), [recursion] (可选，默认为1), [start] (可选，默认为0), [limit] (可选，默认为100), [order] (可选，默认为time), [desc] (可选，默认为1)
       返回: 多媒体文件列表（包含缩略图、尺寸、时长等信息）
       
    13. get_multimedia_metas - 获取多媒体文件元数据信息
       参数: fsids (文件ID列表), [thumb] (可选，默认为1), [extra] (可选，默认为1), [dlink] (可选，默认为1), [needmedia] (可选，默认为1)
       返回: 多媒体文件元数据（包含缩略图、下载链接、媒体信息等）
       
    14. create_share_link - 创建分享链接
       参数: fsids (文件ID列表), [period] (可选，默认为7天), [pwd] (可选，自动生成), [remark] (可选，分享备注)
       返回: 分享链接信息（包含分享ID、短链、密码等）
       
    15. get_share_info - 查询分享详情
       参数: share_id (分享ID)
       返回: 分享详情信息（包含文件列表、创建时间、过期时间等）
       
    16. transfer_share_files - 分享文件转存
       参数: share_id (分享ID), pwd (分享密码), fsids (文件ID列表), [dest_path] (可选，默认为根目录)
       返回: 转存任务信息（包含任务ID、状态、文件数量等）
       
    17. get_share_download_url - 获取分享文件下载地址
       参数: share_id (分享ID), pwd (分享密码), fsid (文件ID)
       返回: 下载地址信息（包含下载链接、文件名、文件大小等）
       
    18. check_auth_status - 检查授权状态
       参数: 无
       返回: 当前授权状态和用户信息
       
    19. refresh_access_token - 刷新访问令牌
       参数: 无
       返回: 刷新结果和新的令牌信息
       
    20. get_auth_help - 获取授权帮助信息
       参数: 无
       返回: 详细的授权步骤和故障排除信息
       
    21. get_rate_limit_status - 获取API调用频率限制状态
       参数: [api_type] (可选，API类型，如果为None则返回所有API的状态)
       返回: 频率限制状态信息（包含使用情况和剩余次数）
       
    22. wait_for_rate_limit - 等待API调用频率限制解除
       参数: api_type (API类型), [max_wait_time] (可选，最大等待时间，默认为300秒)
       返回: 等待结果信息

    23. list_directories - 获取目录列表
       参数: [path] (可选，默认为根目录), [start], [limit]
       返回: 仅包含目录的列表，可用于上传前选择目标目录
       
    使用示例:
    - 上传文件(默认目录): upload_file("/本地文件路径/文件名.ext")
    - 上传到指定目录: upload_file("/本地文件路径/文件名.ext", "/来自：mcp_server/图片/")
    - 指定完整路径上传: upload_file("/本地/1.png", "/来自：mcp_server/图片/1.png")
    - 列出根目录文件: list_files("/")
    - 列出指定目录: list_files("/我的文档")
    - 分页获取文件: list_files("/", start=0, limit=50)
    - 获取目录列表: list_directories("/来自：mcp_server")
    - 下载单个文件: download_file("/来自：mcp_server/文件名.ext", "/本地保存路径/文件名.ext")
    - 批量下载文件: download_files(["/来自：mcp_server/文件1.ext", "/来自：mcp_server/文件2.ext"], "/本地保存目录")
    - 复制文件: copy_file("/来自：mcp_server/原文件.ext", "/来自：mcp_server/副本.ext")
    - 移动文件: move_file("/来自：mcp_server/文件.ext", "/我的文档/文件.ext")
    - 删除文件: delete_file("/来自：mcp_server/文件.ext")
    - 重命名文件: rename_file("/来自：mcp_server/旧文件名.ext", "新文件名.ext")
    - 搜索文件: search_files("关键词", "/来自：mcp_server")
    - 获取用户信息: get_user_info()
    - 获取配额信息: get_quota_info()
    - 列出多媒体文件: list_multimedia_files("/", recursion=1, order="time", desc=1)
    - 获取多媒体元数据: get_multimedia_metas([1234567890, 1234567891])
    - 创建分享链接: create_share_link([1234567890, 1234567891], period=7, remark="测试分享")
    - 查询分享详情: get_share_info(57999490044)
    - 转存分享文件: transfer_share_files(57999490044, "12zx", [1234567890], "/我的文档")
    - 获取分享下载地址: get_share_download_url(57999490044, "12zx", 1234567890)
    - 检查授权状态: check_auth_status()
    - 刷新访问令牌: refresh_access_token()
    - 获取授权帮助: get_auth_help()
    - 安全复制文件: copy_file("/源文件路径", "/目标路径", overwrite=True)
    - 安全移动文件: move_file("/源文件路径", "/目标路径", overwrite=True)
    - 安全删除文件: delete_file("/文件路径", confirm=True)
    - 安全重命名文件: rename_file("/文件路径", "新文件名", overwrite=True)
    - 检查频率限制状态: get_rate_limit_status("search")
    - 查看所有API频率状态: get_rate_limit_status()
    - 等待频率限制解除: wait_for_rate_limit("search", max_wait_time=60)
    
    注意:
    - 大于4MB的文件会自动分片上传
    - 小于等于4MB的文件会直接上传
    - 上传失败时会自动重试
    - access_token参数已被隐藏，将自动使用环境变量中的值
    """


if __name__ == "__main__":
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='网盘MCP服务器')
    parser.add_argument('--transport', choices=['stdio', 'tcp', 'http'], 
                       default='stdio', help='传输模式 (默认: stdio)')
    parser.add_argument('--tcp-host', default='0.0.0.0', 
                       help='TCP监听地址 (默认: 0.0.0.0)')
    parser.add_argument('--tcp-port', type=int, default=8765, 
                       help='TCP监听端口 (默认: 8765)')
    parser.add_argument('--tls-cert', help='TLS证书文件路径')
    parser.add_argument('--tls-key', help='TLS私钥文件路径')
    parser.add_argument('--tls-ca', help='TLS CA证书文件路径')
    parser.add_argument('--auth-token', help='认证令牌 (可选)')
    parser.add_argument('--http-host', default='0.0.0.0', 
                       help='HTTP监听地址 (默认: 0.0.0.0)')
    parser.add_argument('--http-port', type=int, default=8000, 
                       help='HTTP监听端口 (默认: 8000)')
    
    args = parser.parse_args()
    
    # 根据传输模式启动服务器
    if args.transport == 'tcp':
        if args.tls_cert and args.tls_key:
            # TLS模式
            print(f"启动TLS TCP服务器: {args.tcp_host}:{args.tcp_port}")
            print(f"证书: {args.tls_cert}")
            print(f"私钥: {args.tls_key}")
            mcp.run(transport='tcp', host=args.tcp_host, port=args.tcp_port, 
                   tls_cert=args.tls_cert, tls_key=args.tls_key)
        else:
            # 纯TCP模式
            print(f"启动TCP服务器: {args.tcp_host}:{args.tcp_port}")
            mcp.run(transport='tcp', host=args.tcp_host, port=args.tcp_port)
    elif args.transport == 'http':
        print(f"启动HTTP服务器: {args.http_host}:{args.http_port}")
        mcp.run(transport='streamable-http', host=args.http_host, port=args.http_port)
    else:
        # stdio模式（默认）
        print("启动stdio模式服务器")
        mcp.run(transport="stdio")
