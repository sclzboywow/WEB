import sys
import os
import time
import hashlib
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QLineEdit, QLabel, 
                              QTreeView, QFileDialog, QMessageBox, QProgressBar,
                              QStatusBar, QSystemTrayIcon, QMenu, QFrame,
                              QGraphicsDropShadowEffect, QHeaderView, QDialog,
                              QGroupBox, QGridLayout, QAbstractItemView, QListWidget,
                              QListWidgetItem, QCheckBox, QRadioButton, QButtonGroup,
                              QDialogButtonBox, QTextEdit)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize, QPoint, QPropertyAnimation, Property, QRectF, QEvent, QObject
from PySide6.QtGui import (QStandardItemModel, QStandardItem, QIcon, QFont, 
                          QColor, QPainter, QPen, QPainterPath, QBrush, QPixmap,
                          QMovie)
from pan_client.core.utils import get_icon_path
from pan_client.core.api import ApiClient
from pan_client.core.abstract_client import AbstractNetdiskClient
from pan_client.core.client_factory import create_client_with_fallback
from pan_client.core.mcp_session import McpSession
from pan_client.ui.widgets.circular_progress_bar import CircularProgressBar
from pan_client.ui.widgets.material_line_edit import MaterialLineEdit
from pan_client.ui.widgets.material_button import MaterialButton
from pan_client.ui.dialogs import UserInfoDialog, DownloadLimitDialog, LoadingDialog
from pan_client.ui.dialogs.login_dialog import LoginDialog
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from datetime import datetime
from pan_client.ui.dialogs.document_viewer import DocumentViewer

