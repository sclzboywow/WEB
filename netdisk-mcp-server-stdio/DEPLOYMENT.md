# Netdisk MCP Server 部署指南

## 概述

本文档介绍如何在生产环境中部署 Netdisk MCP Server，支持多种传输模式：stdio、TCP、TLS加密TCP。

## 系统要求

- Python 3.8+
- Linux 服务器（推荐 Ubuntu 20.04+ 或 CentOS 8+）
- 网络连接（用于访问百度网盘API）
- 足够的磁盘空间用于临时文件缓存

## 安装步骤

### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv /opt/netdisk/venv
source /opt/netdisk/venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

创建环境变量文件 `/opt/netdisk/.env`：

```bash
# 百度网盘API凭据
export BAIDU_NETDISK_ACCESS_TOKEN="your_access_token"
export BAIDU_NETDISK_APP_KEY="your_app_key"
export BAIDU_NETDISK_REFRESH_TOKEN="your_refresh_token"
export BAIDU_NETDISK_SECRET_KEY="your_secret_key"

# 可选：MCP认证令牌（用于TCP模式）
export MCP_AUTH_TOKEN="your_secure_token"
```

### 3. 创建系统用户

```bash
# 创建专用用户
sudo useradd -r -s /bin/bash -d /opt/netdisk netdisk
sudo chown -R netdisk:netdisk /opt/netdisk
```

## 部署模式

### 模式1：stdio 模式（本地调用）

适合客户端与服务器在同一台机器上运行。

```bash
python3 netdisk.py --transport stdio
```

### 模式2：TCP 模式（纯TCP）

适合内网环境，客户端与服务器分离部署。

```bash
python3 netdisk.py --transport tcp --tcp-host 0.0.0.0 --tcp-port 8765
```

**注意**：纯TCP模式不加密，不建议在公网使用。

### 模式3：TLS 加密TCP模式（推荐用于生产）

适合公网或需要安全通信的场景。

#### 生成TLS证书

```bash
# 使用 Let's Encrypt（推荐）
sudo apt install certbot
sudo certbot certonly --standalone -d mcp.yourdomain.com

# 或自签名证书（仅用于测试）
openssl req -x509 -newkey rsa:4096 -keyout /etc/ssl/private/mcp-server.key \
  -out /etc/ssl/certs/mcp-server.crt -days 365 -nodes
```

#### 启动TLS服务器

```bash
python3 netdisk.py --transport tcp \
  --tcp-host 0.0.0.0 \
  --tcp-port 8765 \
  --tls-cert /etc/ssl/certs/mcp-server.crt \
  --tls-key /etc/ssl/private/mcp-server.key
```

## systemd 服务配置

### 创建服务文件

创建 `/etc/systemd/system/netdisk-mcp-server.service`：

```ini
[Unit]
Description=Netdisk MCP Server
After=network.target
Documentation=https://github.com/your-org/netdisk-mcp-server

[Service]
Type=simple
User=netdisk
Group=netdisk
WorkingDirectory=/opt/netdisk/netdisk-mcp-server-stdio

# 加载环境变量
EnvironmentFile=/opt/netdisk/.env

# 启动命令（根据需要选择模式）
# TCP模式
ExecStart=/opt/netdisk/venv/bin/python3 netdisk.py --transport tcp --tcp-host 0.0.0.0 --tcp-port 8765

# TLS模式（推荐）
# ExecStart=/opt/netdisk/venv/bin/python3 netdisk.py --transport tcp --tcp-host 0.0.0.0 --tcp-port 8765 --tls-cert /etc/ssl/certs/mcp-server.crt --tls-key /etc/ssl/private/mcp-server.key

# 自动重启
Restart=always
RestartSec=5

# 安全加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/netdisk
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=netdisk-mcp

[Install]
WantedBy=multi-user.target
```

### 启动服务

```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable netdisk-mcp-server

# 启动服务
sudo systemctl start netdisk-mcp-server

# 查看状态
sudo systemctl status netdisk-mcp-server

# 查看日志
sudo journalctl -u netdisk-mcp-server -f
```

## Supervisor 配置（备选）

如果使用 Supervisor 管理进程：

创建 `/etc/supervisor/conf.d/netdisk-mcp-server.conf`：

