# Netdisk MCP Server 快速开始

## 5分钟快速部署

### 前置条件

- Python 3.8+
- 百度网盘API凭据（access_token等）

### 步骤1：安装依赖

```bash
pip install mcp fastmcp requests
```

### 步骤2：设置环境变量

```bash
export BAIDU_NETDISK_ACCESS_TOKEN="your_access_token"
export BAIDU_NETDISK_APP_KEY="your_app_key"
export BAIDU_NETDISK_REFRESH_TOKEN="your_refresh_token"
export BAIDU_NETDISK_SECRET_KEY="your_secret_key"
```

### 步骤3：启动服务器

#### 本地stdio模式（最简单）

```bash
python3 netdisk.py --transport stdio
```

#### TCP模式（远程访问）

```bash
# 启动服务器
python3 netdisk.py --transport tcp --tcp-host 0.0.0.0 --tcp-port 8765
```

### 步骤4：配置客户端

编辑客户端 `config.json`：

**本地stdio模式：**
```json
{
  "transport": {
    "mode": "mcp",
    "mcp": {
      "mode": "local-stdio",
      "stdio_binary": "python3",
      "entry": "../netdisk-mcp-server-stdio/netdisk.py"
    }
  }
}
```

**SSH隧道模式：**
```json
{
  "transport": {
    "mode": "mcp",
    "mcp": {
      "mode": "ssh-stdio",
      "ssh": {
        "host": "your-server.com",
        "user": "netdisk",
        "identity_file": "~/.ssh/id_rsa",
        "command": "python3 /opt/netdisk/netdisk.py --transport stdio"
      }
    }
  }
}
```

**TCP模式：**
```json
{
  "transport": {
    "mode": "mcp",
    "mcp": {
      "mode": "tcp",
      "tcp": {
        "host": "your-server.com",
        "port": 8765,
        "tls": false
      }
    }
  }
}
```

### 步骤5：启动客户端

```bash
cd pan_client
python3 main.py --use-mcp
```

## 命令行参数

### 服务器端

```bash
# 查看帮助
python3 netdisk.py --help

# stdio模式（默认）
python3 netdisk.py --transport stdio

# TCP模式
python3 netdisk.py --transport tcp --tcp-host 0.0.0.0 --tcp-port 8765

# TLS加密TCP
python3 netdisk.py --transport tcp \
  --tcp-host 0.0.0.0 \
  --tcp-port 8765 \
  --tls-cert /path/to/cert.pem \
  --tls-key /path/to/key.pem

# HTTP模式
python3 netdisk.py --transport http --http-host 0.0.0.0 --http-port 8000
```

### 客户端

```bash
# 使用MCP模式
python3 main.py --use-mcp

# 指定连接模式
python3 main.py --use-mcp --mcp-mode ssh

# 指定远程主机
python3 main.py --use-mcp --mcp-mode tcp --mcp-host mcp.example.com --mcp-port 8765

# 启用调试日志
python3 main.py --use-mcp --debug
```

## 常见场景

### 场景1：本地开发测试

```bash
# 服务器（终端1）
export BAIDU_NETDISK_ACCESS_TOKEN="..."
python3 netdisk.py --transport stdio

# 客户端（终端2）
cd pan_client
python3 main.py --use-mcp
```

### 场景2：远程服务器部署（SSH）

```bash
# 1. 在远程服务器上部署
ssh user@remote-server
cd /opt/netdisk
python3 netdisk.py --transport stdio

# 2. 配置客户端使用SSH连接
# 编辑config.json，设置mode为ssh-stdio

# 3. 启动客户端
python3 main.py --use-mcp
```

### 场景3：生产环境（TLS加密）

```bash
# 1. 生成TLS证书
openssl req -x509 -newkey rsa:4096 \
  -keyout server.key -out server.crt \
  -days 365 -nodes

# 2. 启动TLS服务器
python3 netdisk.py --transport tcp \
  --tcp-host 0.0.0.0 \
  --tcp-port 8765 \
  --tls-cert server.crt \
  --tls-key server.key

# 3. 配置客户端
# config.json中设置mode为tcp-tls，并配置cert_file和key_file

# 4. 启动客户端
python3 main.py --use-mcp --mcp-mode tcp --mcp-host your-server.com
```

## 验证连接

### 测试stdio连接

```bash
# 直接运行测试
python3 netdisk.py --transport stdio
# 应该看到 "启动stdio模式服务器"
```

### 测试TCP连接

```bash
# 方法1：使用telnet
telnet your-server.com 8765

# 方法2：使用nc（netcat）
nc -zv your-server.com 8765

# 方法3：使用Python
python3 -c "import socket; s=socket.socket(); s.connect(('your-server.com', 8765)); print('Connected')"
```

### 测试SSH连接

```bash
# 测试SSH访问
ssh netdisk@your-server.com "python3 /opt/netdisk/netdisk.py --transport stdio"
# 应该能正常启动
```

## 故障排查快速指南

### 问题1：连接被拒绝

```bash
# 检查服务器是否运行
ps aux | grep netdisk

# 检查端口是否监听
netstat -tulpn | grep 8765

# 检查防火墙
sudo ufw status
```

### 问题2：SSH连接失败

```bash
# 测试SSH密钥
ssh -i ~/.ssh/id_rsa netdisk@your-server.com

# 检查远程命令
ssh netdisk@your-server.com "which python3"
ssh netdisk@your-server.com "ls -la /opt/netdisk/netdisk.py"
```

### 问题3：环境变量未设置

```bash
# 检查环境变量
env | grep BAIDU

# 持久化环境变量（添加到~/.bashrc）
echo 'export BAIDU_NETDISK_ACCESS_TOKEN="..."' >> ~/.bashrc
source ~/.bashrc
```

### 问题4：TLS证书错误

```bash
# 验证证书
openssl x509 -in server.crt -text -noout

# 测试TLS连接
openssl s_client -connect your-server.com:8765
```

## 性能优化

### 服务器端

```bash
# 使用uvloop提升性能（可选）
pip install uvloop

# 增加工作进程（如果MCP支持）
# python3 netdisk.py --transport tcp --workers 4
```

### 客户端

```json
{
  "rate_limit": {
    "requests_per_minute": 60,
    "burst_size": 10
  },
  "timeout": 30
}
```

## 下一步

- 查看 [DEPLOYMENT.md](./DEPLOYMENT.md) 了解生产部署
- 查看 [README_MCP.md](../pan_client/README_MCP.md) 了解MCP模式详细文档
- 查看工具列表：运行客户端后在状态栏查看可用工具

## 获取帮助

- 查看日志：`journalctl -u netdisk-mcp-server -f`（systemd）
- 提交问题：[GitHub Issues](https://github.com/your-org/netdisk/issues)
- 社区支持：查看项目文档和Wiki

