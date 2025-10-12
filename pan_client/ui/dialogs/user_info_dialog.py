from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
                              QFrame, QPushButton, QApplication, QMessageBox, QInputDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont
from typing import Dict, Any, Optional
from pan_client.core.utils import get_icon_path
from pan_client.core.rest_client import ApiClient
from pan_client.core.token import list_accounts, migrate_accounts
from pan_client.ui.login_dialog import LoginDialog

class UserInfoDialog(QDialog):
    def __init__(self, info: Dict[str, Any], parent=None):
        # 兼容旧调用：如果第一个参数是父窗口而不是 info
        if not isinstance(info, dict):
            parent = info
            info = {}
        super().__init__(parent)
        self.setWindowTitle("我的信息")
        self.setFixedSize(520, 380)
        self.machine_code = "DEMO-MACHINE-CODE-12345"

        # 保存用户信息
        self.info: Dict[str, Any] = info or {}

        # 初始化UI元素属性
        self.user_type_label = None
        self.download_limit_label = None
        self.time_label = None
        self.upgrade_btn = None
        self.user_name_label = None

        self.setup_ui()
        self._apply_user_info(self.info)
        
    def setup_ui(self):
        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(20)
        
        # 内容区域（左右分栏）
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        
        # 左侧用户信息
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 15, 0)  # 减小右边距
        left_layout.setSpacing(15)
        
        # 用户信息标题
        user_info_title = QLabel("用户信息")
        user_info_title.setStyleSheet("""
            QLabel {
                color: #333333;
                font-size: 14px;
                font-weight: bold;
                margin-bottom: 10px;
            }
        """)
        
        # 用户类型/名称
        user_type_layout = QHBoxLayout()
        user_icon = QLabel()
        user_icon.setPixmap(QIcon(get_icon_path('user.png')).pixmap(20, 20))
        self.user_type_label = QLabel("演示用户")
        self.user_type_label.setStyleSheet("color: #1976D2; font-weight: bold;")
        user_type_layout.addWidget(user_icon)
        user_type_layout.addWidget(self.user_type_label)
        user_type_layout.addStretch()
        
        # 用户信息列表（改为展示百度网盘用户信息）
        info_items = [
            ("当前用户:", "-"),
            ("账号ID:", "-"),
            ("昵称:", "-"),
            ("会员类型:", "-"),
            ("剩余空间:", "-")
        ]
        
        # 创建并保存需要动态更新的标签
        self.user_name_label = None
        self.user_uk_label = None
        self.user_nick_label = None
        self.user_vip_label = None
        self.space_left_label = None
        
        info_layout = QVBoxLayout()
        info_layout.setSpacing(15)
        
        for label_text, value_text in info_items:
            item_layout = QHBoxLayout()
            item_layout.setSpacing(5)  # 减小标签和值之间的间距
            
            label = QLabel(label_text)
            label.setStyleSheet("color: #666666;")
            label.setFixedWidth(70)  # 固定标签宽度
            
            value = QLabel(value_text)
            value.setStyleSheet("color: #333333;")
            value.setAlignment(Qt.AlignRight)
            
            # 机器码已不展示，去除复制逻辑
            
            # 保存需要动态更新的标签引用
            if label_text == "当前用户:":
                self.user_name_label = value
            elif label_text == "账号ID:":
                self.user_uk_label = value
            elif label_text == "昵称:":
                self.user_nick_label = value
            elif label_text == "会员类型:":
                self.user_vip_label = value
            elif label_text == "剩余空间:":
                self.space_left_label = value
            
            item_layout.addWidget(label)
            item_layout.addWidget(value)
            info_layout.addLayout(item_layout)
        
        left_layout.addWidget(user_info_title)
        left_layout.addLayout(user_type_layout)
        left_layout.addLayout(info_layout)
        left_layout.addStretch()
        
        # 分割线
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setStyleSheet("""
            QFrame {
                background-color: #e5f8ff;  /* 浅蓝色 */
                width: 1px;
                margin-top: 5px;     /* 从用户类型下方开始 */
                margin-bottom: 50px;  /* 缩短底部长度 */
            }
        """)
        
        # 右侧软件介绍（替换会员特权）
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(15, 0, 0, 0)  # 减小左边距
        right_layout.setSpacing(15)
        
        # 标题
        vip_title = QLabel("软件介绍")
        vip_title.setStyleSheet("""
            QLabel {
                color: #333333;
                font-size: 14px;
                font-weight: bold;
                margin-bottom: 10px;
            }
        """)
        
        # 简要功能/说明
        privileges = [
            "云栈·共享资料库 桌面客户端",
            "支持浏览/搜索/下载/预览等常用操作",
            "扫码登录百度网盘，凭令牌访问，不保存账号密码",
            "支持多账号登录与一键切换",
            "数据缓存与下载记录保存在本地",
            "仅用于学习交流，请勿用于商业用途"
        ]
        
        vip_layout = QVBoxLayout()
        vip_layout.setSpacing(15)
        
        for i, privilege in enumerate(privileges):
            label = QLabel(privilege)
            label.setStyleSheet("QLabel {color: #666666; font-size: 13px;}")
            vip_layout.addWidget(label)
        
        right_layout.addWidget(vip_title)
        right_layout.addLayout(vip_layout)
        right_layout.addStretch()
        
        # 添加左右面板和分割线到内容布局
        content_layout.addWidget(left_widget, 1)  # 设置拉伸因子
        content_layout.addWidget(separator)
        content_layout.addWidget(right_widget, 1)  # 设置拉伸因子
        
        # 底部按钮区域：仅切换账号
        self.switch_btn = QPushButton("切换账号")
        self.switch_btn.setFixedHeight(36)
        self.switch_btn.setStyleSheet("""
            QPushButton {
                background: #1976D2;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 0 12px;
            }
            QPushButton:hover { background: #1565C0; }
        """)
        self.switch_btn.clicked.connect(self.on_switch_account)

        # 组装主布局
        main_layout.addLayout(content_layout)
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.switch_btn)
        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)
        
        self.setLayout(main_layout)

    def copy_machine_code(self, code):
        """复制机器码到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(code)
        QMessageBox.information(self, "复制成功", "机器码已复制到剪贴板") 

    def _apply_user_info(self, info: Dict[str, Any]) -> None:
        """将后端 /userinfo 返回的数据映射到对话框上。"""
        # 解析用户名（不同接口可能字段不同）
        user_name = (
            info.get('baidu_name')
            or info.get('netdisk_name')
            or info.get('user_name')
            or info.get('uname')
            or str(info.get('uk') or info.get('userid') or '未知用户')
        )
        if self.user_type_label is not None:
            self.user_type_label.setText(f"已登录：{user_name}")
        if self.user_name_label is not None:
            self.user_name_label.setText(str(user_name))
        if self.user_uk_label is not None:
            self.user_uk_label.setText(str(info.get('uk') or info.get('userid') or '-'))
        if self.user_nick_label is not None:
            self.user_nick_label.setText(str(info.get('baidu_name') or info.get('netdisk_name') or '-'))

        # 可选：解析是否 VIP
        vip_text = None
        vip_val = info.get('vip_type') or info.get('vip')
        if isinstance(vip_val, (int, str)):
            vip_text = "VIP" if str(vip_val) != '0' else "普通用户"
        if vip_text and self.user_type_label is not None:
            self.user_type_label.setText(f"{user_name}（{vip_text}）")
        if self.user_vip_label is not None:
            self.user_vip_label.setText(vip_text or '-')

        # 查询配额并显示剩余空间
        try:
            quota = ApiClient().get_quota()
            total = int(quota.get('total', 0))
            used = int(quota.get('used', 0))
            left = max(total - used, 0)
            if self.space_left_label is not None:
                self.space_left_label.setText(self._format_bytes(left))
        except Exception:
            if self.space_left_label is not None:
                self.space_left_label.setText('-')

    def _format_bytes(self, size: int) -> str:
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.2f} {unit}"
            value /= 1024

    def update_info(self, info: Dict[str, Any]) -> None:
        """外部刷新用户信息。"""
        self.info = info or {}
        self._apply_user_info(self.info)

    def on_switch_account(self) -> None:
        """显示账号列表并切换当前账号；也可扫码新增。"""
        try:
            # 合并历史账号并读取
            try:
                migrate_accounts()
            except Exception:
                pass
            # 尝试补全历史账户的昵称（旧版本保存为 default）
            accts = list_accounts() or []
            try:
                api_probe = ApiClient()
                from pan_client.core.token import get_access_token as _ga
                for a in accts:
                    name = str(a.get('name') or '')
                    acc_id = a.get('id')
                    if name.lower() == 'default' and acc_id:
                        # 切到该账号拉取一次用户信息用于完善昵称
                        if api_probe.switch_account(acc_id):
                            try:
                                info = api_probe.get_userinfo() or {}
                                token_val = _ga(acc_id)
                                if info and token_val:
                                    api_probe.set_local_access_token(token_val, account_id=acc_id, user=info)
                            except Exception:
                                pass
                # 迁移并重新读取一次账户列表
                try:
                    migrate_accounts()
                except Exception:
                    pass
                accts = list_accounts() or []
            except Exception:
                pass
            items = [f"{a.get('name')} ({a.get('id')})" + (" [当前]" if a.get('is_current') else "") for a in accts]
            items.append("添加新账号…")
            chooser = QInputDialog(self)
            chooser.setWindowTitle("切换账号")
            chooser.setLabelText("选择一个账号：")
            chooser.setComboBoxItems(items)
            try:
                chooser.setOkButtonText("确定")
                chooser.setCancelButtonText("取消")
            except Exception:
                pass
            if chooser.exec() != QDialog.Accepted:
                return
            sel = chooser.textValue()
            if sel == "添加新账号…":
                dlg = LoginDialog(self)
                if dlg.exec() == QDialog.Accepted:
                    try:
                        # 使用父窗口的 ApiClient 刷新并重载列表
                        parent = self.parent()
                        if parent is not None and hasattr(parent, 'api'):
                            # 重新读取当前 token 并更新父 api headers
                            from pan_client.core.token import get_access_token as _ga
                            t = _ga()
                            if t:
                                parent.api.set_local_access_token(t)
                            if hasattr(parent, 'load_dir') and hasattr(parent, 'current_folder'):
                                parent.load_dir(parent.current_folder)
                        QMessageBox.information(self, "提示", "已添加并切换到新账号。")
                    except Exception:
                        pass
                    self.accept()
                return
            idx = items.index(sel)
            target_id = accts[idx].get('id')
            switched = False
            parent = self.parent()
            if parent is not None and hasattr(parent, 'api'):
                switched = parent.api.switch_account(target_id)
            else:
                switched = ApiClient().switch_account(target_id)
            if target_id and switched:
                try:
                    # 重新注入最新 token，确保后续请求走新账号
                    from pan_client.core.token import get_access_token as _ga
                    t = _ga(target_id)
                    if parent is not None and hasattr(parent, 'api') and t:
                        parent.api.set_local_access_token(t)
                    if parent is not None and hasattr(parent, 'load_dir') and hasattr(parent, 'current_folder'):
                        parent.load_dir(parent.current_folder)
                except Exception:
                    pass
                QMessageBox.information(self, "提示", f"已切换到账号：{accts[idx].get('name')}")
                self.accept()
        except Exception as e:
            QMessageBox.warning(self, "切换失败", f"切换账号时出错：{e}")