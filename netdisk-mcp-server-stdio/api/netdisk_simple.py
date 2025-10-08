#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网盘API路由 - 简化版本
提供百度网盘文件管理功能的RESTful接口
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Optional, Dict, Any
import os
import sys

router = APIRouter(prefix="/api/netdisk", tags=["netdisk"])

# 延迟导入，避免模块加载时的阻塞
def get_netdisk_config():
    """获取网盘配置"""
    return {
        'access_token': os.getenv('BAIDU_NETDISK_ACCESS_TOKEN'),
        'app_key': os.getenv('BAIDU_NETDISK_APP_KEY'),
        'refresh_token': os.getenv('BAIDU_NETDISK_REFRESH_TOKEN'),
        'secret_key': os.getenv('BAIDU_NETDISK_SECRET_KEY')
    }

def check_dependencies():
    """检查依赖是否可用"""
    try:
        import openapi_client
        import requests
        return True
    except ImportError as e:
        return False

@router.get("/health")
async def health_check():
    """
    网盘API健康检查
    
    检查API是否正常运行
    """
    try:
        config = get_netdisk_config()
        deps_ok = check_dependencies()
        
        return {
            "status": "success",
            "message": "网盘API健康检查通过",
            "config_loaded": bool(config['access_token']),
            "dependencies_ok": deps_ok,
            "api_endpoints": [
                "GET /api/netdisk/health - 健康检查",
                "GET /api/netdisk/help - 获取帮助信息",
                "GET /api/netdisk/auth/status - 检查授权状态"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")

@router.get("/help")
async def get_netdisk_help():
    """
    获取网盘API帮助信息
    
    返回详细的API使用说明和示例
    """
    return {
        "status": "success",
        "message": "网盘API帮助信息",
        "api_endpoints": {
            "GET /api/netdisk/health": "网盘API健康检查",
            "GET /api/netdisk/help": "获取API帮助信息",
            "GET /api/netdisk/auth/status": "检查授权状态"
        },
        "features": [
            "文件上传下载",
            "文件搜索",
            "目录浏览",
            "多媒体文件管理",
            "用户信息查询",
            "配额信息查询",
            "频率限制管理",
            "授权状态检查"
        ],
        "rate_limits": {
            "search": {"daily": 2000, "per_minute": 20},
            "listall": {"per_minute": 8},
            "fileinfo": {"per_minute": 30},
            "filemanager": {"per_minute": 20},
            "userinfo": {"per_minute": 10},
            "multimedia": {"per_minute": 15},
            "share": {"per_minute": 10},
            "upload": {"per_minute": 5},
            "download": {"per_minute": 10},
            "default": {"per_minute": 20}
        },
        "usage_examples": {
            "health_check": "GET /api/netdisk/health",
            "get_help": "GET /api/netdisk/help",
            "check_auth": "GET /api/netdisk/auth/status"
        },
        "configuration_required": [
            "BAIDU_NETDISK_ACCESS_TOKEN",
            "BAIDU_NETDISK_APP_KEY", 
            "BAIDU_NETDISK_REFRESH_TOKEN",
            "BAIDU_NETDISK_SECRET_KEY"
        ],
        "dependencies": [
            "openapi_client",
            "requests",
            "python-multipart"
        ]
    }

@router.get("/auth/status")
async def check_auth_status():
    """
    检查授权状态
    
    返回当前授权状态和配置信息
    """
    try:
        config = get_netdisk_config()
        
        if not config['access_token']:
            return {
                "status": "error",
                "message": "未找到访问令牌，请先进行授权",
                "auth_status": "not_authorized",
                "next_step": "请运行 get_token.py 进行授权",
                "config_status": {
                    "access_token": bool(config['access_token']),
                    "app_key": bool(config['app_key']),
                    "refresh_token": bool(config['refresh_token']),
                    "secret_key": bool(config['secret_key'])
                }
            }
        
        return {
            "status": "success",
            "message": "授权配置已加载",
            "auth_status": "configured",
            "access_token": config['access_token'][:20] + "..." if config['access_token'] else None,
            "app_key": config['app_key'],
            "config_complete": all([
                config['access_token'],
                config['app_key'],
                config['refresh_token'],
                config['secret_key']
            ])
        }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查授权状态时发生错误: {str(e)}")

@router.get("/status")
async def get_netdisk_status():
    """
    获取网盘API状态
    
    返回API运行状态和配置信息
    """
    try:
        config = get_netdisk_config()
        deps_ok = check_dependencies()
        
        return {
            "status": "success",
            "message": "网盘API状态正常",
            "api_status": {
                "running": True,
                "dependencies_loaded": deps_ok,
                "config_loaded": bool(config['access_token']),
                "endpoints_available": 3
            },
            "configuration": {
                "access_token_configured": bool(config['access_token']),
                "app_key_configured": bool(config['app_key']),
                "refresh_token_configured": bool(config['refresh_token']),
                "secret_key_configured": bool(config['secret_key'])
            },
            "next_steps": [
                "配置百度网盘API密钥" if not config['access_token'] else "API已配置",
                "安装python-multipart依赖" if not deps_ok else "依赖已安装",
                "访问 /docs 查看完整API文档"
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态时发生错误: {str(e)}")
