import sys
import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QFrame, QSpacerItem, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QFont, QPainter, QPen, QBrush
from pan_client.core.utils import get_icon_path
from pan_client.core.baidu_oauth import BaiduOAuthClient
from pan_client.config.oauth_config import get_oauth_config


class QRCodeWidget(QLabel):
    """二维码显示组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QLabel {
                border: none;
                background-color: transparent;
            }
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)
        
        # 创建占位符二维码
        self.generate_placeholder_qr()
    
    def generate_placeholder_qr(self):
        """生成占位符二维码"""
        pixmap = QPixmap(200, 200)
        pixmap.fill(Qt.white)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制二维码图案（模拟）
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(QBrush(Qt.black))
        
        # 绘制一些方块模拟二维码
        block_size = 8
        for i in range(0, 200, block_size):
            for j in range(0, 200, block_size):
                if (i // block_size + j // block_size) % 3 == 0:
                    painter.drawRect(i, j, block_size-1, block_size-1)
        
        painter.end()
        self.setPixmap(pixmap)
    
    def update_qr_code(self, qr_data):
        """更新二维码数据"""
        # 这里后续会实现真正的二维码生成
        self.generate_placeholder_qr()


class LoginDialog(QDialog):
    """扫码登录对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录")
        self.setFixedSize(380, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border: 1px solid #e1e5e9;
                border-radius: 12px;
            }
        """)
        
        # OAuth配置
        oauth_config = get_oauth_config()
        self.client_id = oauth_config['client_id']
        self.client_secret = oauth_config['client_secret']
        self.redirect_uri = oauth_config['redirect_uri']
        
        # OAuth客户端（在UI线程中运行，避免线程定时器问题）
        self.oauth_client = None
        self._logged_in = False
        
        self.init_ui()
        self.setup_timer()
        # 倒计时定时器
        self.qr_seconds_left = 120
        self.qr_countdown_timer = QTimer(self)
        self.qr_countdown_timer.timeout.connect(self._on_countdown_tick)
        self.qr_countdown_timer.start(1000)
        self._update_countdown_text()
        # 首次立即加载二维码
        QTimer.singleShot(0, self.refresh_qr_code)
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 32, 32, 32)
        
        # 标题
        title_label = QLabel("扫码登录")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 22px;
                font-weight: 600;
                color: #1a1a1a;
                margin-bottom: 8px;
            }
        """)
        layout.addWidget(title_label)
        
        # 说明文字
        instruction_label = QLabel("采用百度网盘扫码登录")
        instruction_label.setAlignment(Qt.AlignCenter)
        instruction_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #8a8a8a;
                margin-bottom: 4px;
            }
        """)
        layout.addWidget(instruction_label)
        
        instruction_label2 = QLabel("请使用手机扫描二维码完成登录")
        instruction_label2.setAlignment(Qt.AlignCenter)
        instruction_label2.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #8a8a8a;
                margin-bottom: 24px;
            }
        """)
        layout.addWidget(instruction_label2)
        
        # 二维码容器 - 居中且不留空白
        qr_container = QFrame()
        qr_container.setFixedSize(220, 220)
        qr_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e1e5e9;
                border-radius: 8px;
            }
        """)
        
        # 二维码组件 - 填满整个容器
        self.qr_widget = QRCodeWidget()
        self.qr_widget.setFixedSize(220, 220)
        
        # 刷新按钮
        refresh_btn = QPushButton()
        refresh_btn.setFixedSize(20, 20)
        refresh_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: #f5f5f5;
                border-radius: 10px;
                icon-size: 12px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
        """)
        
        # 设置刷新图标
        refresh_icon_path = get_icon_path("refresh.png")
        if os.path.exists(refresh_icon_path):
            refresh_btn.setIcon(QIcon(refresh_icon_path))
        else:
            refresh_btn.setText("↻")
            refresh_btn.setStyleSheet(refresh_btn.styleSheet() + """
                QPushButton {
                    font-size: 12px;
                    font-weight: bold;
                    color: #666666;
                }
            """)
        
        refresh_btn.clicked.connect(self.refresh_qr_code)
        
        # 创建二维码和刷新按钮的容器
        qr_wrapper = QFrame()
        qr_wrapper.setFixedSize(220, 220)
        qr_wrapper.setStyleSheet("background: transparent;")
        qr_wrapper_layout = QVBoxLayout(qr_wrapper)
        qr_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        qr_wrapper_layout.addWidget(qr_container)
        
        # 将二维码添加到容器中
        qr_container_layout = QVBoxLayout(qr_container)
        qr_container_layout.setContentsMargins(0, 0, 0, 0)
        qr_container_layout.addWidget(self.qr_widget)
        
        # 添加刷新按钮到底部右侧
        refresh_layout = QHBoxLayout()
        refresh_layout.addStretch()
        refresh_layout.addWidget(refresh_btn)
        refresh_layout.setContentsMargins(0, 0, 4, 4)
        qr_container_layout.addLayout(refresh_layout)
        
        layout.addWidget(qr_wrapper, alignment=Qt.AlignCenter)
        
        # 文字说明（带倒计时）- 去除容器样式，避免看起来像按钮
        self.bottom_text_label = QLabel("请使用百度网盘扫码登录。二维码有效期 <span style=\"color:#1a73e8;\">120</span> 秒")
        self.bottom_text_label.setAlignment(Qt.AlignCenter)
        self.bottom_text_label.setStyleSheet("""
            QLabel { background: transparent; border: none; color: #70757a; font-size: 12px; }
        """)
        self.bottom_text_label.setWordWrap(True)
        self.bottom_tip_label = QLabel("如果二维码失效，请点击右下角刷新按钮重新获取。客户端仅发起百度OAuth授权，不保存您的账号与密码")
        self.bottom_tip_label.setAlignment(Qt.AlignCenter)
        self.bottom_tip_label.setStyleSheet("""
            QLabel { background: transparent; border: none; color: #70757a; font-size: 12px; }
        """)
        self.bottom_tip_label.setWordWrap(True)
        layout.addWidget(self.bottom_text_label)
        layout.addWidget(self.bottom_tip_label)
    
    def create_login_option(self, text, icon_name):
        """创建登录选项按钮"""
        btn = QPushButton()
        btn.setFixedSize(100, 64)
        btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #f8f9fa;
            }
        """)
        
        layout = QVBoxLayout(btn)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 图标 - 使用文字表述
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #4a90e2;
                font-weight: bold;
            }
        """)
        
        # 使用文字图标
        if icon_name == "phone.png":
            icon_label.setText("📱")
        else:
            icon_label.setText("👤")
        
        layout.addWidget(icon_label)
        
        # 文字
        text_label = QLabel(text)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #333333;
                font-weight: 500;
            }
        """)
        layout.addWidget(text_label)
        
        return btn
    
    def setup_timer(self):
        """设置定时器用于刷新二维码"""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh_qr)
        self.refresh_timer.start(30000)  # 30秒自动刷新
    
    def refresh_qr_code(self):
        """刷新二维码"""
        if self._logged_in:
            return
        # 启动百度OAuth扫码登录
        self.start_baidu_oauth()
        # 重置倒计时
        if hasattr(self, 'qr_countdown_timer'):
            self.qr_seconds_left = 120
            self._update_countdown_text()
    
    def auto_refresh_qr(self):
        """自动刷新二维码"""
        self.refresh_qr_code()
    
    def start_baidu_oauth(self):
        """启动百度OAuth扫码登录"""
        try:
            if self._logged_in:
                return
            # 在UI线程中直接启动OAuth流程
            if self.oauth_client is None:
                self.oauth_client = BaiduOAuthClient(self.client_id, self.client_secret, self.redirect_uri)
                self.oauth_client.qr_code_updated.connect(self.on_qr_code_updated)
                self.oauth_client.login_success.connect(self.on_login_success)
                self.oauth_client.login_failed.connect(self.on_login_failed)
                self.oauth_client.status_changed.connect(self.on_status_changed)
            # 生成二维码
            self.oauth_client.start_qr_login()
            
        except Exception as e:
            print(f"启动OAuth失败: {e}")
    
    def on_qr_code_updated(self, qr_pixmap):
        """处理二维码更新"""
        self.qr_widget.setPixmap(qr_pixmap)
    
    def on_login_success(self, user_data):
        """处理登录成功"""
        # 停止所有定时器并安静关闭
        try:
            if hasattr(self, 'refresh_timer'):
                self.refresh_timer.stop()
            if hasattr(self, 'qr_countdown_timer') and self.qr_countdown_timer.isActive():
                self.qr_countdown_timer.stop()
        except Exception:
            pass
        self._logged_in = True
        # 写入多账号存储
        try:
            from pan_client.core.rest_client import ApiClient
            api = ApiClient()
            token = (user_data or {}).get('access_token') or ''
            user = (user_data or {}).get('user') or {}
            # 以 uk 或 userid 作为账号ID
            account_id = str(user.get('uk') or user.get('userid') or 'default')
            if token:
                api.set_local_access_token(token, account_id=account_id, user=user)
        except Exception:
            pass
        # 登录成功后不在控制台输出敏感令牌信息
        self.accept()  # 关闭对话框
    
    def on_login_failed(self, error_msg):
        """处理登录失败"""
        print(f"登录失败: {error_msg}")
        # 可以显示错误消息给用户
    
    def on_status_changed(self, status):
        """处理状态变化"""
        # 保持安静，不在控制台噪声输出
        # 可以更新状态显示
        if status and "过期" in status:
            if hasattr(self, 'qr_countdown_timer') and self.qr_countdown_timer.isActive():
                self.qr_countdown_timer.stop()
    
    def phone_login(self):
        """手机号登录"""
        print("手机号登录")
        # 这里后续会实现手机号登录逻辑
        self.accept()
    
    def account_login(self):
        """账户密码登录"""
        print("账户密码登录")
        # 这里后续会实现账户密码登录逻辑
        self.accept()
    
    def closeEvent(self, event):
        """关闭事件"""
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        if hasattr(self, 'qr_countdown_timer') and self.qr_countdown_timer.isActive():
            self.qr_countdown_timer.stop()
        try:
            if self.oauth_client is not None:
                # 停止后台轮询，避免窗口关闭后仍在等待
                if hasattr(self.oauth_client, 'stop'):
                    self.oauth_client.stop()
                else:
                    self.oauth_client.logout()
        except Exception:
            pass
        event.accept()

    def _on_countdown_tick(self):
        if self._logged_in:
            return
        if self.qr_seconds_left > 0:
            self.qr_seconds_left -= 1
            self._update_countdown_text()
        else:
            if hasattr(self, 'qr_countdown_timer') and self.qr_countdown_timer.isActive():
                self.qr_countdown_timer.stop()
            self.on_status_changed("二维码已过期，请刷新重试")

    def _update_countdown_text(self):
        if hasattr(self, 'bottom_text_label'):
            self.bottom_text_label.setText(
                f"请使用百度网盘扫码登录。二维码有效期 <span style=\"color:#1a73e8;\">{self.qr_seconds_left}</span> 秒"
            )
