from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect
from PySide6.QtGui import QFont, QIcon, QColor
from PySide6.QtCore import Qt, QSize
import os
from pan_client.core.utils import get_icon_path

class MaterialButton(QPushButton):
    """Material Design风格按钮"""
    def __init__(self, text, icon_name=None, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont("Microsoft YaHei", 10))
        self.setCursor(Qt.PointingHandCursor)
        
        if icon_name:
            icon_path = get_icon_path(icon_name)
            if os.path.exists(icon_path):
                self.setIcon(QIcon(icon_path))
                self.setIconSize(QSize(20, 20))
        
        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 15))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)
        
        self.setStyleSheet("""
            QPushButton {
                padding: 12px 20px;
                background: #F5F9FF;
                border: none;
                border-radius: 8px;
                color: #1976D2;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #E3F2FD;
                color: #1565C0;
            }
            QPushButton:pressed {
                background: #BBDEFB;
            }
            QPushButton:disabled {
                background: #F5F5F5;
                color: #9E9E9E;
            }
        """) 