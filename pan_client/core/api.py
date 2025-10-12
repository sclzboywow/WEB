import os
import json
import logging
from typing import Any, Dict, Optional, List, Tuple

import requests
from pan_client.core.config import get_server_base_url
from pan_client.core.token import (
    get_access_token,
    set_access_token,
    switch_account,
    list_accounts,
    set_current_account,
)
from .abstract_client import (
    AbstractNetdiskClient,
    normalize_file_info,
    normalize_error,
    ClientError,
    AuthenticationError,
    FileNotFoundError,
    PermissionError,
    RateLimitError,
    NetworkError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class RestNetdiskClient(AbstractNetdiskClient):
    """REST-based netdisk client implementation.
    
    Uses direct REST API calls to interact with the netdisk server.
    This is the legacy implementation maintained for backward compatibility.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, base_url: Optional[str] = None, timeout: int = 15) -> None:
        self.config = config or {}
        self.base_url = (base_url or get_server_base_url())
        self.timeout = timeout
        self._session = requests.Session()
        # 注入本地 token（若存在）
        token = get_access_token()
        if token:
            self._session.headers.update({'Authorization': f'Bearer {token}'})
        
        logger.info("RestNetdiskClient initialized")

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def get_userinfo(self) -> Optional[Dict[str, Any]]:
        # 只有在有本地token时才调用服务器接口
        token = get_access_token()
        if not token:
            return None
        
        resp = self._session.get(self._url('/userinfo'), timeout=self.timeout)
        if resp.status_code == 200:
            return resp.json()
        return None

    def get_userinfo_with_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """使用指定 token 获取用户信息（不依赖当前会话头），避免误写入错误账号。"""
        if not access_token:
            return None
        resp = requests.get(self._url('/userinfo'), params={'access_token': access_token}, timeout=self.timeout)
        if resp.status_code == 200:
            return resp.json()
        return None

    def get_auth_qrcode_url(self) -> str:
        return self._url('/auth/scan/qrcode')

    def fetch_auth_qrcode_png(self) -> bytes:
        resp = self._session.get(self._url('/auth/scan/qrcode'), timeout=self.timeout)
        resp.raise_for_status()
        return resp.content

    def fetch_latest_server_token(self) -> Optional[Dict[str, Any]]:
        resp = self._session.get(self._url('/auth/token/latest'), timeout=self.timeout)
        if resp.status_code == 200:
            return resp.json()
        return None

    def set_local_access_token(self, access_token: str, *, account_id: Optional[str] = None, user: Optional[Dict[str, Any]] = None) -> None:
        set_access_token(access_token, account_id=account_id, user=user)
        self._session.headers.update({'Authorization': f'Bearer {access_token}'})

    # -------- 多账号辅助：UI 可调用 --------
    def switch_account(self, account_id: str) -> bool:
        # 先强制设置 current，以免旧会话干扰
        # 仅当目标账号存在时才切换
        set_current_account(account_id)
        ok = switch_account(account_id)
        if ok:
            token = get_access_token(account_id)
            # 重置会话头
            if token:
                self._session.headers.update({'Authorization': f'Bearer {token}'})
            else:
                # 不清除现有Authorization，避免误删旧token导致“token丢失”
                pass
            # 拉取并回写用户信息，确保昵称与 current 生效
            try:
                info = self.get_userinfo() or {}
                if token and info:
                    set_access_token(token, account_id=account_id, user=info)
            except Exception:
                pass
        return ok

    def list_accounts(self) -> List[Dict[str, Any]]:
        return list_accounts()

    def clear_local_access_token(self) -> None:
        """清除会话中的鉴权头，配合删除本地 token 使用。"""
        try:
            if 'Authorization' in self._session.headers:
                self._session.headers.pop('Authorization', None)
        except Exception:
            pass

    def list_files_sync(self, dir_path: str = '/', start: int = 0, limit: int = 100, order: str = 'time', desc: int = 1) -> Dict[str, Any]:
        params = {
            'dir': dir_path,
            'start': start,
            'limit': limit,
            'order': order,
            'desc': desc,
        }
        resp = self._session.get(self._url('/files'), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_quota(self) -> Dict[str, Any]:
        resp = self._session.get(self._url('/quota'), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_cached_files(self, path: Optional[str] = None, kind: Optional[str] = None, limit: Optional[int] = None, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {'offset': offset}
        if path:
            params['path'] = path
        if kind:
            params['kind'] = kind
        if limit is not None:
            params['limit'] = limit
        resp = self._session.get(self._url('/cache/files'), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_auth_url(self) -> Dict[str, Any]:
        """获取简化的授权URL"""
        resp = self._session.get(self._url('/auth/scan/url'), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """使用授权码换取token"""
        resp = self._session.post(
            self._url('/auth/code2token'),
            json={'code': code},
            timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def start_device_code(self) -> Dict[str, Any]:
        """启动设备码流程"""
        resp = self._session.post(self._url('/auth/device/start'), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def poll_device_code(self, device_code: str) -> Dict[str, Any]:
        """轮询设备码状态"""
        resp = self._session.post(
            self._url('/auth/device/poll'),
            json={'device_code': device_code},
            timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json() 

    def get_simple_auth_url(self) -> Dict[str, Any]:
        """获取简化的授权URL"""
        resp = self._session.get(self._url('/auth/simple/url'), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -------------------- 搜索相关 --------------------
    def search_server(self, keyword: str, dir_path: str = '/', recursion: int = 1, page: int = 1, num: int = 100) -> Dict[str, Any]:
        """调用后端 /search 接口搜索网盘（服务器端）。"""
        params = {
            'q': keyword,
            'dir': dir_path,
            'recursion': recursion,
            'page': page,
            'num': num,
        }
        resp = self._session.get(self._url('/search'), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def search_cache(self, keyword: str, path: Optional[str] = None, kind: Optional[str] = None, limit: int = 300) -> Dict[str, Any]:
        """在本地缓存列表中过滤关键字。"""
        data = self.get_cached_files(path=path, kind=kind, limit=limit, offset=0)
        files = data.get('files', []) if isinstance(data, dict) else []
        kw = (keyword or '').lower()
        if kw:
            filtered = []
            for it in files:
                name = (it.get('server_filename') or it.get('name') or it.get('path') or '').lower()
                if kw in name:
                    filtered.append(it)
            data['files'] = filtered
            data['total'] = len(filtered)
        return data

    # -------------------- 上传相关 --------------------
    def upload_to_mine(self, file_path: str, target_path: Optional[str] = None, check_existing: bool = True, conflict_strategy: str = 'skip') -> Dict[str, Any]:
        """上传单个文件到“我的网盘”（使用当前客户端令牌）。"""
        with open(file_path, 'rb') as f:
            files = {
                'file': (os.path.basename(file_path), f, 'application/octet-stream')
            }
            data: Dict[str, Any] = {
                'check_existing': 'true' if check_existing else 'false',
                'conflict_strategy': conflict_strategy,
            }
            if target_path:
                data['path'] = target_path
            resp = self._session.post(self._url('/upload'), files=files, data=data, timeout=None)
            resp.raise_for_status()
            return resp.json()

    def upload_to_shared_batch(self, files_paths: List[str], target_dir: Optional[str] = None, check_existing: bool = True, conflict_strategy: str = 'skip') -> Dict[str, Any]:
        """批量上传到“共享资源”（由后端使用服务器令牌处理）。"""
        # 目标目录不传则让后端用 DEFAULT_DIR
        data: Dict[str, Any] = {
            'check_existing': 'true' if check_existing else 'false',
            'conflict_strategy': conflict_strategy,
        }
        if target_dir:
            data['dir'] = target_dir
        files: List[Tuple[str, Tuple[str, any, str]]] = []
        opened = []
        try:
            for p in files_paths:
                fp = open(p, 'rb')
                opened.append(fp)
                files.append(('file', (os.path.basename(p), fp, 'application/octet-stream')))
            resp = self._session.post(self._url('/upload/batch'), files=files, data=data, timeout=None)
            resp.raise_for_status()
            return resp.json()
        finally:
            for fp in opened:
                try:
                    fp.close()
                except Exception:
                    pass

    # -------------------- 下载相关 --------------------
    def get_dlinks(self, fsids: List[int]) -> Dict[str, Any]:
        """通过 fsid 列表向后端请求下载直链。返回 { items: [ { fsid, dlink, filename } ] }"""
        payload = {'fsids': fsids}
        resp = self._session.post(self._url('/download/dlinks'), json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def stream_file(self, fsid: int):
        """通过后端 /stream 进行代理下载，返回 requests.Response（stream=True）。"""
        import requests
        # 使用内部 session 继承鉴权头
        r = self._session.get(self._url('/stream'), params={'fsid': fsid}, stream=True, timeout=None)
        r.raise_for_status()
        return r

    def delete_files(self, paths: List[str]) -> Dict[str, Any]:
        """删除用户网盘中的文件/目录。仅对"我的网盘"资源使用。"""
        payload = {'paths': paths}
        resp = self._session.post(self._url('/files/delete'), json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def move_files(self, items: List[Dict[str, str]], ondup: str = 'newcopy') -> Dict[str, Any]:
        """移动文件/目录到新位置。items: list of {"path": "/src/file", "dest": "/dest/dir/"}"""
        payload = {'items': items, 'ondup': ondup}
        resp = self._session.post(self._url('/files/move'), json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def copy_files(self, items: List[Dict[str, str]], ondup: str = 'newcopy') -> Dict[str, Any]:
        """复制文件/目录到新位置。items: list of {"path": "/src/file", "dest": "/dest/dir/"}"""
        payload = {'items': items, 'ondup': ondup}
        resp = self._session.post(self._url('/files/copy'), json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def check_file_conflicts(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        """检查文件移动/复制时的冲突。items: list of {"path": "/src/file", "dest": "/dest/dir/"}"""
        payload = {'items': items}
        resp = self._session.post(self._url('/files/check-conflicts'), json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    
    # ==================== AbstractNetdiskClient Implementation ====================
    
    async def list_files(self, path: str, **kwargs) -> Dict[str, Any]:
        """List files in a directory using REST API."""
        try:
            # Extract parameters with defaults
            start = kwargs.get('start', 0)
            limit = kwargs.get('limit', 100)
            order = kwargs.get('order', 'time')
            desc = kwargs.get('desc', 1)
            
            result = self.list_files_sync(path, start=start, limit=limit, order=order, desc=desc)
            
            # Normalize file information
            if 'list' in result:
                normalized_files = []
                for file_data in result['list']:
                    normalized_files.append(normalize_file_info(file_data))
                result['list'] = normalized_files
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list files in {path}: {e}")
            raise normalize_error(e) from e
    
    async def download_file(self, path: str, local_path: str, **kwargs) -> str:
        """Download a file using REST API."""
        try:
            # For REST implementation, we need fsid to download
            # This is a simplified implementation - in practice you'd need to get fsid first
            fsid = kwargs.get('fsid')
            if not fsid:
                raise ValidationError("fsid is required for REST download")
            
            # Use stream_file for download
            response = self.stream_file(fsid)
            
            # Save to local path
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return local_path
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download file {path}: {e}")
            raise normalize_error(e) from e
    
    async def upload_file(self, local_path: str, remote_dir: str, **kwargs) -> Dict[str, Any]:
        """Upload a file using REST API."""
        try:
            target_path = kwargs.get('target_path')
            check_existing = kwargs.get('check_existing', True)
            conflict_strategy = kwargs.get('conflict_strategy', 'skip')
            
            result = self.upload_to_mine(
                local_path, 
                target_path=target_path,
                check_existing=check_existing,
                conflict_strategy=conflict_strategy
            )
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to upload file {local_path}: {e}")
            raise normalize_error(e) from e
    
    async def create_directory(self, path: str, **kwargs) -> Dict[str, Any]:
        """Create a directory using REST API."""
        try:
            # This would need to be implemented in the REST API
            # For now, return a placeholder response
            return {'success': True, 'path': path, 'message': 'Directory creation not implemented in REST API'}
            
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            raise normalize_error(e) from e
    
    async def delete_file(self, path: str, **kwargs) -> Dict[str, Any]:
        """Delete a file using REST API."""
        try:
            result = self.delete_files([path])
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete file {path}: {e}")
            raise normalize_error(e) from e
    
    async def move_file(self, src_path: str, dest_path: str, **kwargs) -> Dict[str, Any]:
        """Move a file using REST API."""
        try:
            ondup = kwargs.get('ondup', 'newcopy')
            items = [{"path": src_path, "dest": dest_path}]
            
            result = self.move_files(items, ondup=ondup)
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to move file {src_path} to {dest_path}: {e}")
            raise normalize_error(e) from e
    
    async def copy_file(self, src_path: str, dest_path: str, **kwargs) -> Dict[str, Any]:
        """Copy a file using REST API."""
        try:
            ondup = kwargs.get('ondup', 'newcopy')
            items = [{"path": src_path, "dest": dest_path}]
            
            result = self.copy_files(items, ondup=ondup)
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to copy file {src_path} to {dest_path}: {e}")
            raise normalize_error(e) from e
    
    async def get_file_info(self, path: str, **kwargs) -> Dict[str, Any]:
        """Get file information using REST API."""
        try:
            # This would need to be implemented in the REST API
            # For now, return a placeholder response
            return {'file_info': {'path': path, 'message': 'File info not implemented in REST API'}}
            
        except Exception as e:
            logger.error(f"Failed to get file info for {path}: {e}")
            raise normalize_error(e) from e
    
    async def search_files(self, query: str, **kwargs) -> Dict[str, Any]:
        """Search files using REST API."""
        try:
            dir_path = kwargs.get('dir_path', '/')
            recursion = kwargs.get('recursion', 1)
            page = kwargs.get('page', 1)
            num = kwargs.get('num', 100)
            
            result = self.search_server(query, dir_path=dir_path, recursion=recursion, page=page, num=num)
            
            # Normalize file information
            if 'list' in result:
                normalized_files = []
                for file_data in result['list']:
                    normalized_files.append(normalize_file_info(file_data))
                result['list'] = normalized_files
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to search files with query '{query}': {e}")
            raise normalize_error(e) from e
    
    async def get_user_info(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Get user information using REST API."""
        try:
            return self.get_userinfo()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get user info: {e}")
            raise normalize_error(e) from e
    
    async def get_auth_status(self, **kwargs) -> Dict[str, Any]:
        """Get authentication status using REST API."""
        try:
            token = get_access_token()
            if not token:
                return {'authenticated': False, 'message': 'No access token found'}
            
            # Try to get user info to verify token
            user_info = self.get_userinfo()
            if user_info:
                return {'authenticated': True, 'user_info': user_info}
            else:
                return {'authenticated': False, 'message': 'Token invalid or expired'}
                
        except Exception as e:
            logger.error(f"Failed to get auth status: {e}")
            return {'authenticated': False, 'error': str(e)}
    
    async def refresh_token(self, **kwargs) -> Dict[str, Any]:
        """Refresh access token using REST API."""
        try:
            # This would need to be implemented in the REST API
            # For now, return a placeholder response
            return {'success': False, 'message': 'Token refresh not implemented in REST API'}
            
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            raise normalize_error(e) from e
    
    def get_client_info(self) -> Dict[str, Any]:
        """Get client information and status."""
        return {
            'type': 'rest',
            'base_url': self.base_url,
            'timeout': self.timeout,
            'has_token': bool(get_access_token()),
            'config': self.config,
        }
    
    async def close(self) -> None:
        """Close the client and cleanup resources."""
        if self._session:
            self._session.close()
            logger.info("RestNetdiskClient closed")


# Backward compatibility alias
ApiClient = RestNetdiskClient