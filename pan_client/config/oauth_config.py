"""
百度OAuth配置
"""

# 百度开发者应用配置
# 需要在百度开发者中心注册应用获取以下信息
BAIDU_OAUTH_CONFIG = {
    # 应用信息 - 需要替换为真实值
    'client_id': 'K7G1wG60FhUOSGHG4eC4JxcYTPODWGfO',
    'client_secret': 'ZgBe3U3ttrfQgk0q1XurOSACuyvz72a4',
    
    # 授权回调地址 - 需要配置为真实可访问的地址
    'redirect_uri': 'http://124.223.185.27/auth/callback',
    
    # OAuth相关URL
    'auth_url': 'https://openapi.baidu.com/oauth/2.0/authorize',
    'token_url': 'https://openapi.baidu.com/oauth/2.0/token',
    'user_info_url': 'https://openapi.baidu.com/rest/2.0/passport/users/getInfo',
    
    # 授权参数
    'scope': 'basic',  # 基础权限
    'display': 'popup',  # 适用于桌面软件应用
    
    # 二维码配置
    'qrcode_width': 200,
    'qrcode_height': 200,
    
    # 轮询配置
    'poll_interval': 2000,  # 2秒轮询一次
    'max_poll_time': 300000,  # 5分钟超时
}

# 开发环境配置
DEVELOPMENT_CONFIG = {
    'debug': True,
    'log_level': 'DEBUG',
}

# 生产环境配置
PRODUCTION_CONFIG = {
    'debug': False,
    'log_level': 'INFO',
}

def get_oauth_config():
    """获取OAuth配置"""
    return BAIDU_OAUTH_CONFIG.copy()

def get_development_config():
    """获取开发环境配置"""
    return DEVELOPMENT_CONFIG.copy()

def get_production_config():
    """获取生产环境配置"""
    return PRODUCTION_CONFIG.copy()
