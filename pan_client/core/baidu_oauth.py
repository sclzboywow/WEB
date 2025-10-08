"""
百度OAuth扫码登录模块
基于百度OAuth 2.0协议实现扫码登录功能
"""

import json
import time
import hashlib
import hmac
import base64
import urllib.parse
from typing import Dict, Optional, Tuple
import requests
from PySide6.QtCore import QObject, Signal, QTimer, QThread, Qt
from PySide6.QtGui import QPixmap, QPainter, QPen, QBrush, QImage
from PySide6.QtWidgets import QApplication
from pan_client.core.api import ApiClient


class BaiduOAuthClient(QObject):
    """百度OAuth客户端"""
    
    # 信号定义
    qr_code_updated = Signal(QPixmap)  # 二维码更新
    login_success = Signal(dict)  # 登录成功
    login_failed = Signal(str)  # 登录失败
    status_changed = Signal(str)  # 状态变化
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        
        # OAuth相关URL
        self.auth_url = "https://openapi.baidu.com/oauth/2.0/authorize"
        self.token_url = "https://openapi.baidu.com/oauth/2.0/token"
        self.user_info_url = "https://openapi.baidu.com/rest/2.0/passport/users/getInfo"
        
        # 状态管理
        self.state = None
        self.code = None
        self.access_token = None
        self.refresh_token = None
        self.openid = None
        self.unionid = None
        self.user_info = None
        
        # 轮询相关
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_authorization)
        self.poll_interval = 2000  # 2秒轮询一次
        self.max_poll_time = 300000  # 5分钟超时
        self.poll_start_time = 0
        # 防止重复成功/失败回调
        self._completed = False
        
    def generate_state(self) -> str:
        """生成state参数用于防CSRF攻击"""
        timestamp = str(int(time.time()))
        random_str = hashlib.md5(timestamp.encode()).hexdigest()[:8]
        self.state = f"{timestamp}_{random_str}"
        return self.state
    
    def build_auth_url(self) -> str:
        """构建授权URL"""
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'basic',
            'display': 'popup',  # 适用于桌面软件应用
            'state': self.generate_state(),
            'qrext_clientid': self.client_id,  # 网盘扫码透传字段
            'qrcodeW': 200,  # 自定义二维码宽度
            'qrcodeH': 200,  # 自定义二维码高度
        }
        
        query_string = urllib.parse.urlencode(params)
        return f"{self.auth_url}?{query_string}"
    
    def start_qr_login(self):
        """开始二维码登录流程。改为从服务器获取授权URL，确保与服务器回调一致。"""
        try:
            # 若已完成一次登录流程，避免重复启动
            self._completed = False
            # 从客户端配置读取后端 base_url
            try:
                import json, os
                conf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
                with open(conf_path, 'r', encoding='utf-8') as f:
                    base_url = json.load(f).get('base_url')
            except Exception:
                base_url = None
            if not base_url:
                raise Exception('缺少服务器 base_url 配置')

            # 生成本次会话 state，并请求服务器生成带 state 的授权URL
            if not self.state:
                self.generate_state()
            resp = requests.get(
                base_url.rstrip('/') + '/auth/scan/url',
                params={'state': self.state},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            auth_url = data.get('auth_url')
            if not auth_url:
                raise Exception('服务器未返回 auth_url')
            # 若服务端返回了标准化的 state，则与客户端保持一致
            srv_state = data.get('state')
            if srv_state:
                self.state = srv_state

            # 生成二维码
            qr_pixmap = self._generate_qr_code(auth_url)
            self.qr_code_updated.emit(qr_pixmap)

            # 开始轮询授权状态（使用 state 参数隔离会话）
            self._start_polling()

            self.status_changed.emit("请使用手机扫描二维码完成登录")

        except Exception as e:
            self.login_failed.emit(f"启动登录失败: {str(e)}")
    
    def _generate_qr_code(self, url: str) -> QPixmap:
        """生成二维码图片"""
        try:
            # 优先使用 qrcode 生成真实可扫二维码
            try:
                import qrcode
                qr = qrcode.QRCode(
                    version=4,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=4,
                    border=1,
                )
                qr.add_data(url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                # 转换为QPixmap
                img = img.convert('RGB')
                w, h = img.size
                data = img.tobytes('raw', 'RGB')
                qimg = QImage(data, w, h, 3 * w, QImage.Format_RGB888)
                return QPixmap.fromImage(qimg).scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception:
                # 回退：使用占位图（不可扫）
                pixmap = QPixmap(220, 220)
                pixmap.fill(Qt.white)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(QPen(Qt.black, 1))
                painter.setBrush(QBrush(Qt.black))
                block_size = 8
                for i in range(0, 220, block_size):
                    for j in range(0, 220, block_size):
                        if (i // block_size + j // block_size) % 3 == 0:
                            painter.drawRect(i, j, block_size-1, block_size-1)
                painter.end()
                return pixmap
            
        except Exception as e:
            # 返回空白图片
            pixmap = QPixmap(200, 200)
            pixmap.fill(Qt.white)
            return pixmap
    
    def _start_polling(self):
        """开始轮询授权状态"""
        self.poll_start_time = int(time.time() * 1000)
        self.poll_timer.start(self.poll_interval)
    
    def _stop_polling(self):
        """停止轮询"""
        self.poll_timer.stop()
    
    def stop(self):
        """对外停止接口，供UI在关闭时调用"""
        self._stop_polling()
    
    def _poll_authorization(self):
        """轮询授权状态"""
        try:
            if self._completed:
                return
            # 检查是否超时
            current_time = int(time.time() * 1000)
            if current_time - self.poll_start_time > self.max_poll_time:
                self._stop_polling()
                self.login_failed.emit("登录超时，请重新扫码")
                return
            
            # 从服务器查询是否已兑换到 token
            import os, json as _json
            base_url = None
            try:
                conf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
                with open(conf_path, 'r', encoding='utf-8') as f:
                    base_url = _json.load(f).get('base_url')
            except Exception:
                base_url = None
            if base_url:
                try:
                    # 使用按 state 轮询接口，避免多个账号互相覆盖
                    poll_url = base_url.rstrip('/') + '/auth/token/poll'
                    resp = requests.get(poll_url, params={'state': self.state}, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json() or {}
                        # 仅接受在本次扫码开始之后生成的 token，防止历史 token 导致“未扫码即登录”
                        created_at = int(data.get('created_at') or 0)
                        poll_start_sec = int(self.poll_start_time / 1000)
                        if created_at >= (poll_start_sec - 3):  # 允许少量时间偏差
                            self.access_token = data.get('access_token')
                            self.refresh_token = data.get('refresh_token')
                            # 保存到本地并尝试补充用户信息，防止覆盖旧账号
                            try:
                                api = ApiClient()
                                # 直接用本次 access_token 获取 userinfo，避免被会话头污染
                                try:
                                    info = api.get_userinfo_with_token(self.access_token or '') or {}
                                except Exception:
                                    info = {}
                                if info:
                                    # 用 uk/userid 作为账号ID 重新写入并设为当前
                                    account_id = str(info.get('uk') or info.get('userid') or 'default')
                                    api.set_local_access_token(self.access_token or '', account_id=account_id, user=info)
                            except Exception:
                                pass
                            self._stop_polling()
                            self._completed = True
                            self.status_changed.emit("授权成功，已获取令牌")
                            self.login_success.emit(data)
                            return
                except Exception:
                    pass

            # 未完成则继续等待
            self.status_changed.emit("等待用户扫码授权...")
            
        except Exception as e:
            self._stop_polling()
            self.login_failed.emit(f"轮询失败: {str(e)}")
    
    def handle_callback(self, code: str, state: str) -> bool:
        """处理授权回调"""
        try:
            # 验证state参数
            if state != self.state:
                self.login_failed.emit("State参数验证失败")
                return False
            
            self.code = code
            self._stop_polling()
            
            # 获取access_token
            if self._get_access_token():
                # 获取用户信息
                if self._get_user_info():
                    self.login_success.emit({
                        'access_token': self.access_token,
                        'refresh_token': self.refresh_token,
                        'openid': self.openid,
                        'unionid': self.unionid,
                        'user': (self.user_info or {})
                    })
                    return True
            
            return False
            
        except Exception as e:
            self.login_failed.emit(f"处理回调失败: {str(e)}")
            return False
    
    def _get_access_token(self) -> bool:
        """获取access_token"""
        try:
            params = {
                'grant_type': 'authorization_code',
                'code': self.code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': self.redirect_uri
            }
            
            response = requests.post(self.token_url, data=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error' in data:
                self.login_failed.emit(f"获取token失败: {data.get('error_description', '未知错误')}")
                return False
            
            self.access_token = data.get('access_token')
            self.refresh_token = data.get('refresh_token')
            
            return True
            
        except Exception as e:
            self.login_failed.emit(f"获取access_token失败: {str(e)}")
            return False
    
    def _get_user_info(self) -> bool:
        """获取用户信息"""
        try:
            params = {
                'access_token': self.access_token,
                'get_unionid': 1
            }
            
            response = requests.get(self.user_info_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error_code' in data:
                self.login_failed.emit(f"获取用户信息失败: {data.get('error_msg', '未知错误')}")
                return False
            
            self.openid = data.get('openid')
            self.unionid = data.get('unionid')
            self.user_info = data
            
            return True
            
        except Exception as e:
            self.login_failed.emit(f"获取用户信息失败: {str(e)}")
            return False
    
    def refresh_access_token(self) -> bool:
        """刷新access_token"""
        try:
            if not self.refresh_token:
                return False
            
            params = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            response = requests.post(self.token_url, data=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error' in data:
                return False
            
            self.access_token = data.get('access_token')
            self.refresh_token = data.get('refresh_token')
            
            return True
            
        except Exception:
            return False
    
    def get_user_info(self) -> Optional[Dict]:
        """获取当前用户信息"""
        if not self.access_token:
            return None
        
        try:
            params = {
                'access_token': self.access_token,
                'get_unionid': 1
            }
            
            response = requests.get(self.user_info_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error_code' in data:
                return None
            
            return data
            
        except Exception:
            return None
    
    def logout(self):
        """登出"""
        self._stop_polling()
        self.access_token = None
        self.refresh_token = None
        self.openid = None
        self.unionid = None
        self.code = None
        self.state = None


class BaiduOAuthWorker(QThread):
    """百度OAuth工作线程"""
    
    # 信号定义
    qr_code_updated = Signal(QPixmap)
    login_success = Signal(dict)
    login_failed = Signal(str)
    status_changed = Signal(str)
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        super().__init__()
        self.oauth_client = BaiduOAuthClient(client_id, client_secret, redirect_uri)
        
        # 连接信号
        self.oauth_client.qr_code_updated.connect(self.qr_code_updated)
        self.oauth_client.login_success.connect(self.login_success)
        self.oauth_client.login_failed.connect(self.login_failed)
        self.oauth_client.status_changed.connect(self.status_changed)
    
    def run(self):
        """运行OAuth流程"""
        self.oauth_client.start_qr_login()
    
    def handle_callback(self, code: str, state: str) -> bool:
        """处理授权回调"""
        return self.oauth_client.handle_callback(code, state)
    
    def refresh_token(self) -> bool:
        """刷新token"""
        return self.oauth_client.refresh_access_token()
    
    def get_user_info(self) -> Optional[Dict]:
        """获取用户信息"""
        return self.oauth_client.get_user_info()
    
    def logout(self):
        """登出"""
        self.oauth_client.logout()
