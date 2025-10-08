#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的auth_server.py包装
兼容原有的启动方式：python auth_server.py
新架构使用：python main.py 或 uvicorn main:app
"""

# 导入主应用
from main import app

# 兼容性：如果直接运行此文件，启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1
    )