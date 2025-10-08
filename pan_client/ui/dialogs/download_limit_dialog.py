from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget, 
                              QFrame, QPushButton)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from pan_client.core.utils import get_icon_path

class DownloadLimitDialog(QDialog):
    """下载限制提示对话框"""
    def __init__(self, parent=None, message="", show_upgrade=False, file_info=None):
        super().__init__(parent)
        self.setWindowTitle("下载限制")
        self.setFixedSize(520, 320)  # 增加宽度和高度，给按钮更多空间
        self.setWindowFlags(Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint)
        
        # 设置窗口背景为白色，移除半透明效果
        self.setStyleSheet("""
            QDialog {
                background: white;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
            }
        """)
        
        self.setup_ui(message, show_upgrade)
        
    def setup_ui(self, message, show_upgrade):
        # 主布局
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)  # 设置合适的边距
        
        # 顶部区域（图标和标题）
        top_layout = QHBoxLayout()
        top_layout.setSpacing(20)
        
        # 警告图标
        icon_label = QLabel()
        icon_label.setPixmap(QIcon(get_icon_path('warning.png')).pixmap(48, 48))
        top_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignTop)
        
        # 消息区域
        msg_container = QWidget()
        msg_layout = QVBoxLayout(msg_container)
        msg_layout.setContentsMargins(0, 0, 0, 0)
        msg_layout.setSpacing(10)
        
        # 标题
        title_label = QLabel("下载次数已达上限")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #333333;
            }
        """)
        msg_layout.addWidget(title_label)
        
        # 消息文本
        msg_label = QLabel(message if message else "此功能在演示模式下不可用")
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #666666;
                line-height: 150%;
            }
        """)
        msg_layout.addWidget(msg_label)
        
        # 添加单次付费下载说明
        pay_label = QLabel("此功能在演示模式下不可用")
        pay_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #FF6B6B;
                font-weight: bold;
                margin-top: 10px;
            }
        """)
        msg_layout.addWidget(pay_label)
        
        top_layout.addWidget(msg_container, 1)
        layout.addLayout(top_layout)
        
        # 添加分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(separator)
        
        # 按钮区域 - 使用流式布局
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)  # 增加顶部边距
        button_layout.setSpacing(15)
        button_layout.addStretch(1)  # 添加弹性空间，使按钮靠右对齐
        
        # 取消按钮
        cancel_btn = QPushButton("关闭")
        cancel_btn.setFixedSize(100, 40)  # 减小宽度
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #F5F5F5;
                color: #666666;
                border: none;
                border-radius: 20px;
                font-size: 14px;
                padding: 0 15px;
            }
            QPushButton:hover {
                background: #EEEEEE;
            }
            QPushButton:pressed {
                background: #E0E0E0;
            }
        """)
        cancel_btn.clicked.connect(self.handle_ok_click)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # 设置主布局
        self.setLayout(layout)

    def handle_ok_click(self):
        """处理确定按钮点击"""
        self.done(0)  # 使用done而不是accept 