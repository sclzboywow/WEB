from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QPropertyAnimation, Property
from PySide6.QtGui import QPainter, QPen, QColor

class CircularProgressBar(QWidget):
    """自定义圆形进度条"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)  # 保持控件大小不变
        self._progress = 0
        self._animation = QPropertyAnimation(self, b"progress", self)
        self._animation.setDuration(200)

    @Property(float)
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = value
        self.update()
        
    @Property(float)
    def value(self):
        return self._progress

    @value.setter
    def value(self, value):
        """设置进度值(0-100)"""
        self._progress = value / 100.0  # 转换为0-1的范围
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制背景圆环
        pen = QPen()
        pen.setWidth(2)
        pen.setColor(QColor("#E0E0E0"))
        painter.setPen(pen)
        painter.drawArc(1, 1, 14, 14, 0, 360 * 16)  # 增大圆环尺寸为14x14

        # 绘制进度圆环
        if self._progress > 0:
            pen.setColor(QColor("#2196F3"))
            painter.setPen(pen)
            painter.drawArc(1, 1, 14, 14, 90 * 16, -self._progress * 360 * 16) 