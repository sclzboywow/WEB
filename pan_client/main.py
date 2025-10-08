import sys
import os
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from pan_client.ui.modern_pan import FileManagerUI

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('云栈-您身边的共享资料库')
    app.setQuitOnLastWindowClosed(False)
    
    # 创建界面实例并显示
    window = FileManagerUI()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 