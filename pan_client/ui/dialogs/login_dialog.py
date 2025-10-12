from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QPushButton, QTextEdit
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
from io import BytesIO
from pan_client.core.token import get_access_token
from pan_client.core.abstract_client import AbstractNetdiskClient
from pan_client.core.mcp_session import McpSession

class LoginDialog(QDialog):
    def __init__(self, client: AbstractNetdiskClient = None, mcp_session: McpSession = None, parent=None):
        super().__init__(parent)
        self.client = client
        self.mcp_session = mcp_session
        self.setWindowTitle('扫码登录百度网盘')
        self.resize(400, 500)
        
        # 检查是否已经有本地token
        local_token = get_access_token()
        if local_token:
            # 如果已经有token，直接关闭对话框
            self.accept()
            return
        
        layout = QVBoxLayout(self)
        
        # 二维码显示区域
        self.qr_label = QLabel('正在获取授权链接...')
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet("border: 1px solid #ddd; background: white;")
        layout.addWidget(self.qr_label)
        
        # 提示信息
        self.tip = QLabel('请使用百度网盘APP扫描二维码完成授权')
        self.tip.setAlignment(Qt.AlignCenter)
        self.tip.setWordWrap(True)
        layout.addWidget(self.tip)
        
        # 授权码输入区域（备用方案）
        self.code_label = QLabel('或者手动输入授权码：')
        layout.addWidget(self.code_label)
        
        self.code_input = QTextEdit()
        self.code_input.setMaximumHeight(60)
        self.code_input.setPlaceholderText('如果扫码失败，请在此输入授权码')
        layout.addWidget(self.code_input)
        
        # 按钮区域
        button_layout = QVBoxLayout()
        
        self.exchange_btn = QPushButton('使用授权码登录')
        self.exchange_btn.clicked.connect(self._exchange_code)
        self.exchange_btn.setEnabled(False)
        button_layout.addWidget(self.exchange_btn)
        
        self.close_btn = QPushButton('取消')
        self.close_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)

        # 轮询定时器
        self._timer = QTimer(self)
        self._timer.setInterval(2000)  # 2秒轮询一次
        self._timer.timeout.connect(self._poll_userinfo)

        # 获取授权URL并生成二维码
        self._load_auth_url()

    def _load_auth_url(self):
        """获取授权URL并生成二维码"""
        try:
            # 使用简化的授权流程
            if self.client:
                auth_data = self.client.get_simple_auth_url()
            else:
                # 向后兼容
                from pan_client.core.rest_client import ApiClient
                api = ApiClient()
                auth_data = api.get_simple_auth_url()
            if auth_data and 'auth_url' in auth_data:
                auth_url = auth_data['auth_url']
                
                if QRCODE_AVAILABLE:
                    # 生成二维码
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(auth_url)
                    qr.make(fit=True)
                    
                    # 创建二维码图片
                    img = qr.make_image(fill_color="black", back_color="white")
                    
                    # 转换为QPixmap
                    buffer = BytesIO()
                    img.save(buffer, format='PNG')
                    buffer.seek(0)
                    
                    pixmap = QPixmap()
                    pixmap.loadFromData(buffer.getvalue())
                    
                    # 缩放二维码到合适大小
                    scaled_pixmap = pixmap.scaled(280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.qr_label.setPixmap(scaled_pixmap)
                else:
                    # 如果没有qrcode库，显示链接文本
                    self.qr_label.setText(f"授权链接:\n{auth_url}")
                    self.qr_label.setAlignment(Qt.AlignCenter)
                
                # 更新提示信息
                self.tip.setText('请使用百度网盘APP扫描二维码完成授权\n扫码后会自动完成登录')
                
                # 启用授权码输入作为备用方案
                self.exchange_btn.setEnabled(True)
                
            else:
                self.qr_label.setText('获取授权URL失败')
                
        except Exception as e:
            self.qr_label.setText(f'获取授权URL失败: {str(e)}')
            self.tip.setText('请尝试手动输入授权码')

    def _exchange_code(self):
        """使用授权码换取token"""
        code = self.code_input.toPlainText().strip()
        if not code:
            return
            
        try:
            # 使用授权码换取token
            if self.client:
                token_data = self.client.exchange_code_for_token(code)
            else:
                # 向后兼容
                from pan_client.core.rest_client import ApiClient
                api = ApiClient()
                token_data = api.exchange_code_for_token(code)
            if token_data and 'access_token' in token_data:
                # 保存token到本地
                if self.client:
                    self.client.set_local_access_token(token_data['access_token'])
                else:
                    # 向后兼容
                    from pan_client.core.rest_client import ApiClient
                    api = ApiClient()
                    api.set_local_access_token(token_data['access_token'])
                
                # 停止轮询
                self._timer.stop()
                
                # 关闭对话框
                self.accept()
            else:
                self.tip.setText('授权码无效，请重新获取')
                
        except Exception as e:
            self.tip.setText(f'授权失败: {str(e)}')

    def _poll_userinfo(self):
        """轮询用户信息（简化版本，不需要轮询）"""
        # 简化版本不需要轮询，用户扫码后直接完成授权
        pass 