class FileManagerUI(QMainWindow):
    def __init__(self, client: AbstractNetdiskClient = None, mcp_session: McpSession = None):
        super().__init__()
        
        # 初始化UI相关属性
        self.is_vip = True  # 默认为VIP用户体验，以便启用多选等功能

        # 后端客户端 - 支持MCP和REST模式
        self.client = client or create_client_with_fallback({})
        self.mcp_session = mcp_session
        
        # 为了向后兼容，保留api属性
        if hasattr(self.client, '_session'):
            self.api = self.client  # RestNetdiskClient
        else:
            # 为MCP客户端创建兼容适配器
            from pan_client.core.api import RestCompatibilityAdapter
            self.api = RestCompatibilityAdapter(self.client)
        
        # 初始化用户信息对话框
        self._user_info_dialog = None
        
        # 初始化分页相关属性
        self.page_size = 1000  # 每页显示数量
        self.current_page = 1
        self.has_more = True
        self.is_loading = False
        self.current_folder = '/'  # 默认从根目录开始
        self.view_mode = 'shared'  # 默认共享资源视图，未登录也可使用
        
        # 复制粘贴相关属性
        self.clipboard_files = []  # 剪贴板中的文件列表
        self.clipboard_operation = None  # 操作类型：'copy' 或 'cut'
        
        self.initUI()
        self.bootstrap_and_load()  # 登录并加载文件
        
        # 设置窗口图标
        self.setWindowIcon(QIcon(get_icon_path('logo.png')))
        
        # 创建系统托盘
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(get_icon_path('logo.png')))
        self.create_tray_icon()
        
        # 设置任务栏图标（Windows系统）
        try:
            import ctypes
            myappid = 'mycompany.sharealbum.app.1.0.1'  # 应用程序ID
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            print(f"设置任务栏图标失败: {e}")
        
        # 添加加载对话框
        self.loading_dialog = LoadingDialog(self)
        
        # 连接滚动信号
        self.file_tree.verticalScrollBar().valueChanged.connect(self.check_scroll_position)
        
        # 设置MCP状态更新定时器
        self.mcp_status_timer = QTimer()
        self.mcp_status_timer.timeout.connect(self._update_mcp_status)
        self.mcp_status_timer.start(5000)  # 每5秒更新一次
        
    def generate_machine_code(self):
        """生成机器码（演示用）"""
        return "DEMO-MACHINE-CODE-12345"
        
    def initUI(self):
        """初始化界面"""
        self.setWindowTitle('云栈-您身边的共享资料库 V1.0.1')
        self.resize(1200, 800)
        self.setFixedSize(1200, 800)
        
        # 设置窗口标志，移除拖动手柄
        self.setWindowFlags(Qt.Window | Qt.MSWindowsFixedSizeDialogHint)
        
        # 设置窗口样式
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1: 0, y1: 0,
                    x2: 1, y2: 1,
                    stop: 0 #F5F7FA,
                    stop: 1 #E4E9F2
                );
            }
        """)
        
        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建左侧导航栏
        nav_bar = QFrame()  # 创建一个框架组件作为导航栏容器
        nav_bar.setObjectName("navBar")  # 设置对象名称，用于CSS样式选择器
        nav_bar.setStyleSheet("""
            QFrame#navBar {  # 使用ID选择器指定样式
                background: #2C3E50;
                border-right: 1px solid #34495E;
            }
        """)
        nav_bar.setFixedWidth(80)  # 调整宽度以适应垂直图标
        nav_layout = QVBoxLayout(nav_bar)  # 创建垂直布局
        nav_layout.setContentsMargins(15, 25, 15, 25)  # 设置布局的内边距（左、上、右、下）
        nav_layout.setSpacing(10)  # 设置垂直布局中各个控件之间的间距为10像素
        
        # 添加Logo
        logo_frame = QFrame()  # 创建一个框架组件作为Logo容器
        logo_layout = QVBoxLayout(logo_frame)  # 创建垂直布局
        logo_layout.setContentsMargins(0, 0, 0, 20)  # 设置Logo区域的内边距（左、上、右、下）
        
        logo_icon = QLabel()
        logo_icon.setPixmap(QIcon(get_icon_path('logo.png')).pixmap(32,32))
        logo_text = QLabel("云栈")
        logo_text.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        logo_text.setStyleSheet("color: #1976D2;")
        
        logo_layout.addWidget(logo_icon, alignment=Qt.AlignCenter)  # 将Logo图标添加到Logo区域  
        logo_layout.addWidget(logo_text, alignment=Qt.AlignCenter)  # 将Logo文本添加到Logo区域
        nav_layout.addWidget(logo_frame)  # 将Logo容器添加到导航栏布局
        
        # 添加导航按钮
        nav_buttons = [
            ("首页", self.go_home, "home.png"),
            ("共享资源", self.show_shared_resources, "share.png"),
            ("上传文档", self.upload_file, "upload.png"),
            ("我的信息", self.show_my_info, "user.png")
        ]
        
        for text, slot, icon in nav_buttons:
            btn = MaterialButton("", icon, self)  # 仅显示图标
            btn.setFixedSize(50, 50)  # 调整按钮大小
            btn.clicked.connect(slot)  # 将按钮的点击事件连接到相应的槽函数
            btn.setToolTip(text)  # 添加工具提示，显示按钮功能
            nav_layout.addWidget(btn, alignment=Qt.AlignCenter)  # 将按钮添加到导航栏布局
        
        nav_layout.addStretch()  # 添加一个伸缩空间，使按钮靠右对齐
        main_layout.addWidget(nav_bar)  # 将导航栏添加到主布局
        
        # 创建右侧内容区
        content_area = QFrame()  # 创建一个框架组件作为内容区容器
        content_area.setObjectName("contentArea")  # 设置对象名称，用于CSS样式选择器
        content_area.setStyleSheet("""
            QFrame#contentArea {
                background: #FFFFFF;
                border-radius: 12px; 
                margin: 5px;
            }
        """)
        
        # 添加内容区阴影
        shadow = QGraphicsDropShadowEffect(content_area)  # 创建阴影效果
        shadow.setBlurRadius(20)  # 设置阴影的模糊半径为20像素  
        shadow.setColor(QColor(0, 0, 0, 25))  # 设置阴影的颜色和透明度
        shadow.setOffset(0, 2)  # 设置阴影的偏移量（水平和垂直）
        content_area.setGraphicsEffect(shadow)
        
        content_layout = QVBoxLayout(content_area)  # 创建垂直布局
        content_layout.setContentsMargins(5, 5, 5, 5)  # 设置布局的内边距（左、上、右、下）
        content_layout.setSpacing(20)  # 设置垂直布局中各个控件之间的间距为20像素
        
        # 添加搜索栏
        search_frame = QFrame()  # 创建一个框架组件作为搜索栏容器
        search_layout = QHBoxLayout(search_frame)  # 创建水平布局
        search_layout.setContentsMargins(0, 0, 0, 0)  # 设置布局的内边距（左、上、右、下）
        
        self.search_input = MaterialLineEdit("请输入您要搜索的文件编号或名称...")
        self.search_input.returnPressed.connect(self.search_files)  # 添加回车键支持
        
        search_btn = MaterialButton("搜索", "search.png")
        search_btn.setFixedWidth(100)  # 设置搜索按钮的宽度为120像素
        search_btn.clicked.connect(self.search_files)  # 将搜索按钮的点击事件连接到搜索文件的槽函数
        
        search_layout.addWidget(self.search_input)  # 将搜索输入框添加到搜索栏布局
        search_layout.addWidget(search_btn)  # 将搜索按钮添加到搜索栏布局
        content_layout.addWidget(search_frame)  # 将搜索栏容器添加到内容区布局
        
        # 创建文件列表
        self.file_tree = QTreeView()
        self.file_tree.installEventFilter(self)
        self.file_tree.doubleClicked.connect(self.on_item_double_clicked)
        self.file_tree.clicked.connect(self.on_tree_clicked)
        self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.file_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 根据VIP状态设置选择模式
        if self.is_vip:
            self.file_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)  # VIP用户可以多选
        else:
            self.file_tree.setSelectionMode(QAbstractItemView.SingleSelection)  # 非VIP用户单选
        
        # 移除序号列
        self.file_tree.setRootIsDecorated(False)  # 不显示根节点的装饰（即不显示展开/折叠图标）
        self.file_tree.setItemsExpandable(False)  # 禁止项目展开
        
        self.file_tree.setEditTriggers(QTreeView.NoEditTriggers)  # 禁用编辑
        self.file_tree.setStyleSheet("""
            QTreeView {
                background: white; 
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                padding: 10px;
                outline: none;  /* 移除焦点框 */
                show-decoration-selected: 0;  /* 移除选中项的装饰 */
            }
            QTreeView::item {
                height: 40px;
                border: none;  /* 移除项目边框 */
                border-radius: 4px;
                margin: 2px 0;
            }
            QTreeView::branch {
                background: transparent;  /* 移除树状图分支线 */
                border: none;
            }
            QTreeView::item:hover {
                background: #F5F5F5;
            }
            QTreeView::item:selected {
                background: #E3F2FD;
                color: #1976D2;
            }
            /* 垂直滚动条样式 */
            QScrollBar:vertical {
                border: none;
                background: #F5F5F5;
                width: 10px;
                margin: 40px 0 0 0;  /* 顶部margin设置为表头高度 */
            }
            QScrollBar::handle:vertical {
                background: #BDBDBD;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #9E9E9E;
            }
            QScrollBar::add-line:vertical {
                height: 0px;
            }
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            /* 水平滚动条样式 */
            QScrollBar:horizontal {
                border: none;
                background: #F5F5F5;
                height: 10px;
                margin: 0 10px 0 0;  /* 右侧margin留出垂直滚动条的宽度 */
            }
            QScrollBar::handle:horizontal {
                background: #BDBDBD;
                border-radius: 5px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #9E9E9E;
            }
            QScrollBar::add-line:horizontal {
                width: 0px;
            }
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)
        
        # 修改模型标题，添加分享列
        self.model = QStandardItemModel()   
        self.model.setHorizontalHeaderLabels(['文件名称', '文件大小', '文件类型', '上传时间', '下载', '分享', '举报'])  
        self.file_tree.setModel(self.model)  
        
        # 设置列宽和对齐方式
        header = self.file_tree.header()
        header.setStretchLastSection(False)  # 禁用最后一列自动拉伸
        
        # 设置固定列宽和对齐方式
        header.resizeSection(0, 550)  # 文件名列 - 左对齐（默认）
        header.resizeSection(1, 100)  # 文件大小列
        header.resizeSection(2, 80)  # 文件类型列
        header.resizeSection(3, 130)  # 上传时间列
        header.resizeSection(4, 60)   # 下载列
        header.resizeSection(5, 60)   # 分享列
        header.resizeSection(6, 60)   # 举报列

        # 设置对齐方式
        self.model.horizontalHeaderItem(0).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 文件名左对齐
        self.model.horizontalHeaderItem(1).setTextAlignment(Qt.AlignCenter)  # 文件大小居中
        self.model.horizontalHeaderItem(2).setTextAlignment(Qt.AlignCenter)  # 文件类型居中
        self.model.horizontalHeaderItem(3).setTextAlignment(Qt.AlignCenter)  # 上传时间居中
        self.model.horizontalHeaderItem(4).setTextAlignment(Qt.AlignCenter)  # 下载居中
        self.model.horizontalHeaderItem(5).setTextAlignment(Qt.AlignCenter)  # 分享居中
        self.model.horizontalHeaderItem(6).setTextAlignment(Qt.AlignCenter)  # 举报居中
        
        # 防止用户手动调整列宽
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        
        # 右键菜单已在上面设置，这里不需要重复设置
        
        # 设置表头样式
        header = self.file_tree.header()  # 获取文件树的表头
        header.setStyleSheet("""
            QHeaderView::section {
                background: white;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #E0E0E0;
                font-family: "Microsoft YaHei";  /* 使用微软雅黑字体 */
                font-size: 12px;                 /* 设置字体大小 */
                font-weight: 500;                /* 调整字重，不要太粗 */
                color: #333333;                  /* 更深的文字颜色 */
                letter-spacing: 0.5px;           /* 增加字间距 */
            }
            QHeaderView::section:hover {
                background: #F5F5F5;          /* 悬停时背景颜色为浅灰色 */
            }
        """)
        
        content_layout.addWidget(self.file_tree)  # 将文件树添加到内容区布局
        
        main_layout.addWidget(content_area)
        
        # 创建状态栏
        self.statusBar = QStatusBar()  # 创建状态栏
        self.statusBar.setStyleSheet("""
            QStatusBar {                              /* 状态栏整体样式 */
                background: white;                   /* 背景色为白色 */
                border-top: 1px solid #E0E0E0;      /* 上边框颜色为灰色 */  
            }
            QStatusBar QLabel {
                color: #424242;                  /* 文本颜色为深灰色 */
                padding: 3px;                     /* 内边距为3px */
            }
        """)
        self.setStatusBar(self.statusBar)  # 将状态栏设置为窗口的状态栏
        
        # 添加状态标签
        self.status_label = QLabel()
        self.status_label.setFont(QFont("Microsoft YaHei", 9))
        self.statusBar.addWidget(self.status_label)
        
        # 添加MCP状态指示器
        self.mcp_status_label = QLabel()
        self.mcp_status_label.setFont(QFont("Microsoft YaHei", 9))
        self.mcp_status_label.setStyleSheet("color: #666;")
        self.statusBar.addPermanentWidget(self.mcp_status_label)
        
        # 更新MCP状态显示
        self._update_mcp_status()
        
        # 添加进度条到状态栏
        self.progress_bar = CircularProgressBar()
        self.progress_bar.setFixedSize(16, 16)  # 调整为更小的尺寸
        self.progress_bar.hide()  # 默认隐藏
        self.statusBar.addPermanentWidget(self.progress_bar)
        

    def create_tray_icon(self):
        """创建系统托盘"""
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #E3F2FD;
                color: #2196F3;
            }
            QMenu::separator {
                height: 1px;
                background: #E0E0E0;
                margin: 5px 0;
            }
        """)
        
        show_action = tray_menu.addAction("显示界面")
        show_action.triggered.connect(self.show)
        
        tray_menu.addSeparator()
        
        # 添加版本检测
        check_version_action = tray_menu.addAction("检查更新")
        check_version_action.triggered.connect(self._check_version_from_tray)  # 直接连接，不用 lambda
        
        # 添加关于信息
        about_action = tray_menu.addAction("关于")
        about_action.triggered.connect(self.show_about)
        
        tray_menu.addSeparator()
        
        quit_action = tray_menu.addAction("退出")
        quit_action.triggered.connect(self.quit_application)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        self.tray_icon.setToolTip('云栈')

    def _update_mcp_status(self):
        """更新MCP连接状态显示"""
        if self.mcp_session and self.mcp_session.is_alive():
            try:
                # 获取MCP指标
                metrics = self.mcp_session.get_metrics()
                summary = self.mcp_session.get_metrics_summary()
                
                # 构建状态文本
                if metrics['call_count'] > 0:
                    status_text = f"MCP已连接 | {summary}"
                    # 根据健康度设置颜色
                    if metrics['health_score'] >= 80:
                        color = "#4CAF50"  # 绿色 - 健康
                    elif metrics['health_score'] >= 60:
                        color = "#FF9800"  # 橙色 - 警告
                    else:
                        color = "#F44336"  # 红色 - 不健康
                else:
                    status_text = "MCP已连接"
                    color = "#4CAF50"  # 绿色
                
                self.mcp_status_label.setText(status_text)
                self.mcp_status_label.setStyleSheet(f"color: {color};")
                
            except Exception as e:
                # 如果获取指标失败，显示基本状态
                self.mcp_status_label.setText("MCP已连接")
                self.mcp_status_label.setStyleSheet("color: #4CAF50;")
        else:
            self.mcp_status_label.setText("MCP未连接")
            self.mcp_status_label.setStyleSheet("color: #F44336;")  # 红色

    def _check_version_from_tray(self):
        """从系统托盘触发的版本检查"""
        QMessageBox.information(self, '版本检查', '版本检查功能已移除业务逻辑，仅保留界面。')

    def closeEvent(self, event):
        """重写关闭事件"""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "云栈",
            "程序已最小化到系统托盘\n双击托盘图标可以重新打开",
            QSystemTrayIcon.Information,
            2000
        )

    def close(self):
        """重写关闭方法，确保MCP会话正确清理"""
        try:
            if self.mcp_session:
                import asyncio
                asyncio.run(self.mcp_session.dispose())
        except Exception as e:
            print(f"清理MCP会话时出错: {e}")
        super().close()

    def tray_icon_activated(self, reason):
        """处理托盘图标事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isHidden():
                self.show()
                self.activateWindow()
            else:
                self.hide()

    def showEvent(self, event):
        """窗口首次显示后再按比例调整列宽，避免初始化阶段宽度为0导致比例错误。"""
        super().showEvent(event)
        try:
            QTimer.singleShot(0, self.adjust_column_widths)
        except Exception:
            pass

    def quit_application(self):
        """退出应用"""
        box = QMessageBox(self)
        box.setWindowTitle('退出确认')
        box.setText("确定要退出程序吗？")
        box.setIcon(QMessageBox.Question)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("是")
        box.button(QMessageBox.No).setText("否")
        reply = box.exec()
        
        if reply == QMessageBox.Yes:
            try:
                # 隐藏托盘图标并退出应用
                self.tray_icon.hide()
                QApplication.quit()
            except Exception as e:
                # 记录错误后继续退出
                print(f"退出时出错: {e}")
                self.tray_icon.hide()
                QApplication.quit()

    def go_home(self):
        """返回主页（个人网盘视图）"""
        self.view_mode = 'mine'
        self.current_folder = '/'
        self.load_dir(self.current_folder)

    def show_shared_resources(self):
        """切换到共享资源视图（仅服务器缓存）。"""
        self.view_mode = 'shared'
        self.current_folder = '/'
        self.load_dir(self.current_folder)

    def upload_file(self):
        """上传文件：用户选择文件后，确认上传到共享资源或我的网盘。"""
        # 选择文件（可多选）
        file_paths, _ = QFileDialog.getOpenFileNames(self, '选择要上传的文件')
        if not file_paths:
            return
        
        # 选择目标：共享资源 / 我的网盘
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('选择上传目标')
        msg_box.setText('将所选文件上传到：')
        msg_box.setInformativeText('请选择上传目标位置')
        
        # 创建自定义按钮
        shared_btn = msg_box.addButton('共享资源', QMessageBox.ButtonRole.AcceptRole)
        mine_btn = msg_box.addButton('我的网盘', QMessageBox.ButtonRole.RejectRole)
        cancel_btn = msg_box.addButton('取消', QMessageBox.ButtonRole.DestructiveRole)
        
        msg_box.setDefaultButton(shared_btn)
        msg_box.exec()
        
        clicked_button = msg_box.clickedButton()
        if clicked_button == cancel_btn:
                return
        elif clicked_button == shared_btn:
            target = QMessageBox.StandardButton.Yes
        else:  # mine_btn
            target = QMessageBox.StandardButton.No
        
        # 初始化进度条
        self.progress_bar.value = 0
        self.progress_bar.show()
        self.status_label.setText('正在准备上传…')
        
        # 确定目标类型
        target_type = 'shared' if target == QMessageBox.StandardButton.Yes else 'mine'
        
        # 创建异步上传工作线程
        self.upload_thread = QThread()
        self.upload_worker = UploadWorker(self.client, file_paths, target_type, self.current_folder)
        self.upload_worker.moveToThread(self.upload_thread)
        
        # 连接信号
        self.upload_thread.started.connect(self.upload_worker.run)
        self.upload_worker.progress_updated.connect(self._on_upload_progress)
        self.upload_worker.upload_finished.connect(self._on_upload_finished)
        self.upload_worker.error_occurred.connect(self._on_upload_error)
        self.upload_thread.finished.connect(self.upload_thread.deleteLater)
        
        # 启动上传线程
        self.upload_thread.start()
    
    def _on_upload_progress(self, percent, filename):
        """处理上传进度更新"""
        self.progress_bar.value = percent
        self.status_label.setText(f'{filename} ({percent}%)')
    
    def _on_upload_finished(self, result):
        """处理上传完成"""
        success = result['success']
        failed = result['failed']
        total = result['total']
        results = result['results']
        cancelled = result['cancelled']
        
        # 隐藏进度条
        self.progress_bar.hide()

        if cancelled:
            self.status_label.setText('上传已取消')
            return
        
        # 显示结果
        if failed == 0 and success > 0:
            tip = f'上传成功：{success}/{total}'
            QMessageBox.information(self, '上传完成', tip)
            self.status_label.setText(tip)
        else:
            detail = '\n'.join([f"{r.get('filename')}: {r.get('error')}" for r in results if not r.get('ok')][:5])
            tip = f'部分失败：成功 {success}，失败 {failed}' + (f"\n{detail}" if detail else '')
            QMessageBox.warning(self, '上传结果', tip)
            self.status_label.setText(tip)
        
        # 刷新当前目录
        self.load_dir(self.current_folder)
        
        # 清理线程
        self.upload_thread.quit()
        self.upload_thread.wait()
    
    def _on_upload_error(self, error_msg):
        """处理上传错误"""
        self.progress_bar.hide()
        QMessageBox.warning(self, '上传失败', f'上传失败：{error_msg}')
        self.status_label.setText(f'上传失败：{error_msg}')
        
        # 清理线程
        self.upload_thread.quit()
        self.upload_thread.wait()
        
    def search_files(self):
        """搜索文件：清空当前列表，在列表区域并发加载两个来源结果并上色标记。"""
        keyword = self.search_input.text().strip()
        if not keyword:
            return
            
        # 清空旧表格并设置表头
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["名称", "类型", "大小", "更新时间", "来源", "阅读", "下载", "分享", "其它"])
        self.file_tree.setModel(self.model)
        for i in range(self.model.columnCount()):
            item = self.model.horizontalHeaderItem(i)
            if item is not None:
                if i == 0:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
        self.status_label.setText(f"正在搜索：{keyword} …")
        self.progress_bar.show()
            
        # 启动并发搜索线程
        self._start_search_threads(keyword)

    # ---------------- 搜索内部实现 ----------------
    def _start_search_threads(self, keyword: str) -> None:
        """并行启动服务器与缓存搜索线程。"""
        # 记录结果
        self._search_results_server = None
        self._search_results_cache = None

        # 服务器搜索线程
        class _ServerThread(QThread):
            done = Signal(dict)
            fail = Signal(str)
            def __init__(self, client, kw: str):
                super().__init__()
                self.client, self.kw = client, kw
            def run(self):
                try:
                    res = self.client.search_server(self.kw, dir_path='/', recursion=1, page=1, num=200)
                    self.done.emit(res)
                except Exception as e:
                    self.fail.emit(str(e))
        
        # 缓存搜索线程
        class _CacheThread(QThread):
            done = Signal(dict)
            fail = Signal(str)
            def __init__(self, client, kw: str):
                super().__init__()
                self.client, self.kw = client, kw
            def run(self):
                try:
                    res = self.client.search_cache(self.kw, path='/', limit=800)
                    self.done.emit(res)
                except Exception as e:
                    self.fail.emit(str(e))
        
        self._th_server = _ServerThread(self.client, keyword)
        self._th_cache = _CacheThread(self.client, keyword)
        
        self._th_server.done.connect(self._on_server_search_ok)
        self._th_server.fail.connect(self._on_search_fail)
        self._th_cache.done.connect(self._on_cache_search_ok)
        self._th_cache.fail.connect(self._on_search_fail)
        
        self._th_server.start()
        self._th_cache.start()

    def _on_server_search_ok(self, data: dict) -> None:
        self._search_results_server = data or {}
        self._try_render_search_results()

    def _on_cache_search_ok(self, data: dict) -> None:
        self._search_results_cache = data or {}
        self._try_render_search_results()

    def _on_search_fail(self, msg: str) -> None:
        # 显示但不中断另一侧
        QMessageBox.information(self, "搜索提示", f"有一侧搜索失败：{msg}")
        self._try_render_search_results()

    def _try_render_search_results(self) -> None:
        """当两侧任一返回后就可增量渲染；两侧都返回后更新状态栏。"""
        # 增量渲染：已渲染的来源做标记
        if getattr(self, '_rendered_server', False) is False and self._search_results_server is not None:
            self._append_search_source(self._search_results_server, source='server')
            self._rendered_server = True
        if getattr(self, '_rendered_cache', False) is False and self._search_results_cache is not None:
            self._append_search_source(self._search_results_cache, source='cache')
            self._rendered_cache = True
        
        # 如果两侧都完成，更新状态与进度
        if (self._search_results_server is not None) and (self._search_results_cache is not None):
            self.progress_bar.hide()
            total_server = len((self._search_results_server or {}).get('list', []) or [])
            total_cache = len((self._search_results_cache or {}).get('files', []) or [])
            self.status_label.setText(f"搜索完成 - 网盘资源: {total_server}，共享资源: {total_cache}")
            # 重置标记，便于下一次搜索
            self._rendered_server = False
            self._rendered_cache = False

    def _append_search_source(self, data: dict, *, source: str) -> None:
        """把某一来源的结果追加到表格。"""
        if source == 'server':
            # server 源：直接调用 /search，代表“客户网盘里的资源”
            items = data.get('list', []) if isinstance(data, dict) else []
            bg = QColor(230, 244, 255)  # 浅蓝
            src_text = '网盘资源'
        else:
            # cache 源：来自 /cache/files（后端共享资源缓存）
            items = data.get('files', []) if isinstance(data, dict) else []
            bg = QColor(230, 255, 230)  # 浅绿
            src_text = '共享资源'
        
        for file in items:
            filename = file.get('server_filename') or file.get('name') or file.get('path') or '未命名'
            size_val = file.get('size') or file.get('filesize') or 0
            category = file.get('category') or 0
            
            # 设置文件来源标记，用于右键菜单判断
            file['__source'] = source
            
            name_item = QStandardItem(QIcon(get_icon_path(self.get_file_icon(file))), filename)
            name_item.setData(file, Qt.UserRole)
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            type_item = QStandardItem(self.map_kind_to_type((file.get('kind') or '').lower(), filename, category, False))
            type_item.setTextAlignment(Qt.AlignCenter)
            size_item = QStandardItem(self.format_size(size_val))
            size_item.setTextAlignment(Qt.AlignCenter)
            updated_item = QStandardItem(self.format_updated_at(file))
            updated_item.setTextAlignment(Qt.AlignCenter)
            source_item = QStandardItem(src_text)
            source_item.setTextAlignment(Qt.AlignCenter)
            
            for it in (name_item, type_item, size_item, updated_item, source_item):
                it.setBackground(bg)
            
            # 操作列占位（保持现有表头结构）
            read_item = QStandardItem("阅读")
            read_item.setTextAlignment(Qt.AlignCenter)
            read_item.setForeground(QColor("#2E7D32"))
            download_item = QStandardItem("下载")
            download_item.setTextAlignment(Qt.AlignCenter)
            download_item.setForeground(QColor("#1976D2"))
            share_item = QStandardItem("分享")
            share_item.setTextAlignment(Qt.AlignCenter)
            share_item.setForeground(QColor("#F57C00"))
            other_item = QStandardItem("其它")
            other_item.setTextAlignment(Qt.AlignCenter)
            other_item.setForeground(QColor("#616161"))
            
            self.model.appendRow([name_item, type_item, size_item, updated_item, source_item, read_item, download_item, share_item, other_item])
        
        # 刷新显示
        self.file_tree.viewport().update()

    def show_my_info(self):
        """优先检测是否已登录；未登录才弹出扫码。若已登录但无法取到信息，也不强制弹扫码。"""
        try:
            from pan_client.core.token import get_access_token, list_accounts
            token = get_access_token()
            if token:
                # 尝试获取用户信息验证 token 是否可用
                info = None
                try:
                    # 确保当前会话头包含 token，并取回用户信息
                    if hasattr(self.client, 'set_local_access_token'):
                        self.client.set_local_access_token(token)
                    else:
                        self.api.set_local_access_token(token)
                    info = self.client.get_userinfo()
                    # 将用户信息写回本地账户，便于切换列表显示昵称
                    if info:
                        if hasattr(self.client, 'set_local_access_token'):
                            self.client.set_local_access_token(token, user=info)
                        else:
                            self.api.set_local_access_token(token, user=info)
                except Exception:
                    info = None
                if info:
                    # 已登录，展示个人信息对话框
                    try:
                        # 显示账号信息，后续可在对话框内加入账号切换入口
                        dlg = UserInfoDialog(info, self)
                        dlg.exec()
                        return
                    except Exception:
                        # 即使展示失败，也继续走登录逻辑
                        pass
                # 有 token 但未取到 info：认为已登录但后端信息不可用，不弹出扫码
                try:
                    from pan_client.core.token import list_accounts as _list
                    accts = _list()
                    if isinstance(accts, list) and len(accts) > 1:
                        # 提供一个简单的切换入口
                        from PySide6.QtWidgets import QInputDialog
                        items = [f"{a.get('name')} ({a.get('id')})" + (" [当前]" if a.get('is_current') else "") for a in accts]
                        sel, ok = QInputDialog.getItem(self, "切换账号", "选择一个账号：", items, 0, False)
                        if ok:
                            idx = items.index(sel)
                            target_id = accts[idx].get('id')
                            if target_id:
                                if hasattr(self.client, 'switch_account') and self.client.switch_account(target_id):
                                    # 切换后刷新
                                    t_sw = self.api._session.headers.get('Authorization')
                                    if t_sw:
                                        self.load_dir(self.current_folder)
                                        QMessageBox.information(self, "提示", f"已切换到账号：{accts[idx].get('name')}")
                                        return
                except Exception:
                    pass
                QMessageBox.information(self, "提示", "当前已登录。")
                return
        except Exception:
            pass

        # 未登录或 token 失效：弹出扫码对话框
        from pan_client.ui.login_dialog import LoginDialog
        dlg = LoginDialog(self.client, self.mcp_session, self)
        if dlg.exec() == QDialog.Accepted:
            # 刷新会话鉴权头与文件列表
            try:
                from pan_client.core.token import get_access_token as _ga
                t2 = _ga()
                if t2:
                    if hasattr(self.client, 'set_local_access_token'):
                        self.client.set_local_access_token(t2)
                    else:
                        self.api.set_local_access_token(t2)
                self.load_dir(self.current_folder)
                self.status_label.setText("登录成功，已刷新列表")
            except Exception:
                pass
    

    # 旧的 show_context_menu 已废弃，右键菜单由 _on_tree_context_menu 实现
    
    def check_scroll_position(self, value):
        """检查滚动位置，用于触发加载更多"""
        # 简化版本，仅保留UI逻辑
        pass
    
    def load_more_files(self):
        """加载更多文件"""
        QMessageBox.information(self, "加载更多", "加载更多功能已移除业务逻辑，仅保留界面。")

    def download_selected_files(self):
        """下载选中的文件"""
        QMessageBox.information(self, "批量下载", "批量下载功能已移除业务逻辑，仅保留界面。")

    def check_version(self):
        """检查版本更新"""
        QMessageBox.information(self, '版本检查', '版本检查功能已移除业务逻辑，仅保留界面。')

    def format_size(self, size_bytes):
        """格式化文件大小显示"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def map_kind_to_type(self, kind: str, filename: str, category: int, is_dir: bool = False) -> str:
        """更稳健的类型映射。
        - 目录优先显示为 文件夹
        - 对包含特殊字符/不规范的 kind 回退到扩展名
        - 若扩展名也无法判断，则根据分类兜底
        """
        if is_dir:
            return "文件夹"
        norm = (kind or "").strip().lower()
        # 不规范的 kind（包含分隔符或空格）直接忽略
        if "/" in norm or " " in norm:
            norm = ""
        # 常见 kind 直接返回
        if norm in {"video","audio","image","pdf","doc","docx","xls","xlsx","ppt","pptx"}:
            return norm
        # 扩展名判断
        ext = os.path.splitext((filename or "").lower())[1]
        if ext in (".mp4",".mov",".mkv",".avi",".flv",".wmv",".m4v"):
            return "video"
        if ext in (".mp3",".flac",".wav",".aac",".m4a"):
            return "audio"
        if ext in (".jpg",".jpeg",".png",".gif",".bmp",".webp"):
            return "image"
        if ext == ".pdf":
            return "pdf"
        if ext in (".doc",".docx"):
            return "docx" if ext == ".docx" else "doc"
        if ext in (".xls",".xlsx"):
            return "xlsx" if ext == ".xlsx" else "xls"
        if ext in (".ppt",".pptx"):
            return "pptx" if ext == ".pptx" else "ppt"
        # 分类兜底
        return self.map_category_to_type(category)

    def adjust_column_widths(self):
        """根据视图模式按比例调整列宽。"""
        if not self.model:
            return
        total = max(1, self.file_tree.viewport().width())
        # 扣除垂直滚动条宽度（出现时会压缩可视区域，导致超宽）
        vbar = self.file_tree.verticalScrollBar()
        if vbar and vbar.isVisible():
            total = max(1, total - vbar.sizeHint().width())
        # 两种视图统一比例：名称, 类型, 大小, 更新时间, 阅读, 下载, 分享, 其它
        ratios = [0.52, 0.06, 0.08, 0.12, 0.06, 0.06, 0.06, 0.04]
        cols = min(len(ratios), self.model.columnCount())
        assigned = 0
        for i in range(cols - 1):
            w = int(total * ratios[i])
            self.file_tree.setColumnWidth(i, w)
            assigned += w
        # 最后一列占据剩余，避免舍入误差
        self.file_tree.setColumnWidth(cols - 1, max(10, total - assigned - 1))
        # 再次延迟微调一次，确保布局完成（避免首次进入目录时出现水平滚动条）
        try:
            QTimer.singleShot(0, lambda: self._post_adjust_columns())
        except Exception:
            pass

    def _post_adjust_columns(self):
        try:
            total = max(1, self.file_tree.viewport().width())
            vbar = self.file_tree.verticalScrollBar()
            if vbar and vbar.isVisible():
                total = max(1, total - vbar.sizeHint().width())
            cols = self.model.columnCount()
            if cols <= 0:
                return
            current = sum(self.file_tree.columnWidth(i) for i in range(cols - 1))
            self.file_tree.setColumnWidth(cols - 1, max(10, total - current - 1))
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if obj is self.file_tree and event.type() == QEvent.Resize:
            self.adjust_column_widths()
        return super().eventFilter(obj, event)

    # ============== 下载相关 ==============
    def on_item_double_clicked(self, index):
        """双击进入下一级目录（当目标为目录）。"""
        try:
            if not index.isValid():
                return
            # 总是取名称列的数据
            name_index = index.sibling(index.row(), 0)
            item = self.model.itemFromIndex(name_index)
            file = item.data(Qt.UserRole) if item else None
            if not isinstance(file, dict):
                return
            is_dir = bool(file.get('is_dir') or file.get('isdir') or 0)
            if not is_dir:
                return
            next_path = file.get('path') or file.get('name') or file.get('server_filename')
            if not next_path:
                return
            self.current_folder = next_path
            self.load_dir(self.current_folder)
        except Exception:
            pass

    def on_tree_clicked(self, index):
        try:
            if not index.isValid():
                return
            col = index.column()
            # 下载列点击
            header_text = self.model.headerData(col, Qt.Horizontal)
            if str(header_text) == '下载':
                row = index.row()
                file_info = self.model.item(row, 0).data(Qt.UserRole)
                if file_info and not (file_info.get('is_dir') or file_info.get('isdir')):
                    self._download_single(file_info)
            # 阅读列点击
            if str(header_text) == '阅读':
                row = index.row()
                file_info = self.model.item(row, 0).data(Qt.UserRole)
                if file_info and not (file_info.get('is_dir') or file_info.get('isdir')):
                    self._read_single(file_info)
        except Exception as e:
            QMessageBox.warning(self, '下载失败', str(e))

    def _download_single(self, file_info):
        """根据来源获取直链并保存文件。"""
        fsid = file_info.get('fs_id') or file_info.get('fsid')
        if not fsid:
            raise Exception('缺少 fsid')
        save_name = (file_info.get('server_filename') or file_info.get('name') or 'download')
        # 选择保存路径
        save_dir = QFileDialog.getExistingDirectory(self, '选择保存目录')
        if not save_dir:
            return
        import requests, os
        self.status_label.setText('正在获取下载链接…')
        target_path = os.path.join(save_dir, save_name)
        self.progress_bar.value = 0
        self.progress_bar.show()
        self.status_label.setText(f'正在下载：{save_name}')
        # 通过后端代理流式下载，规避403
        r = self.client.stream_file(int(fsid))
        total = int(r.headers.get('Content-Length') or 0)
        downloaded = 0
        with open(target_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                f.write(chunk)
                if total:
                    downloaded += len(chunk)
                    percent = int(downloaded * 100 / total)
                    self.progress_bar.value = percent
        self.progress_bar.hide()
        self.status_label.setText(f'下载完成：{save_name}')
        QMessageBox.information(self, '下载完成', f'已保存到：\n{target_path}')

    def _download_multiple(self, file_list):
        """批量下载文件"""
        if not file_list:
            return
        
        # 选择保存目录
        save_dir = QFileDialog.getExistingDirectory(self, '选择保存目录')
        if not save_dir:
            return
        
        # 初始化进度条
        self.progress_bar.value = 0
        self.progress_bar.show()
        self.status_label.setText(f'开始批量下载 {len(file_list)} 个文件...')
        
        # 创建异步下载工作线程
        self.download_thread = QThread()
        self.download_worker = DownloadWorker(self.client, file_list, save_dir)
        self.download_worker.moveToThread(self.download_thread)
        
        # 连接信号
        self.download_thread.started.connect(self.download_worker.run)
        self.download_worker.progress_updated.connect(self._on_download_progress)
        self.download_worker.download_finished.connect(self._on_download_finished)
        self.download_worker.error_occurred.connect(self._on_download_error)
        self.download_thread.finished.connect(self.download_thread.deleteLater)
        
        # 启动下载线程
        self.download_thread.start()
    
    def _on_download_progress(self, percent, filename):
        """处理下载进度更新"""
        self.progress_bar.value = percent
        self.status_label.setText(f'{filename} ({percent}%)')
    
    def _on_download_finished(self, result):
        """处理下载完成"""
        success = result['success']
        failed = result['failed']
        total = result['total']
        results = result['results']
        cancelled = result['cancelled']
        
        # 隐藏进度条
        self.progress_bar.hide()
        
        if cancelled:
            self.status_label.setText('下载已取消')
            return
        
        # 显示结果
        if success > 0:
            QMessageBox.information(self, '批量下载完成', 
                f'成功下载 {success}/{total} 个文件')
            self.status_label.setText(f'下载完成：{success}/{total} 个文件')
        else:
            QMessageBox.warning(self, '下载失败', '没有文件下载成功')
            self.status_label.setText('下载失败')
        
        # 清理线程
        self.download_thread.quit()
        self.download_thread.wait()
    
    def _on_download_error(self, error_msg):
        """处理下载错误"""
        self.progress_bar.hide()
        QMessageBox.warning(self, '下载失败', f'下载失败：{error_msg}')
        self.status_label.setText(f'下载失败：{error_msg}')
        
        # 清理线程
        self.download_thread.quit()
        self.download_thread.wait()

    def _read_single(self, file_info):
        """后台拉取到临时目录后再打开阅读器，避免阻塞UI。"""
        name = (file_info.get('server_filename') or file_info.get('name') or 'document')
        lower = name.lower()
        supported_ext = ('.pdf', '.txt', '.log', '.md', '.json', '.csv', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        if not any(lower.endswith(ext) for ext in supported_ext):
            QMessageBox.information(self, '不支持的格式', '该文件类型暂不支持在线阅读，请下载后使用本地应用打开。')
            return
        # 启动读取线程
        try:
            self.read_thread = QThread(self)
            self.read_worker = SingleReadWorker(self.client, file_info)
            self.read_worker.moveToThread(self.read_thread)
            self.read_thread.started.connect(self.read_worker.run)
            self.read_worker.progress_updated.connect(self._on_read_progress)
            self.read_worker.read_finished.connect(self._on_read_finished)
            self.read_worker.error_occurred.connect(self._on_read_error)
            self.read_worker.finished.connect(self.read_thread.quit)
            self.read_worker.finished.connect(self.read_worker.deleteLater)
            self.read_thread.finished.connect(self.read_thread.deleteLater)
            # UI 初始状态
            self.progress_bar.value = 0
            self.progress_bar.show()
            self.status_label.setText(f'正在加载文档：{name}')
            self.read_thread.start()
        except Exception as e:
            QMessageBox.warning(self, '打开失败', f'无法启动读取任务：{e}')

    def _on_read_progress(self, percent, text):
        try:
            self.progress_bar.value = max(0, min(100, int(percent)))
            self.status_label.setText(text)
        except Exception:
            pass

    def _on_read_finished(self, result):
        try:
            self.progress_bar.hide()
            if isinstance(result, dict) and result.get('ok'):
                local_path = result.get('path')
                name = result.get('name')
                dlg = DocumentViewer(local_path, name, self)
                dlg.exec()
            else:
                msg = result.get('error', '未知错误') if isinstance(result, dict) else '未知错误'
                QMessageBox.warning(self, '打开失败', f'读取失败：{msg}')
        except Exception:
            pass

    def _on_read_error(self, error_msg):
        try:
            self.progress_bar.hide()
            QMessageBox.warning(self, '打开失败', f'读取失败：{error_msg}')
        except Exception:
            pass

    def show_about(self):
        """显示关于信息"""
        about_text = (
            "云栈-您身边的共享资料库 V1.0.1\n\n"
            "这是一个简化版的界面演示程序，已移除所有业务逻辑。\n"
            "© 2023 云栈团队 保留所有权利。"
        )
        QMessageBox.about(self, "关于云栈", about_text)

    def bootstrap_and_load(self):
        """启动默认加载共享资源，不做登录检查。"""
        try:
            self.view_mode = 'shared'
            self.load_dir(self.current_folder)
            self.status_label.setText("已加载（共享资源）：/")
        except Exception as e:
            QMessageBox.warning(self, "初始化失败", str(e))

    # 旧浏览器打开二维码登录逻辑已移除，统一使用扫码登录对话框
    
    def display_files(self, files, append=False):
        """显示文件列表（真实数据）"""
        try:
            # 如果不是追加模式且当前有行，则先清空
            if not append and self.model.rowCount() > 0:
                self.model.removeRows(0, self.model.rowCount())
            
            # 添加每个文件项
            for file in files:
                filename = file.get("server_filename") or file.get("name") or ""
                size_val = file.get("size") or file.get("filesize") or 0
                fsid = file.get("fs_id") or file.get("fsid") or ""
                category = file.get("category") or 0
                is_dir = bool(file.get("is_dir") or file.get("isdir") or 0)

                # 创建名称列
                name_item = QStandardItem(QIcon(get_icon_path(self.get_file_icon(file))), filename)
                name_item.setData(file, Qt.UserRole)
                name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                
                # 标记来源：mine/shared
                if getattr(self, 'view_mode', 'mine') == 'shared':
                    file['__source'] = 'shared'
                else:
                    file['__source'] = 'mine'
                
                # 创建其他列
                type_item = QStandardItem(self.map_kind_to_type((file.get("kind") or "").lower(), filename, category, is_dir))
                type_item.setTextAlignment(Qt.AlignCenter)
                size_item = QStandardItem(self.format_size(size_val))
                size_item.setTextAlignment(Qt.AlignCenter)
                updated_item = QStandardItem(self.format_updated_at(file))
                updated_item.setTextAlignment(Qt.AlignCenter)
 
                # 共享视图增加操作列
                if getattr(self, 'view_mode', 'mine') == 'shared':
                    read_item = QStandardItem("阅读")
                    read_item.setTextAlignment(Qt.AlignCenter)
                    read_item.setForeground(QColor("#2E7D32"))  # 绿色，强调可读
                    read_item.setData('read', Qt.UserRole + 1)
                    download_item = QStandardItem("下载")
                    download_item.setTextAlignment(Qt.AlignCenter)
                    download_item.setForeground(QColor("#1976D2"))  # 主色蓝，呼应整体主题
                    # 点击下载
                    download_item.setData('download', Qt.UserRole + 1)
                    share_item = QStandardItem("分享")
                    share_item.setTextAlignment(Qt.AlignCenter)
                    share_item.setForeground(QColor("#F57C00"))  # 橙色，强调交互
                    other_item = QStandardItem("其它")
                    other_item.setTextAlignment(Qt.AlignCenter)
                    other_item.setForeground(QColor("#616161"))  # 中性灰
                    self.model.appendRow([name_item, type_item, size_item, updated_item, read_item, download_item, share_item, other_item])
                else:
                    # 首页与共享尽量一致，补齐操作列（可为空或占位）
                    read_item = QStandardItem("阅读" if not is_dir else "")
                    read_item.setTextAlignment(Qt.AlignCenter)
                    read_item.setForeground(QColor("#2E7D32"))
                    read_item.setData('read', Qt.UserRole + 1)
                    download_item = QStandardItem("下载" if not is_dir else "")
                    download_item.setTextAlignment(Qt.AlignCenter)
                    download_item.setForeground(QColor("#1976D2"))
                    download_item.setData('download', Qt.UserRole + 1)
                    share_item = QStandardItem("分享" if not is_dir else "")
                    share_item.setTextAlignment(Qt.AlignCenter)
                    share_item.setForeground(QColor("#F57C00"))
                    other_item = QStandardItem("其它")
                    other_item.setTextAlignment(Qt.AlignCenter)
                    other_item.setForeground(QColor("#616161"))
                    self.model.appendRow([name_item, type_item, size_item, updated_item, read_item, download_item, share_item, other_item])
                
            # 更新界面状态
            if not append:
                # 滚动到顶部
                self.file_tree.scrollToTop()
                self.adjust_column_widths()
            
        except Exception as e:
            QMessageBox.warning(
                self, 
                "显示文件失败", 
                f"显示文件失败: {str(e)}"
            )

    def load_dir(self, dir_path: str):
        """从后端加载目录内容。"""
        try:
            # 如果模型不存在，创建一个新的标准项模型
            if not hasattr(self, 'model') or self.model is None:
                self.model = QStandardItemModel()
                # 两种视图尽量统一列头
                self.model.setHorizontalHeaderLabels(["名称", "类型", "大小", "更新时间", "阅读", "下载", "分享", "其它"])
                self.file_tree.setModel(self.model)
            else:
                # 清空现有模型的内容，而不是创建新模型
                self.model.clear()
                self.model.setHorizontalHeaderLabels(["名称", "类型", "大小", "更新时间", "阅读", "下载", "分享", "其它"])

            # 表头对齐：名称列左，其余列居中
            for i in range(self.model.columnCount()):
                item = self.model.horizontalHeaderItem(i)
                if item is not None:
                    if i == 0:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignCenter)
 
            # 列宽：按比例
            header = self.file_tree.header()
            header.setStretchLastSection(False)
            from PySide6.QtWidgets import QHeaderView
            header.setSectionResizeMode(QHeaderView.Fixed)
            header.setMinimumSectionSize(10)
 
            if self.view_mode == 'mine':
                # 没有本地token则先要求登录，并清除内存鉴权头
                try:
                    from pan_client.core.token import get_access_token
                    token = get_access_token()
                    if not token:
                        try:
                            self.api.clear_local_access_token()
                        except Exception:
                            pass
                        from pan_client.ui.login_dialog import LoginDialog
                        dlg = LoginDialog(self.client, self.mcp_session, self)
                        if dlg.exec() == QDialog.Accepted:
                            from pan_client.core.token import get_access_token as _ga
                            t2 = _ga()
                            if t2:
                                if hasattr(self.client, 'set_local_access_token'):
                                    self.client.set_local_access_token(t2)
                                else:
                                    self.api.set_local_access_token(t2)
                            else:
                                raise RuntimeError('用户未登录')
                except Exception:
                    pass
                # 仅个人网盘
                data_user = self.client.list_files(dir_path=dir_path, limit=200, order='time', desc=1)
                user_files = data_user.get('list', []) if isinstance(data_user, dict) else []
                self.display_files(user_files)
                self.status_label.setText(f"已加载（我的网盘）：{dir_path}")
            elif self.view_mode == 'shared':
                # 仅服务器缓存
                data_cache = self.client.get_cached_files(path=dir_path, limit=200, offset=0)
                cache_files = data_cache.get('files', []) if isinstance(data_cache, dict) else []
                self.display_files(cache_files)
                self.status_label.setText(f"已加载（共享资源）：{dir_path}")
            else:
                # 兼容：合并模式
                data_user = self.client.list_files(dir_path=dir_path, limit=200, order='time', desc=1)
                user_files = data_user.get('list', []) if isinstance(data_user, dict) else []
                data_cache = self.client.get_cached_files(path=dir_path, limit=200, offset=0)
                cache_files = data_cache.get('files', []) if isinstance(data_cache, dict) else []
                merged = []
                seen_keys = set()
                def make_key(it):
                    return (it.get('fs_id') or it.get('fsid') or None) or (it.get('path') or it.get('server_filename'))
                for it in user_files + cache_files:
                    k = make_key(it)
                    if k in seen_keys:
                        continue
                    seen_keys.add(k)
                    merged.append(it)
                self.display_files(merged)
                self.status_label.setText(f"已加载：{dir_path}")

            self.adjust_column_widths()
        except Exception as e:
            # 401 等鉴权失败时，触发重新登录
            err_text = str(e)
            if '401' in err_text or 'Unauthorized' in err_text or 'authorization' in err_text.lower():
                try:
                    from pan_client.core.token import clear_token
                    clear_token()
                except Exception:
                    pass
                # 弹出登录框
                try:
                    dlg = LoginDialog(self.client, self.mcp_session, self)
                    if dlg.exec() == QDialog.Accepted:
                        # 登录成功后重试
                        try:
                            from pan_client.core.token import get_access_token
                            token = get_access_token()
                            if token:
                                # 更新现有客户端的鉴权头
                                if hasattr(self.client, 'set_local_access_token'):
                                    self.client.set_local_access_token(token)
                                else:
                                    self.api.set_local_access_token(token)
                            self.view_mode = 'mine'
                            self.load_dir(dir_path)
                            return
                        except Exception:
                            pass
                except Exception:
                    pass
            QMessageBox.warning(self, "加载失败", f"加载目录失败: {err_text}")
    
    def get_file_icon(self, file_info):
        """根据 kind/扩展名/分类 返回图标名称（优先 kind）。"""
        kind = (file_info.get("kind") or "").lower()
        category = file_info.get("category", 0)
        filename = (file_info.get("server_filename") or "").lower()
        
        if kind in ("mp4","mov","mkv","avi","flv","wmv","m4v","video") or category == 1:
            return "video.png"
        if kind in ("mp3","flac","wav","aac","m4a","audio") or category == 2:
            return "audio.png"
        if kind in ("jpg","jpeg","png","gif","bmp","webp","image") or category == 3:
            return "image.png"
        if kind in ("pdf","doc","docx","ppt","pptx","xls","xlsx","sheet","document") or category == 4:
            if kind == "pdf" or filename.endswith(".pdf"):
                return "pdf.png"
            if kind in ("doc","docx") or filename.endswith((".doc",".docx")):
                return "word.png"
            if kind in ("xls","xlsx") or filename.endswith((".xls",".xlsx")):
                return "excel.png"
            if kind in ("ppt","pptx") or filename.endswith((".ppt",".pptx")):
                return "ppt.png"
            return "document.png"
        
        # 默认返回文件图标
        return "file.png"
    
    def format_size(self, size_bytes):
        """格式化文件大小为人类可读格式"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def map_category_to_type(self, category):
        """映射分类ID到文件类型名称"""
        categories = {
            1: "视频",
            2: "音频",
            3: "图片",
            4: "文档",
            5: "应用",
            6: "其他",
            7: "种子"
        }
        return categories.get(category, "未知")

    def format_updated_at(self, file: dict) -> str:
        """格式化更新时间，优先使用 updated_at，否则使用 mtime/server_mtime/local_mtime。"""
        val = file.get('updated_at')
        if val:
            return str(val)
        # 尝试从时间戳转换
        ts = file.get('server_mtime') or file.get('local_mtime') or file.get('mtime')
        try:
            if isinstance(ts, (int, float)) and ts > 0:
                from datetime import datetime
                return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        return ""

    def download_file(self, file_info):
        """下载文件"""
        QMessageBox.information(self, "下载文件", "下载功能已移除业务逻辑，仅保留界面。")

    def update_upload_progress(self, status, value):
        """更新上传进度"""
        pass

    def update_progress(self, message, percent):
        """更新进度对话框"""
        if hasattr(self, 'loading_dialog'):
            self.loading_dialog.update_status(message, percent)
        
    def upload_finished(self, success, message, failed_files):
        """上传完成的处理"""
        pass

    def check_scroll_position(self, value):
        """检查滚动位置，到底时加载更多"""
        scrollbar = self.file_tree.verticalScrollBar()
        # 当滚动到底部且不在加载状态且还有更多数据时
        if (value == scrollbar.maximum() and 
            not self.is_loading and 
            self.has_more):
            self.load_more_files()
        elif value == scrollbar.maximum() and not self.has_more:
            # 当滚动到底部但没有更多数据时显示提示
            self.status_label.setText("已加载全部文件")

    def load_more_files(self):
        """加载更多文件"""
        self.is_loading = True
        self.status_label.setText("正在加载更多文件...")
        self.current_page += 1
        
        try:
            # 构造请求参数
            params = {
                'method': 'list',
                'access_token': self.access_token,
                'dir': self.current_folder,
                'order': 'time',
                'desc': 1,
                'start': (self.current_page - 1) * self.page_size,
                'limit': self.page_size
            }
            
            # 调用百度网盘API
            response = requests.get(
                'https://pan.baidu.com/rest/2.0/xpan/file',
                params=params
            )
            
            result = response.json()
            if result.get('errno') == 0:
                files = result.get('list', [])
                
                # 如果返回的文件数小于页大小，说明没有更多数据了
                if len(files) < self.page_size:
                    self.has_more = False
                    self.status_label.setText("已加载全部文件")
                
                # 添加新的文件到列表
                if files:
                    self.display_files(files, append=True)
                    if self.has_more:
                        self.status_label.setText(f"已加载第 {self.current_page} 页")
                else:
                    self.has_more = False
                    self.status_label.setText("已加载全部文件")
            else:
                self.status_label.setText(f"加载失败：错误码 {result.get('errno')}")
                
        except Exception as e:
            self.status_label.setText(f"加载失败：{str(e)}")
        finally:
            self.is_loading = False

    def download_selected_files(self):
        """批量下载选择的文件"""
        if not self.is_vip:
            QMessageBox.warning(self, "提示", "批量下载功能仅对VIP用户开放")
            return

        # 检查是否有正在进行的下载任务
        if (self.download_worker and self.download_worker.isRunning()) or \
           (hasattr(self, 'batch_download_worker') and self.batch_download_worker and self.batch_download_worker.isRunning()):
            QMessageBox.warning(self, "提示", "有正在进行的下载任务，请等待当前下载完成。")
            return

        # 获取所有选中的项目
        selected_indexes = self.file_tree.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "提示", "请先选择要下载的文件")
            return

        # 获取保存目录
        save_dir = QFileDialog.getExistingDirectory(
            self,
            "选择保存目录",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if not save_dir:
            return

        try:
            # 创建下载队列
            download_queue = []
            for index in selected_indexes:
                file_info = self.model.item(index.row(), 0).data(Qt.UserRole)
                if file_info:
                    fs_id = file_info.get('fs_id')
                    file_name = file_info.get('server_filename') or file_info.get('name') or 'unknown_file'
                    if fs_id and file_name:
                        save_path = os.path.join(save_dir, file_name)
                        download_queue.append((fs_id, save_path, file_name))

            if not download_queue:
                return

            # 显示进度条
            self.progress_bar.show()
            self.status_label.setText(f"准备下载 {len(download_queue)} 个文件...")

            # 创建批量下载线程
            self.batch_download_worker = BatchDownloadWorker(
                self.access_token,
                download_queue
            )
            self.batch_download_worker.progress.connect(self.update_batch_download_progress)
            self.batch_download_worker.finished.connect(self.batch_download_finished)
            self.batch_download_worker.start()

        except Exception as e:
            self.status_label.setText(f"批量下载失败: {str(e)}")
            self.progress_bar.hide()

    def update_batch_download_progress(self, current, total, file_name):
        """更新批量下载进度"""
        pass

    def batch_download_finished(self):
        """批量下载完成"""
        pass

    def pay_once_download(self, file_info):
        """单次付费下载"""
        QMessageBox.information(self, "付费下载", "付费下载功能已移除业务逻辑，仅保留界面。")

    def start_actual_download(self, file_info):
        """实际开始下载文件（付费下载后调用）"""
        QMessageBox.information(self, "下载", "下载功能已移除业务逻辑，仅保留界面。")

    def check_vip_status(self):
        """检查用户VIP状态（本地）"""
        pass
        
    def set_vip_status(self, is_vip: bool):
        """设置用户VIP状态（本地）"""
        self.is_vip = is_vip
        # 更新文件树的选择模式
        if is_vip:
            self.file_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        else:
            self.file_tree.setSelectionMode(QAbstractItemView.SingleSelection)

    def start_download(self, file_info):
        """开始下载文件"""
        QMessageBox.information(self, "下载", "下载功能已移除业务逻辑，仅保留界面。")

    def on_download_finished(self, success, file_name):
        """处理下载完成的逻辑"""
        QMessageBox.information(self, "下载完成", "下载功能已移除业务逻辑，仅保留界面。")

    def share_file(self, file_info):
        """分享文件信息"""
        QMessageBox.information(self, "分享", "分享功能已移除业务逻辑，仅保留界面。")

    def show_report_dialog(self, file_info):
        """显示举报对话框"""
        QMessageBox.information(self, "举报", "举报功能已移除业务逻辑，仅保留界面。")

    def _on_tree_context_menu(self, pos):
        index = self.file_tree.indexAt(pos)
        
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        
        # 获取选中的项目
        selected_indexes = self.file_tree.selectedIndexes()
        selected_files = []
        selected_folders = []
        
        # 收集选中的文件和文件夹信息
        for idx in selected_indexes:
            if idx.column() == 0:  # 只处理名称列
                file_info = self.model.item(idx.row(), 0).data(Qt.UserRole)
                if file_info:
                    is_file = not (file_info.get('is_dir') or file_info.get('isdir'))
                    if is_file:
                        selected_files.append(file_info)
                    else:
                        selected_folders.append(file_info)
        
        # 如果点击的是空白区域，只显示粘贴选项
        if not index.isValid():
            if self.view_mode == 'mine' and self.clipboard_files:
                act_paste = menu.addAction('粘贴')
                act_paste.triggered.connect(lambda: self._paste_files())
            if not menu.isEmpty():
                menu.exec(self.file_tree.viewport().mapToGlobal(pos))
            return
            
        # 如果点击的是已选中的项目，使用选中项目；否则使用点击的项目
        if index in selected_indexes:
            # 使用选中的项目
            target_files = selected_files
            target_folders = selected_folders
        else:
            # 使用点击的项目
            row = index.row()
            file_info = self.model.item(row, 0).data(Qt.UserRole)
            if not file_info:
                return
            is_file = not (file_info.get('is_dir') or file_info.get('isdir'))
            if is_file:
                target_files = [file_info]
                target_folders = []
            else:
                target_files = []
                target_folders = [file_info]
        
        # 如果有选中的文件夹
        if target_folders:
            folder = target_folders[0]  # 取第一个文件夹
            src = folder.get('__source') or ('mine' if self.view_mode == 'mine' else 'shared')
            
            # 如果是文件夹且在我的网盘中，可以粘贴到该文件夹
            if src == 'mine' and self.clipboard_files:
                act_paste = menu.addAction('粘贴到此文件夹')
                act_paste.triggered.connect(lambda: self._paste_files_to_folder(folder))
            
            # 只有菜单有内容才显示
            if not menu.isEmpty():
                menu.exec(self.file_tree.viewport().mapToGlobal(pos))
            return
            
        # 如果有选中的文件
        if target_files:
            file_info = target_files[0]  # 取第一个文件用于判断来源
            src = file_info.get('__source') or ('mine' if self.view_mode == 'mine' else 'shared')
            
            # 显示选中文件数量
            count_text = f" ({len(target_files)}个)" if len(target_files) > 1 else ""
            
            # shared: 阅读/下载
            if src == 'shared':
                if len(target_files) == 1:
                    act_read = menu.addAction('阅读')
                    act_read.triggered.connect(lambda: self._read_single(target_files[0]))
                act_down = menu.addAction(f'下载{count_text}')
                act_down.triggered.connect(lambda: self._download_multiple(target_files))
            else:
                # mine: 复制/剪切/删除/下载/阅读
                act_copy = menu.addAction(f'复制{count_text}')
                act_copy.triggered.connect(lambda: self._copy_multiple(target_files))
                
                act_cut = menu.addAction(f'剪切{count_text}')
                act_cut.triggered.connect(lambda: self._cut_multiple(target_files))
                
                menu.addSeparator()
                
                act_del = menu.addAction(f'删除{count_text}')
                def _do_delete_multiple():
                    try:
                        paths = []
                        for f in target_files:
                            path = f.get('path') or (self.current_folder.rstrip('/') + '/' + (f.get('server_filename') or f.get('name') or ''))
                            if path:
                                paths.append(path)
                        
                        if not paths:
                            return
                        
                        from PySide6.QtWidgets import QMessageBox
                        if QMessageBox.question(self, '确认删除', f'确定删除 {len(paths)} 个文件/文件夹？') != QMessageBox.Yes:
                            return
                        
                        self.client.delete_files(paths)
                        self.status_label.setText(f'删除完成 ({len(paths)}个)')
                        self.load_dir(self.current_folder)
                    except Exception as e:
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, '删除失败', str(e))
                act_del.triggered.connect(_do_delete_multiple)
                
                menu.addSeparator()
                
                if len(target_files) == 1:
                    act_read = menu.addAction('阅读')
                    act_read.triggered.connect(lambda: self._read_single(target_files[0]))
                
                act_down = menu.addAction(f'下载{count_text}')
                act_down.triggered.connect(lambda: self._download_multiple(target_files))
        
        # 确保菜单有内容才显示
        if not menu.isEmpty():
            menu.exec(self.file_tree.viewport().mapToGlobal(pos))

    def _copy_file(self, file_info):
        """复制文件到剪贴板"""
        self.clipboard_files = [file_info]
        self.clipboard_operation = 'copy'
        filename = file_info.get('server_filename') or file_info.get('name') or ''
        self.status_label.setText(f'已复制: {filename}')

    def _cut_file(self, file_info):
        """剪切文件到剪贴板"""
        self.clipboard_files = [file_info]
        self.clipboard_operation = 'cut'
        filename = file_info.get('server_filename') or file_info.get('name') or ''
        self.status_label.setText(f'已剪切: {filename}')

    def _copy_multiple(self, file_list):
        """批量复制文件到剪贴板"""
        self.clipboard_files = file_list
        self.clipboard_operation = 'copy'
        count = len(file_list)
        if count == 1:
            filename = file_list[0].get('server_filename') or file_list[0].get('name') or ''
            self.status_label.setText(f'已复制: {filename}')
        else:
            self.status_label.setText(f'已复制 {count} 个文件/文件夹')

    def _cut_multiple(self, file_list):
        """批量剪切文件到剪贴板"""
        self.clipboard_files = file_list
        self.clipboard_operation = 'cut'
        count = len(file_list)
        if count == 1:
            filename = file_list[0].get('server_filename') or file_list[0].get('name') or ''
            self.status_label.setText(f'已剪切: {filename}')
        else:
            self.status_label.setText(f'已剪切 {count} 个文件/文件夹')

    def _paste_files(self):
        """粘贴文件到当前目录"""
        if not self.clipboard_files:
            return
            
        try:
            items = []
            for file_info in self.clipboard_files:
                source_path = file_info.get('path') or (self.current_folder.rstrip('/') + '/' + (file_info.get('server_filename') or file_info.get('name') or ''))
                if not source_path:
                    continue
                    
                # 构造目标路径
                dest_path = self.current_folder.rstrip('/') + '/'
                
                # 如果是剪切操作且源路径和目标路径相同，跳过
                if self.clipboard_operation == 'cut' and source_path.startswith(dest_path):
                    continue
                
                items.append({"path": source_path, "dest": dest_path})
            
            if not items:
                return
            
            # 检查文件冲突
            conflict_response = self.client.check_file_conflicts(items)
            conflicts = conflict_response.get('conflicts', [])
            
            if conflicts:
                # 显示冲突处理对话框
                dialog = FileConflictDialog(conflicts, self.clipboard_operation, self)
                if dialog.exec() == QDialog.Accepted:
                    resolutions = dialog.get_resolutions()
                    # 根据用户选择处理冲突
                    items = self._resolve_conflicts(items, conflicts, resolutions)
                else:
                    # 用户取消操作
                    return
            
            if not items:
                self.status_label.setText('没有文件需要处理')
                return
            
            # 根据操作类型调用不同的API
            if self.clipboard_operation == 'copy':
                # 复制操作：调用复制API
                self.client.copy_files(items)
                self.status_label.setText('复制完成')
            else:
                # 剪切操作：调用移动API
                self.client.move_files(items)
                # 剪切操作完成后清空剪贴板
                self.clipboard_files = []
                self.clipboard_operation = None
                self.status_label.setText('移动完成')
                
            self.load_dir(self.current_folder)
            
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, '粘贴失败', str(e))

    def _paste_files_to_folder(self, folder_info):
        """粘贴文件到指定文件夹"""
        if not self.clipboard_files:
            return
            
        try:
            folder_path = folder_info.get('path') or (self.current_folder.rstrip('/') + '/' + (folder_info.get('server_filename') or folder_info.get('name') or ''))
            if not folder_path:
                return
                
            items = []
            for file_info in self.clipboard_files:
                source_path = file_info.get('path') or (self.current_folder.rstrip('/') + '/' + (file_info.get('server_filename') or file_info.get('name') or ''))
                if not source_path:
                    continue
                    
                # 构造目标路径
                dest_path = folder_path.rstrip('/') + '/'
                
                # 如果是剪切操作且源路径和目标路径相同，跳过
                if self.clipboard_operation == 'cut' and source_path.startswith(dest_path):
                    continue
                
                items.append({"path": source_path, "dest": dest_path})
            
            if not items:
                return
            
            # 检查文件冲突
            conflict_response = self.client.check_file_conflicts(items)
            conflicts = conflict_response.get('conflicts', [])
            
            if conflicts:
                # 显示冲突处理对话框
                dialog = FileConflictDialog(conflicts, self.clipboard_operation, self)
                if dialog.exec() == QDialog.Accepted:
                    resolutions = dialog.get_resolutions()
                    # 根据用户选择处理冲突
                    items = self._resolve_conflicts(items, conflicts, resolutions)
                else:
                    # 用户取消操作
                    return
            
            if not items:
                self.status_label.setText('没有文件需要处理')
                return
            
            # 根据操作类型调用不同的API
            if self.clipboard_operation == 'copy':
                # 复制操作：调用复制API
                self.client.copy_files(items)
                folder_name = folder_info.get('server_filename') or folder_info.get('name') or ''
                self.status_label.setText(f'复制到 {folder_name} 完成')
            else:
                # 剪切操作：调用移动API
                self.client.move_files(items)
                # 剪切操作完成后清空剪贴板
                self.clipboard_files = []
                self.clipboard_operation = None
                folder_name = folder_info.get('server_filename') or folder_info.get('name') or ''
                self.status_label.setText(f'移动到 {folder_name} 完成')
            self.load_dir(self.current_folder)
            
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, '粘贴失败', str(e))

    def _resolve_conflicts(self, items, conflicts, resolutions):
        """根据用户选择处理文件冲突"""
        resolved_items = []
        conflict_paths = {conflict['source_path'] for conflict in conflicts}
        
        for item in items:
            source_path = item['path']
            if source_path in conflict_paths:
                # 找到对应的冲突
                conflict = next(c for c in conflicts if c['source_path'] == source_path)
                conflict_index = conflicts.index(conflict)
                resolution = resolutions.get(conflict_index, 'skip')
                
                if resolution == 'skip':
                    # 跳过此文件
                    continue
                elif resolution == 'overwrite':
                    # 覆盖，使用原始目标路径
                    resolved_items.append(item)
                elif resolution == 'rename':
                    # 重命名，修改目标路径
                    dest_dir = item['dest']
                    filename = os.path.basename(source_path)
                    name, ext = os.path.splitext(filename)
                    
                    # 生成新的文件名
                    counter = 1
                    while True:
                        new_filename = f"{name}_{counter}{ext}"
                        new_target_path = dest_dir.rstrip('/') + '/' + new_filename
                        
                        # 检查新文件名是否也存在冲突
                        new_item = {"path": source_path, "dest": dest_dir}
                        new_conflict_response = self.client.check_file_conflicts([new_item])
                        if not new_conflict_response.get('conflicts'):
                            item['dest'] = dest_dir  # 保持目录不变，让API处理重命名
                            resolved_items.append(item)
                            break
                        counter += 1
            else:
                # 没有冲突的文件直接添加
                resolved_items.append(item)
        
        return resolved_items


