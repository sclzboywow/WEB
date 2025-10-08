from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor

class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.angle = 0
        
        # 创建并启动定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.rotate)
        self.timer.start(50)
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  
        
    def rotate(self):
        self.angle = (self.angle + 30) % 360
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        width = min(self.width(), self.height())
        rect = QRectF(
            1,
            1,
            width - 2,
            width - 2
        )
        
        # 绘制背景圆环
        pen = QPen()
        pen.setWidth(1)
        pen.setColor(QColor(230, 230, 230))
        painter.setPen(pen)
        painter.drawEllipse(rect)
        
        # 绘制旋转的蓝色弧线
        pen.setColor(QColor(33, 150, 243))
        painter.setPen(pen)
        painter.drawArc(rect, self.angle * 16, 120 * 16) 