from PySide6.QtWidgets import QLineEdit, QGraphicsDropShadowEffect
from PySide6.QtGui import QFont, QColor

class MaterialLineEdit(QLineEdit):
    """Material Design风格输入框"""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(45)
        self.setFont(QFont("Microsoft YaHei", 10))
        
        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 15))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)
        
        self.setStyleSheet("""
            QLineEdit {
                padding: 8px 15px;
                background: white;
                border: 2px solid #E0E0E0;
                border-radius: 8px;
            }
            QLineEdit:focus {
                border: 2px solid #2196F3;
                background: #FFFFFF;
            }
            QLineEdit:hover {
                border: 2px solid #BBDEFB;
            }
        """) 