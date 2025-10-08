#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付服务层
包含支付配置管理、支付账户绑定等功能
"""

import sqlite3
import json
import base64
import os
import time
from typing import Dict, Any, Optional
from urllib.parse import urlencode, quote_plus
from datetime import datetime
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.fernet import Fernet
from .db import init_sync_db

# 加密密钥，从环境变量获取
_raw_key = os.getenv('PAYMENT_ENCRYPTION_KEY')
_allow_tmp = (os.getenv('ALLOW_TEMP_ENCRYPTION_KEY') or '').lower() == 'true'
if not _raw_key and not _allow_tmp:
    raise RuntimeError('PAYMENT_ENCRYPTION_KEY missing - 请设置加密密钥或允许临时密钥')
if not _raw_key and _allow_tmp:
    _raw_key = Fernet.generate_key().decode()
    print("警告: 使用临时加密密钥，生产环境请设置 PAYMENT_ENCRYPTION_KEY")
ENCRYPTION_KEY = _raw_key.encode() if isinstance(_raw_key, str) else _raw_key

def encrypt_sensitive_data(data: str) -> str:
    """加密敏感数据"""
    if not data:
        return ""
    try:
        f = Fernet(ENCRYPTION_KEY)
        encrypted_data = f.encrypt(data.encode())
        return base64.b64encode(encrypted_data).decode()
    except Exception as e:
        print(f"加密失败: {e}")
        return data

def decrypt_sensitive_data(encrypted_data: str) -> str:
    """解密敏感数据"""
    if not encrypted_data:
        return ""
    try:
        f = Fernet(ENCRYPTION_KEY)
        decoded_data = base64.b64decode(encrypted_data.encode())
        decrypted_data = f.decrypt(decoded_data)
        return decrypted_data.decode()
    except Exception as e:
        print(f"解密失败: {e}")
        return encrypted_data

def load_platform_payment_config(provider: str) -> Optional[Dict[str, str]]:
    """加载平台支付配置

    优先从环境变量读取（路径或Base64），否则读取数据库加密存储。
    支持变量：
    - ALIPAY_PRIVATE_KEY_PATH / ALIPAY_PUBLIC_KEY_PATH（PEM 文件路径）
    - ALIPAY_PRIVATE_KEY_B64 / ALIPAY_PUBLIC_KEY_B64（PEM Base64 单行）
    - 仅当 provider == 'alipay' 时生效。
    """
    if provider == 'alipay':
        # 1) 路径优先
        priv_path = os.getenv('ALIPAY_PRIVATE_KEY_PATH')
        pub_path = os.getenv('ALIPAY_PUBLIC_KEY_PATH')
        if priv_path and pub_path and os.path.exists(priv_path) and os.path.exists(pub_path):
            try:
                with open(priv_path, 'r', encoding='utf-8') as f:
                    priv = f.read()
                with open(pub_path, 'r', encoding='utf-8') as f:
                    pub = f.read()
                return {"public_key": pub, "private_key": priv, "status": "active", "source": "env:path"}
            except Exception as e:
                print(f"读取支付宝密钥文件失败: {e}")
        # 2) Base64 其次
        priv_b64 = os.getenv('ALIPAY_PRIVATE_KEY_B64')
        pub_b64 = os.getenv('ALIPAY_PUBLIC_KEY_B64')
        if priv_b64 and pub_b64:
            try:
                priv = base64.b64decode(priv_b64).decode('utf-8')
                pub = base64.b64decode(pub_b64).decode('utf-8')
                return {"public_key": pub, "private_key": priv, "status": "active", "source": "env:b64"}
            except Exception as e:
                print(f"解码支付宝密钥Base64失败: {e}")
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT public_key, private_key, status
            FROM platform_payment_configs
            WHERE provider = ? AND status = 'active'
        ''', (provider,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        public_key, private_key, status = row
        
        return {
            "public_key": decrypt_sensitive_data(public_key),
            "private_key": decrypt_sensitive_data(private_key),
            "status": status
        }
    except Exception as e:
        print(f"加载平台支付配置失败: {e}")
        return None
    finally:
        conn.close()

def save_platform_payment_config(provider: str, public_key: str, private_key: str, admin_id: str = "system") -> Dict[str, Any]:
    """保存平台支付配置"""
    # 导入风控服务
    from .risk_service import check_rate_limit
    
    # 检查频控（管理员操作限制）
    rate_limit_result = check_rate_limit(admin_id, 'payment_config')
    if not rate_limit_result.get('allowed', False):
        return {"status": "error", "message": rate_limit_result.get('message', '操作过于频繁')}
    
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查是否已存在
        cursor.execute('SELECT id FROM platform_payment_configs WHERE provider = ?', (provider,))
        existing = cursor.fetchone()
        
        if existing:
            # 更新现有配置
            cursor.execute('''
                UPDATE platform_payment_configs 
                SET public_key = ?, private_key = ?, updated_at = ?, status = 'active'
                WHERE provider = ?
            ''', (
                encrypt_sensitive_data(public_key),
                encrypt_sensitive_data(private_key),
                time.time(),
                provider
            ))
            message = "payment config updated"
        else:
            # 创建新配置
            cursor.execute('''
                INSERT INTO platform_payment_configs (provider, public_key, private_key, status)
                VALUES (?, ?, ?, 'active')
            ''', (
                provider,
                encrypt_sensitive_data(public_key),
                encrypt_sensitive_data(private_key)
            ))
            message = "payment config created"
        
        conn.commit()
        return {"status": "success", "message": message}
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def bind_payment_account(user_id: str, provider: str, account_no: str, 
                       account_name: Optional[str] = None) -> Dict[str, Any]:
    """
    绑定支付账户，支持支付宝等支付渠道
    密钥完全从平台配置中获取，用户只需提供账户信息
    """
    if not user_id or not provider or not account_no:
        return {"status": "error", "message": "missing parameters"}

    provider = provider.lower()

    # 检查平台是否已配置该支付渠道
    platform_config = load_platform_payment_config(provider)
    if not platform_config:
        return {"status": "error", "message": f"platform not configured for {provider}"}

    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO payment_accounts (user_id, provider, account_no, account_name, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', (user_id, provider, account_no, account_name))
        
        conn.commit()
        return {"status": "success", "message": "payment account bound"}
        
    except Exception as exc:
        conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()

def process_payment_transaction(provider: str, amount: float, order_id: str) -> Dict[str, Any]:
    """
    处理支付交易的示例函数
    展示如何使用平台配置进行支付操作
    """
    payment_config = load_platform_payment_config(provider)
    
    if not payment_config:
        return {
            "status": "error",
            "message": f"未找到支付配置: {provider}"
        }
    
    public_key = payment_config["public_key"]
    private_key = payment_config["private_key"]
    
    print(f"使用平台配置处理支付: {provider}, 金额: {amount}, 订单: {order_id}")
    # 注意：不输出密钥信息，避免敏感数据泄露
    
    # 这里可以集成真实的支付SDK
    # 例如支付宝SDK、微信支付SDK等
    
    return {
        "status": "success",
        "message": "支付处理完成",
        "payment_config": {
            "provider": provider,
            "amount": amount,
            "order_id": order_id,
            "has_valid_keys": bool(public_key and private_key)
        }
    }


# =============== Alipay 无回调前端轮询：页面支付与查询 ===============

def _rsa2_sign(content: str, private_key_pem: str) -> str:
    key = load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
    signature = key.sign(
        content.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def _ordered_query(params: Dict[str, Any]) -> str:
    # 以 key 的字典序排序，值保持原文，不做 url 编码
    items = [(k, params[k]) for k in sorted(params.keys()) if params[k] is not None and k != 'sign']
    return "&".join([f"{k}={v}" for k, v in items])

def create_alipay_page_pay(subject: str, total_amount: float, out_trade_no: str) -> Dict[str, Any]:
    """生成 PC 网页支付链接（FAST_INSTANT_TRADE_PAY），无回调场景。

    返回: { status, pay_url, gateway }
    """
    try:
        cfg = load_platform_payment_config('alipay') or {}
        private_key = (cfg.get('private_key') or '').strip()
        if not private_key:
            return {"status": "error", "message": "missing private key"}

        app_id = os.getenv('ALIPAY_APP_ID') or ''
        if not app_id:
            return {"status": "error", "message": "missing ALIPAY_APP_ID"}
        gateway = os.getenv('ALIPAY_GATEWAY') or 'https://openapi.alipay.com/gateway.do'

        # 通用参数
        common = {
            'app_id': app_id,
            'method': 'alipay.trade.page.pay',
            'format': 'JSON',
            'charset': 'utf-8',
            'sign_type': 'RSA2',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'version': '1.0',
        }
        # 仅当配置不为空时才附带 return/notify
        ret = (os.getenv('PAY_RETURN_URL') or '').strip()
        noti = (os.getenv('PAY_NOTIFY_URL') or '').strip()
        if ret:
            common['return_url'] = ret
        if noti:
            common['notify_url'] = noti
        biz_content = {
            'out_trade_no': out_trade_no,
            'product_code': 'FAST_INSTANT_TRADE_PAY',
            'total_amount': str(round(float(total_amount), 2)),
            'subject': subject,
            # 可按需扩展: 'timeout_express': '15m'
        }
        params = dict(common)
        params['biz_content'] = json.dumps(biz_content, ensure_ascii=False, separators=(',', ':'))

        # 签名
        unsigned = _ordered_query(params)
        sign = _rsa2_sign(unsigned, private_key)
        params['sign'] = sign

        # 生成最终 URL（参数需 url 编码）
        # 按支付宝规范，sign 也需要 url 编码
        query = urlencode({k: params[k] for k in params}, quote_via=quote_plus)
        pay_url = f"{gateway}?{query}"
        return {"status": "success", "pay_url": pay_url, "gateway": gateway}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def query_alipay_trade(out_trade_no: str) -> Dict[str, Any]:
    """服务端查询交易结果（alipay.trade.query）。返回 {status, paid, raw}。"""
    try:
        cfg = load_platform_payment_config('alipay') or {}
        private_key = (cfg.get('private_key') or '').strip()
        if not private_key:
            return {"status": "error", "message": "missing private key"}
        app_id = os.getenv('ALIPAY_APP_ID') or ''
        if not app_id:
            return {"status": "error", "message": "missing ALIPAY_APP_ID"}
        gateway = os.getenv('ALIPAY_GATEWAY') or 'https://openapi.alipay.com/gateway.do'

        common = {
            'app_id': app_id,
            'method': 'alipay.trade.query',
            'format': 'JSON',
            'charset': 'utf-8',
            'sign_type': 'RSA2',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'version': '1.0',
        }
        biz_content = {
            'out_trade_no': out_trade_no,
        }
        params = dict(common)
        params['biz_content'] = json.dumps(biz_content, ensure_ascii=False, separators=(',', ':'))
        unsigned = _ordered_query(params)
        sign = _rsa2_sign(unsigned, private_key)
        params['sign'] = sign

        # 按官方要求使用 x-www-form-urlencoded POST
        import requests
        resp = requests.post(gateway, data=params, timeout=10)
        if not resp.ok:
            return {"status": "error", "message": resp.text}
        data = resp.json()
        body = data.get('alipay_trade_query_response') or {}
        code = str(body.get('code'))
        paid = (body.get('trade_status') == 'TRADE_SUCCESS')
        return {"status": "success" if code == '10000' else "error", "paid": paid, "raw": body}
    except Exception as e:
        return {"status": "error", "message": str(e)}