class FileConflictDialog(QDialog):
    """文件冲突处理对话框"""
    
    def __init__(self, conflicts, operation_type, parent=None):
        super().__init__(parent)
        self.conflicts = conflicts
        self.operation_type = operation_type  # 'copy' 或 'cut'
        self.resolutions = {}  # 存储每个冲突的解决方案
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle(f'文件冲突 - {self.operation_type}')
        self.setModal(True)
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel(f'检测到 {len(self.conflicts)} 个文件冲突，请选择处理方式：')
        title_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 冲突列表
        self.conflict_list = QListWidget()
        self.conflict_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.conflict_list)
        
        # 为每个冲突创建项目
        for i, conflict in enumerate(self.conflicts):
            source_name = os.path.basename(conflict['source_path'])
            existing_file = conflict['existing_file']
            existing_size = existing_file.get('size', 0)
            existing_time = existing_file.get('server_mtime', 0)
            
            # 格式化文件大小
            size_text = self._format_file_size(existing_size)
            
            # 格式化时间
            time_text = self._format_timestamp(existing_time)
            
            item_text = f"{source_name}\n"
            item_text += f"目标位置已存在同名文件 (大小: {size_text}, 修改时间: {time_text})"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, i)
            self.conflict_list.addItem(item)
        
        # 处理方式选择
        self.strategy_group = QGroupBox("处理方式")
        strategy_layout = QVBoxLayout(self.strategy_group)
        
        self.strategy_buttons = QButtonGroup()
        
        # 跳过
        self.skip_radio = QRadioButton("跳过此文件")
        self.skip_radio.setChecked(True)
        self.strategy_buttons.addButton(self.skip_radio, 0)
        strategy_layout.addWidget(self.skip_radio)
        
        # 覆盖
        self.overwrite_radio = QRadioButton("覆盖目标文件")
        self.strategy_buttons.addButton(self.overwrite_radio, 1)
        strategy_layout.addWidget(self.overwrite_radio)
        
        # 重命名
        self.rename_radio = QRadioButton("重命名（添加数字后缀）")
        self.strategy_buttons.addButton(self.rename_radio, 2)
        strategy_layout.addWidget(self.rename_radio)
        
        # 应用到所有
        self.apply_all_checkbox = QCheckBox("应用到所有冲突")
        strategy_layout.addWidget(self.apply_all_checkbox)
        
        layout.addWidget(self.strategy_group)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 连接信号
        self.conflict_list.currentRowChanged.connect(self.on_conflict_selected)
        self.strategy_buttons.buttonClicked.connect(self.on_strategy_changed)
        
        # 初始化第一个冲突
        if self.conflicts:
            self.conflict_list.setCurrentRow(0)
            self.on_conflict_selected(0)
    
    def on_conflict_selected(self, row):
        """当选择不同冲突时更新策略选择"""
        if row < 0 or row >= len(self.conflicts):
            return
            
        conflict_index = self.conflict_list.item(row).data(Qt.UserRole)
        if conflict_index in self.resolutions:
            strategy = self.resolutions[conflict_index]
            if strategy == 'skip':
                self.skip_radio.setChecked(True)
            elif strategy == 'overwrite':
                self.overwrite_radio.setChecked(True)
            elif strategy == 'rename':
                self.rename_radio.setChecked(True)
    
    def on_strategy_changed(self, button):
        """当策略改变时保存选择"""
        current_row = self.conflict_list.currentRow()
        if current_row < 0:
            return
            
        conflict_index = self.conflict_list.item(current_row).data(Qt.UserRole)
        
        if button == self.skip_radio:
            strategy = 'skip'
        elif button == self.overwrite_radio:
            strategy = 'overwrite'
        elif button == self.rename_radio:
            strategy = 'rename'
        else:
            return
            
        self.resolutions[conflict_index] = strategy
        
        # 如果选择了"应用到所有"，则更新所有冲突
        if self.apply_all_checkbox.isChecked():
            for i in range(len(self.conflicts)):
                self.resolutions[i] = strategy
    
    def get_resolutions(self):
        """获取所有冲突的解决方案"""
        # 确保所有冲突都有解决方案
        for i in range(len(self.conflicts)):
            if i not in self.resolutions:
                self.resolutions[i] = 'skip'  # 默认跳过
        return self.resolutions
    
    def _format_file_size(self, size_bytes):
        """格式化文件大小为可读格式"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        if i == 0:
            return f"{int(size)} {size_names[i]}"
        else:
            return f"{size:.1f} {size_names[i]}"
    
    def _format_timestamp(self, timestamp):
        """格式化时间戳为可读格式"""
        if not timestamp or timestamp == 0:
            return "未知时间"
        
        try:
            import datetime
            # 百度网盘的时间戳通常是秒级
            dt = datetime.datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return "无效时间"


class UploadWorker(QObject):
    """异步上传工作线程"""
    
    # 信号定义
    progress_updated = Signal(int, str)  # 进度百分比, 当前文件名
    upload_finished = Signal(dict)  # 上传结果
    error_occurred = Signal(str)  # 错误信息
    
    def __init__(self, client, file_paths, target_type, current_folder=None):
        super().__init__()
        self.client = client
        self.file_paths = file_paths
        self.target_type = target_type  # 'shared' 或 'mine'
        self.current_folder = current_folder
        self.is_cancelled = False
    
    def cancel(self):
        """取消上传"""
        self.is_cancelled = True
    
    def run(self):
        """执行上传任务"""
        try:
            total = len(self.file_paths)
            success = 0
            failed = 0
            results = []
            
            if self.target_type == 'shared':
                # 共享资源：批量上传
                self.progress_updated.emit(10, '正在上传到共享资源...')
                resp = self.client.upload_to_shared_batch(self.file_paths)
                results = (resp or {}).get('results', []) if isinstance(resp, dict) else []
                success = sum(1 for r in results if r.get('ok'))
                failed = len(results) - success
                self.progress_updated.emit(100, f'上传完成：{success}/{total}')
            else:
                # 我的网盘：逐个上传
                for idx, file_path in enumerate(self.file_paths, start=1):
                    if self.is_cancelled:
                        break
                        
                    percent = int(idx * 100 / total)
                    name = os.path.basename(file_path)
                    self.progress_updated.emit(percent, f'正在上传：{name}')
                    
                    try:
                        target_path = (self.current_folder.rstrip('/') + '/' + name) if self.current_folder else None
                        resp = self.client.upload_to_mine(file_path, target_path=target_path)
                        
                        if isinstance(resp, dict) and not resp.get('error'):
                            success += 1
                            results.append({'filename': name, 'ok': True, 'path': resp.get('path')})
                        else:
                            failed += 1
                            error_msg = resp.get('error', '未知错误') if isinstance(resp, dict) else str(resp)
                            results.append({'filename': name, 'ok': False, 'error': error_msg})
                    except Exception as e:
                        failed += 1
                        results.append({'filename': name, 'ok': False, 'error': str(e)})
            
            # 发送完成信号
            self.upload_finished.emit({
                'success': success,
                'failed': failed,
                'total': total,
                'results': results,
                'cancelled': self.is_cancelled
            })
                
        except Exception as e:
            self.error_occurred.emit(str(e))


class DownloadWorker(QObject):
    """异步下载工作线程"""
    
    # 信号定义
    progress_updated = Signal(int, str)  # 进度百分比, 当前文件名
    download_finished = Signal(dict)  # 下载结果
    error_occurred = Signal(str)  # 错误信息
    
    def __init__(self, client, file_list, save_dir):
        super().__init__()
        self.client = client
        self.file_list = file_list
        self.save_dir = save_dir
        self.is_cancelled = False
    
    def cancel(self):
        """取消下载"""
        self.is_cancelled = True
    
    def run(self):
        """执行下载任务"""
        try:
            total_files = len(self.file_list)
            success_count = 0
            failed_count = 0
            results = []
            
            for i, file_info in enumerate(self.file_list):
                if self.is_cancelled:
                    break
                
                try:
                    fsid = file_info.get('fs_id') or file_info.get('fsid')
                    if not fsid:
                        failed_count += 1
                        results.append({'filename': f'file_{i+1}', 'ok': False, 'error': '缺少文件ID'})
                        continue
                    
                    save_name = (file_info.get('server_filename') or file_info.get('name') or f'file_{i+1}')
                    target_path = os.path.join(self.save_dir, save_name)
                    
                    # 更新进度
                    progress = int((i / total_files) * 100)
                    self.progress_updated.emit(progress, f'正在下载：{save_name}')
                    
                    # 下载文件
                    r = self.client.stream_file(int(fsid))
                    with open(target_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if self.is_cancelled:
                                break
                            if chunk:
                                f.write(chunk)
                        
                    if not self.is_cancelled:
                        success_count += 1
                        results.append({'filename': save_name, 'ok': True, 'path': target_path})
                        
                except Exception as e:
                    failed_count += 1
                    results.append({'filename': save_name, 'ok': False, 'error': str(e)})
            
            # 发送完成信号
            self.download_finished.emit({
                'success': success_count,
                'failed': failed_count,
                'total': total_files,
                'results': results,
                'cancelled': self.is_cancelled
            })
            
        except Exception as e:
            self.error_occurred.emit(str(e))


class SingleReadWorker(QObject):
    """将单个文件通过后端流式保存到临时目录（用于阅读），带进度。"""
    progress_updated = Signal(int, str)
    read_finished = Signal(dict)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, client, file_info):
        super().__init__()
        self.client = client
        self.file_info = file_info

    def run(self):
        try:
            import tempfile, os
            name = (self.file_info.get('server_filename') or self.file_info.get('name') or 'document')
            fsid = int(self.file_info.get('fs_id') or self.file_info.get('fsid'))
            tmp_dir = tempfile.mkdtemp(prefix='docview_')
            local_path = os.path.join(tmp_dir, name)

            r = self.client.stream_file(fsid)
            total = int(r.headers.get('Content-Length') or 0)
            downloaded = 0
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=64*1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    if total:
                        downloaded += len(chunk)
                        percent = int(downloaded * 100 / total)
                        self.progress_updated.emit(percent, f'正在加载文档：{name} {percent}%')

            self.read_finished.emit({'ok': True, 'path': local_path, 'name': name})
            self.finished.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.finished.emit()
