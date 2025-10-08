#!/bin/bash
# Ubuntu 环境配置脚本 - 使用国内镜像源
# 配置 apt 和 pip 使用国内镜像，加速安装

set -e

echo "========================================"
echo "Ubuntu 环境配置 - 使用国内镜像源"
echo "========================================"

# 配置 apt 使用阿里云镜像
echo ""
echo "[1/4] 配置 apt 使用阿里云镜像源..."
sudo cp /etc/apt/sources.list /etc/apt/sources.list.backup
sudo tee /etc/apt/sources.list > /dev/null <<EOF
# 阿里云镜像源
deb http://mirrors.aliyun.com/ubuntu/ $(lsb_release -cs) main restricted universe multiverse
deb http://mirrors.aliyun.com/ubuntu/ $(lsb_release -cs)-security main restricted universe multiverse
deb http://mirrors.aliyun.com/ubuntu/ $(lsb_release -cs)-updates main restricted universe multiverse
deb http://mirrors.aliyun.com/ubuntu/ $(lsb_release -cs)-proposed main restricted universe multiverse
deb http://mirrors.aliyun.com/ubuntu/ $(lsb_release -cs)-backports main restricted universe multiverse
EOF

echo ""
echo "[2/4] 更新 apt 包列表..."
sudo apt update

echo ""
echo "[3/4] 安装 Python 开发环境..."
sudo apt install -y python3 python3-pip python3-venv python3-dev build-essential

echo ""
echo "[4/4] 配置 pip 使用清华大学镜像源..."
mkdir -p ~/.pip
cat > ~/.pip/pip.conf <<EOF
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
EOF

echo ""
echo "========================================"
echo "配置完成！"
echo "========================================"
echo "apt 镜像源: 阿里云"
echo "pip 镜像源: 清华大学"
echo ""
echo "现在可以运行: ./start_mcp_server.sh"
echo "========================================"
