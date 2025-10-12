#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP重连对话框

当MCP连接失败时，显示重连对话框供用户选择重试或取消。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from typing import Dict, Any


class McpReconnectDialog(QDialog):
    """MCP连接失败重连对话框"""
    
    def __init__(self, error_message: str, connection_info: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("MCP连接失败")
        self.setModal(True)
        self.resize(500, 300)
        
        self.connection_info = connection_info
        self.setup_ui(error_message)
    
    def setup_ui(self, error_message: str):
        """设置UI界面"""
        layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel("MCP服务器连接失败")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 错误信息
        error_label = QLabel("错误详情：")
        error_label.setStyleSheet("font-weight: bold; color: #d32f2f;")
        layout.addWidget(error_label)
        
        error_text = QTextEdit()
        error_text.setPlainText(error_message)
        error_text.setReadOnly(True)
        error_text.setMaximumHeight(80)
        error_text.setStyleSheet("background-color: #ffebee; border: 1px solid #f44336;")
        layout.addWidget(error_text)
        
        # 连接信息
        info_label = QLabel("连接配置：")
        info_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(info_label)
        
        info_text = self._format_connection_info()
        info_display = QTextEdit()
        info_display.setPlainText(info_text)
        info_display.setReadOnly(True)
        info_display.setMaximumHeight(100)
        info_display.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ccc;")
        layout.addWidget(info_display)
        
        # 建议
        suggestion_label = QLabel("建议操作：")
        suggestion_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(suggestion_label)
        
        suggestions = self._get_suggestions()
        suggestion_text = QTextEdit()
        suggestion_text.setPlainText(suggestions)
        suggestion_text.setReadOnly(True)
        suggestion_text.setMaximumHeight(60)
        suggestion_text.setStyleSheet("background-color: #e3f2fd; border: 1px solid #2196f3;")
        layout.addWidget(suggestion_text)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        retry_btn = QPushButton("重试连接")
        retry_btn.setStyleSheet("""
            QPushButton {
                background-color: #4caf50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        retry_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(retry_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _format_connection_info(self) -> str:
        """格式化连接信息"""
        mode = self.connection_info.get('mode', 'unknown')
        info_lines = [f"连接模式: {mode}"]
        
        if mode == 'ssh-stdio':
            remote_host = self.connection_info.get('remote_host', 'N/A')
            info_lines.append(f"远程主机: {remote_host}")
        elif mode in ('tcp', 'tcp-tls'):
            endpoint = self.connection_info.get('remote_endpoint', 'N/A')
            encrypted = self.connection_info.get('encrypted', False)
            info_lines.append(f"远程端点: {endpoint}")
            info_lines.append(f"加密连接: {'是' if encrypted else '否'}")
        
        session_start = self.connection_info.get('session_start_time')
        if session_start:
            import time
            uptime = time.time() - session_start
            info_lines.append(f"会话运行时间: {uptime:.0f}秒")
        
        return '\n'.join(info_lines)
    
    def _get_suggestions(self) -> str:
        """获取建议操作"""
        mode = self.connection_info.get('mode', 'unknown')
        
        if mode == 'ssh-stdio':
            return ("1. 检查SSH服务器是否运行\n"
                   "2. 验证SSH密钥文件是否存在\n"
                   "3. 确认网络连接正常")
        elif mode in ('tcp', 'tcp-tls'):
            return ("1. 检查MCP服务器是否在指定端口监听\n"
                   "2. 验证防火墙设置\n"
                   "3. 确认TLS证书配置正确（如使用TLS）")
        else:
            return ("1. 检查本地MCP服务器进程\n"
                   "2. 验证配置文件设置\n"
                   "3. 查看日志文件获取详细错误信息")
