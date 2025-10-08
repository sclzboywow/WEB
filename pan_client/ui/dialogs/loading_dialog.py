from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import Qt
from pan_client.ui.widgets.loading_spinner import LoadingSpinner

class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量上传")
        self.setFixedSize(300, 150)
        self.setWindowFlags(Qt.WindowType.Dialog | 
                          Qt.WindowType.CustomizeWindowHint | 
                          Qt.WindowType.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 创建并添加加载动画
        self.spinner = LoadingSpinner(self)
        spinner_container = QWidget()
        spinner_layout = QVBoxLayout()
        spinner_layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        spinner_container.setLayout(spinner_layout)
        
        # 状态文本
        self.status_label = QLabel("准备上传...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 进度文本
        self.progress_label = QLabel("0%")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(spinner_container)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_label)
        self.setLayout(layout)
        
        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background: white;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
            QLabel {
                color: #333;
                font-size: 14px;
                margin-top: 10px;
            }
        """)
    
    def update_status(self, text, percent):
        self.status_label.setText(text)
        self.progress_label.setText(f"{percent}%")
    
    # 新增：开始/结束便捷方法，供外部调用
    def start(self, text: str = "正在处理…"):
        try:
            if text:
                self.status_label.setText(text)
            # 确保动画在运行
            if hasattr(self, 'spinner') and hasattr(self.spinner, 'timer'):
                if not self.spinner.timer.isActive():
                    self.spinner.timer.start(50)
            self.show()
        except Exception:
            self.show()
    
    def stop(self):
        try:
            if hasattr(self, 'spinner') and hasattr(self.spinner, 'timer'):
                self.spinner.timer.stop()
        except Exception:
            pass
        self.close()
        
    def closeEvent(self, event):
        # 确保关闭对话框时停止动画
        if hasattr(self, 'spinner'):
            self.spinner.timer.stop()
        super().closeEvent(event) 