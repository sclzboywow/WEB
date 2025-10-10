#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分享API路由
严格按照百度网盘官方文档实现分享功能
参考文档: https://pan.baidu.com/union/doc/Tlaaocmkj
"""

from fastapi import APIRouter, HTTPException, Query, Path, Body, Request
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
import os
import sys
import json
import requests
import random
import string
from datetime import datetime

# 添加当前目录到系统路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

router = APIRouter(prefix="/api/share", tags=["share"])

# 获取网盘配置
def get_netdisk_config():
    """获取网盘配置"""
    return {
        'access_token': os.getenv('BAIDU_NETDISK_ACCESS_TOKEN'),
        'app_key': os.getenv('BAIDU_NETDISK_APP_KEY'),
        'refresh_token': os.getenv('BAIDU_NETDISK_REFRESH_TOKEN'),
        'secret_key': os.getenv('BAIDU_NETDISK_SECRET_KEY')
    }

def generate_share_password():
    """生成4位分享密码，数字+小写字母组成"""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=4))

@router.post("/create")
async def create_share_link(
    fsid_list: List[str] = Body(..., description="分享文件ID列表"),
    period: int = Body(7, description="分享有效期，单位天"),
    pwd: Optional[str] = Body(None, description="分享密码，4位数字+小写字母组成"),
    remark: Optional[str] = Body("", description="分享备注")
):
    """
    创建分享链接
    
    严格按照官方文档实现：
    POST /apaas/1.0/share/set?product=netdisk HTTP/1.1
    Host: pan.baidu.com
    
    请求参数：
    - fsid_list: 分享文件id列表，json格式，字符串数组
    - period: 分享有效期，单位天
    - pwd: 分享密码，长度4位，数字+小写字母组成
    - remark: 分享备注
    """
    try:
        config = get_netdisk_config()
        if not config['access_token'] or not config['app_key']:
            raise HTTPException(status_code=500, detail="网盘配置不完整")
        
        # 如果没有提供密码，自动生成一个4位密码
        if not pwd:
            pwd = generate_share_password()
        
        # 验证密码格式 - 允许数字和小写字母
        if len(pwd) != 4 or not all(c.isalnum() and (c.isdigit() or c.islower()) for c in pwd):
            raise HTTPException(status_code=400, detail="分享密码必须是4位数字+小写字母组成")
        
        # 构建请求URL - 严格按照官方文档
        url = "https://pan.baidu.com/apaas/1.0/share/set"
        
        # 构建请求参数 - 严格按照官方文档
        params = {
            'product': 'netdisk',
            'appid': config['app_key'],
            'access_token': config['access_token']
        }
        
        # 构建请求体 - 严格按照官方文档
        data = {
            'fsid_list': json.dumps(fsid_list),
            'period': str(period),
            'pwd': pwd,
            'remark': remark or ""
        }
        
        # 发送请求
        response = requests.post(url, params=params, data=data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # 检查错误码
        if result.get('errno') != 0:
            error_msg = result.get('show_msg', '未知错误')
            raise HTTPException(status_code=400, detail=f"创建分享链接失败: {error_msg}")
        
        # 返回分享信息 - 严格按照官方文档的响应格式
        share_data = result.get('data', {})
        return JSONResponse({
            "status": "success",
            "message": "创建分享链接成功",
            "data": {
                "share_id": share_data.get('share_id'),
                "short_url": share_data.get('short_url'),
                "link": share_data.get('link'),
                "period": share_data.get('period'),
                "pwd": share_data.get('pwd'),
                "remark": share_data.get('remark')
            },
            "request_id": result.get('request_id'),
            "errno": result.get('errno'),
            "show_msg": result.get('show_msg')
        })
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"网络请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建分享链接时发生错误: {str(e)}")

@router.get("/query/{share_id}")
async def get_share_info(share_id: int):
    """
    查询分享详情
    
    严格按照官方文档实现：
    GET /apaas/1.0/share/query?product=netdisk&appid={appid}&access_token={access_token}&share_id={share_id}
    """
    try:
        config = get_netdisk_config()
        if not config['access_token'] or not config['app_key']:
            raise HTTPException(status_code=500, detail="网盘配置不完整")
        
        # 构建请求URL - 严格按照官方文档
        url = "https://pan.baidu.com/apaas/1.0/share/query"
        
        # 构建请求参数 - 严格按照官方文档
        params = {
            'product': 'netdisk',
            'appid': config['app_key'],
            'access_token': config['access_token'],
            'share_id': str(share_id)
        }
        
        # 发送请求
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # 检查错误码
        if result.get('errno') != 0:
            error_msg = result.get('show_msg', '未知错误')
            raise HTTPException(status_code=400, detail=f"查询分享详情失败: {error_msg}")
        
        # 返回分享详情 - 严格按照官方文档的响应格式
        share_data = result.get('data', {})
        return JSONResponse({
            "status": "success",
            "message": "查询分享详情成功",
            "data": share_data,
            "request_id": result.get('request_id'),
            "errno": result.get('errno'),
            "show_msg": result.get('show_msg')
        })
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"网络请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询分享详情时发生错误: {str(e)}")

@router.post("/transfer")
async def transfer_share_files(
    share_id: int = Body(..., description="分享ID"),
    pwd: str = Body(..., description="分享密码"),
    fsids: List[str] = Body(..., description="要转存的文件ID列表"),
    dest_path: str = Body("/", description="转存目标路径")
):
    """
    分享文件转存
    
    严格按照官方文档实现：
    POST /apaas/1.0/share/transfer?product=netdisk&appid={appid}&access_token={access_token}
    """
    try:
        config = get_netdisk_config()
        if not config['access_token'] or not config['app_key']:
            raise HTTPException(status_code=500, detail="网盘配置不完整")
        
        # 构建请求URL - 严格按照官方文档
        url = "https://pan.baidu.com/apaas/1.0/share/transfer"
        
        # 构建请求参数 - 严格按照官方文档
        params = {
            'product': 'netdisk',
            'appid': config['app_key'],
            'access_token': config['access_token']
        }
        
        # 构建请求体 - 严格按照官方文档
        data = {
            'share_id': str(share_id),
            'pwd': pwd,
            'fsids': json.dumps(fsids),
            'dest_path': dest_path
        }
        
        # 发送请求
        response = requests.post(url, params=params, data=data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # 检查错误码
        if result.get('errno') != 0:
            error_msg = result.get('show_msg', '未知错误')
            raise HTTPException(status_code=400, detail=f"分享文件转存失败: {error_msg}")
        
        # 返回转存任务信息 - 严格按照官方文档的响应格式
        transfer_data = result.get('data', {})
        return JSONResponse({
            "status": "success",
            "message": "分享文件转存成功",
            "data": transfer_data,
            "request_id": result.get('request_id'),
            "errno": result.get('errno'),
            "show_msg": result.get('show_msg')
        })
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"网络请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分享文件转存时发生错误: {str(e)}")

@router.get("/download")
async def get_share_download_url(
    share_id: int = Query(..., description="分享ID"),
    pwd: str = Query(..., description="分享密码"),
    fsid: str = Query(..., description="文件ID")
):
    """
    获取分享文件下载地址
    
    严格按照官方文档实现：
    GET /apaas/1.0/share/download?product=netdisk&appid={appid}&access_token={access_token}&share_id={share_id}&pwd={pwd}&fsid={fsid}
    """
    try:
        config = get_netdisk_config()
        if not config['access_token'] or not config['app_key']:
            raise HTTPException(status_code=500, detail="网盘配置不完整")
        
        # 构建请求URL - 严格按照官方文档
        url = "https://pan.baidu.com/apaas/1.0/share/download"
        
        # 构建请求参数 - 严格按照官方文档
        params = {
            'product': 'netdisk',
            'appid': config['app_key'],
            'access_token': config['access_token'],
            'share_id': str(share_id),
            'pwd': pwd,
            'fsid': str(fsid)
        }
        
        # 发送请求
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # 检查错误码
        if result.get('errno') != 0:
            error_msg = result.get('show_msg', '未知错误')
            raise HTTPException(status_code=400, detail=f"获取分享下载地址失败: {error_msg}")
        
        # 返回下载地址信息 - 严格按照官方文档的响应格式
        download_data = result.get('data', {})
        return JSONResponse({
            "status": "success",
            "message": "获取分享下载地址成功",
            "data": download_data,
            "request_id": result.get('request_id'),
            "errno": result.get('errno'),
            "show_msg": result.get('show_msg')
        })
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"网络请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分享下载地址时发生错误: {str(e)}")

@router.get("/health")
async def share_health():
    """分享服务健康检查"""
    return JSONResponse({
        "status": "healthy",
        "service": "share-api",
        "timestamp": datetime.now().isoformat()
    })

@router.get("/help")
async def share_help():
    """分享API帮助信息"""
    return JSONResponse({
        "service": "百度网盘分享API",
        "version": "1.0",
        "description": "严格按照百度网盘官方文档实现的分享功能",
        "documentation": "https://pan.baidu.com/union/doc/Tlaaocmkj",
        "endpoints": {
            "create": {
                "method": "POST",
                "path": "/api/share/create",
                "description": "创建分享链接",
                "parameters": {
                    "fsid_list": "分享文件ID列表 (必填)",
                    "period": "分享有效期，单位天 (可选，默认7天)",
                    "pwd": "分享密码，4位数字+小写字母组成 (可选，自动生成)",
                    "remark": "分享备注 (可选)"
                }
            },
            "query": {
                "method": "GET",
                "path": "/api/share/query/{share_id}",
                "description": "查询分享详情",
                "parameters": {
                    "share_id": "分享ID (路径参数)"
                }
            },
            "transfer": {
                "method": "POST",
                "path": "/api/share/transfer",
                "description": "分享文件转存",
                "parameters": {
                    "share_id": "分享ID (必填)",
                    "pwd": "分享密码 (必填)",
                    "fsids": "要转存的文件ID列表 (必填)",
                    "dest_path": "转存目标路径 (可选，默认根目录)"
                }
            },
            "download": {
                "method": "GET",
                "path": "/api/share/download",
                "description": "获取分享文件下载地址",
                "parameters": {
                    "share_id": "分享ID (必填)",
                    "pwd": "分享密码 (必填)",
                    "fsid": "文件ID (必填)"
                }
            }
        },
        "examples": {
            "create_share": {
                "url": "POST /api/share/create",
                "body": {
                    "fsid_list": ["1234567890", "1234567891"],
                    "period": 7,
                    "pwd": "12zx",
                    "remark": "测试分享"
                }
            },
            "query_share": {
                "url": "GET /api/share/query/57999490044"
            },
            "transfer_files": {
                "url": "POST /api/share/transfer",
                "body": {
                    "share_id": 57999490044,
                    "pwd": "12zx",
                    "fsids": ["1234567890"],
                    "dest_path": "/我的文档"
                }
            },
            "get_download_url": {
                "url": "GET /api/share/download?share_id=57999490044&pwd=12zx&fsid=1234567890"
            }
        }
    })