```ini
[program:netdisk-mcp-server]
command=/opt/netdisk/venv/bin/python3 /opt/netdisk/netdisk-mcp-server-stdio/netdisk.py --transport tcp --tcp-host 0.0.0.0 --tcp-port 8765
directory=/opt/netdisk/netdisk-mcp-server-stdio
user=netdisk
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/netdisk-mcp-server.log
environment=BAIDU_NETDISK_ACCESS_TOKEN="%(ENV_BAIDU_NETDISK_ACCESS_TOKEN)s",BAIDU_NETDISK_APP_KEY="%(ENV_BAIDU_NETDISK_APP_KEY)s",BAIDU_NETDISK_REFRESH_TOKEN="%(ENV_BAIDU_NETDISK_REFRESH_TOKEN)s",BAIDU_NETDISK_SECRET_KEY="%(ENV_BAIDU_NETDISK_SECRET_KEY)s"
```

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start netdisk-mcp-server
```

## 网络配置

### 防火墙规则

#### UFW（Ubuntu）

```bash
# 允许MCP端口
sudo ufw allow 8765/tcp

# 查看规则
sudo ufw status
```

#### firewalld（CentOS/RHEL）

```bash
# 允许MCP端口
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload

# 查看规则
sudo firewall-cmd --list-all
```

#### iptables

```bash
# 允许MCP端口
sudo iptables -A INPUT -p tcp --dport 8765 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4
```

### Nginx 反向代理（可选）

如果需要通过Nginx进行反向代理：

```nginx
upstream mcp_backend {
    server 127.0.0.1:8765;
}

server {
    listen 443 ssl http2;
    server_name mcp.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/mcp.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://mcp_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 监控与日志

### 日志位置

- **systemd**: `journalctl -u netdisk-mcp-server`
- **Supervisor**: `/var/log/supervisor/netdisk-mcp-server.log`

### 日志轮转

创建 `/etc/logrotate.d/netdisk-mcp-server`：

```
/var/log/supervisor/netdisk-mcp-server.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    missingok
    postrotate
        supervisorctl restart netdisk-mcp-server > /dev/null
    endscript
}
```

### 性能监控

使用 `htop` 或 `top` 监控资源使用：

```bash
# 查看进程资源使用
ps aux | grep netdisk

# 实时监控
htop -p $(pgrep -f netdisk.py)
```

## 故障排查

### 常见问题

#### 1. 连接被拒绝

```bash
# 检查服务是否运行
sudo systemctl status netdisk-mcp-server

# 检查端口是否监听
sudo netstat -tulpn | grep 8765
# 或
sudo ss -tulpn | grep 8765
```

#### 2. TLS证书错误

```bash
# 验证证书
openssl s_client -connect mcp.yourdomain.com:8765

# 检查证书权限
ls -la /etc/ssl/certs/mcp-server.crt
ls -la /etc/ssl/private/mcp-server.key
```

#### 3. 环境变量未加载

```bash
# 检查环境变量
sudo systemctl show netdisk-mcp-server -p Environment

# 手动测试
source /opt/netdisk/.env
python3 netdisk.py --transport stdio
```

### 调试模式

启用详细日志：

```bash
# 临时启用调试
export LOG_LEVEL=DEBUG
python3 netdisk.py --transport tcp --tcp-host 0.0.0.0 --tcp-port 8765
```

## 安全建议

1. **使用TLS加密**：生产环境必须使用TLS
2. **限制访问**：使用防火墙限制只允许客户端IP访问
3. **定期更新证书**：使用Let's Encrypt自动续期
4. **安全存储凭据**：使用环境变量或密钥管理服务
5. **最小权限原则**：使用专用用户运行服务
6. **监控日志**：定期检查异常访问

## 备份与恢复

### 备份配置

```bash
# 备份配置和环境变量
tar -czf netdisk-backup-$(date +%Y%m%d).tar.gz \
  /opt/netdisk/.env \
  /etc/systemd/system/netdisk-mcp-server.service
```

### 恢复

```bash
# 解压备份
tar -xzf netdisk-backup-YYYYMMDD.tar.gz -C /

# 重启服务
sudo systemctl daemon-reload
sudo systemctl restart netdisk-mcp-server
```

## 升级指南

```bash
# 停止服务
sudo systemctl stop netdisk-mcp-server

# 备份当前版本
cp -r /opt/netdisk/netdisk-mcp-server-stdio /opt/netdisk/netdisk-mcp-server-stdio.bak

# 拉取最新代码
cd /opt/netdisk/netdisk-mcp-server-stdio
git pull origin main

# 更新依赖
source /opt/netdisk/venv/bin/activate
pip install -r requirements.txt --upgrade

# 重启服务
sudo systemctl start netdisk-mcp-server

# 验证
sudo systemctl status netdisk-mcp-server
```

## 支持

如有问题，请：
1. 查看日志文件
2. 检查GitHub Issues
3. 提交问题报告时包含：
   - 系统信息
   - 错误日志
   - 配置文件（隐藏敏感信息）

