# 百度OAuth扫码登录配置指南

## 概述

本指南将帮助您配置百度OAuth扫码登录功能，实现客户端与百度网盘的集成登录。

## 前置条件

1. 百度开发者账号
2. 已注册的百度开发者应用
3. 配置好的授权回调地址

## 配置步骤

### 1. 注册百度开发者应用

1. 访问 [百度开发者中心](https://developer.baidu.com/)
2. 登录您的百度账号
3. 创建新应用或选择现有应用
4. 记录以下信息：
   - `API Key` (client_id)
   - `Secret Key` (client_secret)

### 2. 配置授权回调地址

1. 在开发者中心进入应用管理页面
2. 点击需要配置的应用
3. 进入"安全设置"页面
4. 添加授权回调地址：
   ```
   http://localhost:8080/oauth/callback
   ```

### 3. 配置客户端

编辑 `pan_client/config/oauth_config.py` 文件：

```python
BAIDU_OAUTH_CONFIG = {
    # 替换为您的真实应用信息
    'client_id': 'your_real_client_id',
    'client_secret': 'your_real_client_secret',
    
    # 授权回调地址
    'redirect_uri': 'http://localhost:8080/oauth/callback',
    
    # 其他配置保持不变
    'scope': 'basic',
    'display': 'popup',
    'qrcode_width': 200,
    'qrcode_height': 200,
    'poll_interval': 2000,
    'max_poll_time': 300000,
}
```

### 4. 启动应用

1. 确保OAuth回调服务器可以正常启动（端口8080）
2. 启动客户端应用
3. 点击"我的信息"按钮打开登录对话框
4. 使用手机扫描二维码完成登录

## 技术实现

### 核心组件

1. **BaiduOAuthClient**: OAuth客户端核心类
2. **BaiduOAuthWorker**: 异步OAuth工作线程
3. **OAuthCallbackServer**: 回调服务器
4. **LoginDialog**: 登录界面

### 工作流程

1. 用户点击登录按钮
2. 生成授权URL和二维码
3. 启动OAuth回调服务器
4. 用户扫码授权
5. 获取授权码
6. 换取access_token
7. 获取用户信息
8. 完成登录

### 安全特性

- 使用state参数防止CSRF攻击
- 支持token自动刷新
- 安全的回调地址验证
- 错误处理和超时机制

## 错误处理

### 常见错误码

根据[百度OAuth错误码文档](https://openauth.baidu.com/doc/appendix.html)：

- `invalid_client`: 客户端ID或密钥无效
- `invalid_grant`: 授权码无效或已过期
- `redirect_uri_mismatch`: 回调地址不匹配
- `access_denied`: 用户拒绝授权

### 调试建议

1. 检查网络连接
2. 验证应用配置
3. 确认回调地址可访问
4. 查看控制台日志输出

## 注意事项

1. **开发环境**: 使用localhost作为回调地址
2. **生产环境**: 需要配置真实的域名和HTTPS
3. **权限申请**: 某些用户信息需要额外申请权限
4. **Token管理**: 妥善保存refresh_token用于自动刷新

## 相关文档

- [百度OAuth接入指南](https://openauth.baidu.com/doc/doc.html)
- [OAuth错误码列表](https://openauth.baidu.com/doc/appendix.html)
- [OpenID介绍](https://openauth.baidu.com/doc/openid.html)

## 支持

如遇到问题，请检查：
1. 应用配置是否正确
2. 网络连接是否正常
3. 回调服务器是否启动
4. 查看详细错误日志
