"""
OAuth回调服务器
用于处理百度OAuth授权回调
"""

import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """OAuth回调处理器"""
    
    def __init__(self, *args, callback_func=None, **kwargs):
        self.callback_func = callback_func
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """处理GET请求"""
        try:
            # 解析URL
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            # 检查是否是OAuth回调
            if parsed_url.path == '/oauth/callback':
                self._handle_oauth_callback(query_params)
            else:
                self._send_response(404, "Not Found")
                
        except Exception as e:
            print(f"处理回调请求失败: {e}")
            self._send_response(500, "Internal Server Error")
    
    def _handle_oauth_callback(self, params):
        """处理OAuth回调"""
        try:
            # 获取授权码和state
            code = params.get('code', [None])[0]
            state = params.get('state', [None])[0]
            error = params.get('error', [None])[0]
            
            if error:
                # 用户取消授权
                self._send_oauth_response({
                    'success': False,
                    'error': error,
                    'message': '用户取消授权'
                })
                return
            
            if code and state:
                # 授权成功
                result = {
                    'success': True,
                    'code': code,
                    'state': state
                }
                
                # 调用回调函数
                if self.callback_func:
                    self.callback_func(code, state)
                
                self._send_oauth_response(result)
            else:
                # 参数不完整
                self._send_oauth_response({
                    'success': False,
                    'error': 'invalid_request',
                    'message': '缺少必要参数'
                })
                
        except Exception as e:
            print(f"处理OAuth回调失败: {e}")
            self._send_oauth_response({
                'success': False,
                'error': 'server_error',
                'message': str(e)
            })
    
    def _send_oauth_response(self, data):
        """发送OAuth响应"""
        response_data = json.dumps(data, ensure_ascii=False)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response_data.encode('utf-8'))))
        self.end_headers()
        
        self.wfile.write(response_data.encode('utf-8'))
    
    def _send_response(self, status_code, message):
        """发送简单响应"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))
    
    def log_message(self, format, *args):
        """禁用日志输出"""
        pass


class OAuthCallbackServer:
    """OAuth回调服务器"""
    
    def __init__(self, host='localhost', port=8080, callback_func=None):
        self.host = host
        self.port = port
        self.callback_func = callback_func
        self.server = None
        self.server_thread = None
        self.running = False
    
    def start(self):
        """启动服务器"""
        try:
            # 创建处理器类
            handler_class = lambda *args, **kwargs: OAuthCallbackHandler(
                *args, callback_func=self.callback_func, **kwargs
            )
            
            # 创建HTTP服务器
            self.server = HTTPServer((self.host, self.port), handler_class)
            
            # 启动服务器线程
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            
            self.running = True
            print(f"OAuth回调服务器已启动: http://{self.host}:{self.port}")
            
        except Exception as e:
            print(f"启动OAuth回调服务器失败: {e}")
            raise
    
    def stop(self):
        """停止服务器"""
        if self.server and self.running:
            self.running = False
            self.server.shutdown()
            self.server.server_close()
            print("OAuth回调服务器已停止")
    
    def _run_server(self):
        """运行服务器"""
        try:
            self.server.serve_forever()
        except Exception as e:
            if self.running:
                print(f"OAuth回调服务器运行错误: {e}")


def create_callback_server(callback_func, host='localhost', port=8080):
    """创建OAuth回调服务器"""
    server = OAuthCallbackServer(host, port, callback_func)
    server.start()
    return server
