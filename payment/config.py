"""支付宝PC网站支付配置"""

# 应用配置
ALIPAY_F2F_CONFIG = {
    # 应用ID
    "app_id": "2021003138699127",
    
    # 是否使用沙箱环境
    "use_sandbox": False,  # 使用正式环境
    
    # 二维码配置
    "qr_code_config": {
        "box_size": 10,  # 二维码格子大小
        "border": 4,     # 二维码边框宽度
    }
}

# 网关地址
GATEWAY_URLS = {
    "sandbox": "https://openapi.alipaydev.com/gateway.do",    # 沙箱环境
    "production": "https://openapi.alipay.com/gateway.do"     # 生产环境
}

# 订单配置
ORDER_CONFIG = {
    "prefix": "ORDER",           # 订单号前缀
    "query_interval": 5,         # 查询间隔(秒)，建议3-5秒
    "max_query_times": 120,      # 最大查询次数，建议120次（等待6-10分钟）
    "timeout_express": "15m"     # 订单超时时间，建议15分钟
}

# 密钥文件路径
KEY_PATH_CONFIG = {
    "private_key_path": "private_key.pem",
    "public_key_path": "public_key.pem"
} 