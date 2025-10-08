#!/bin/bash
# 一键启动 MCP 回调服务（Ubuntu/Linux）
# - 使用 UTF-8 环境，避免中文乱码
# - 自动创建/启用虚拟环境（固定为项目内 .venv）
# - 自动安装依赖
# - 支持自定义端口（默认 8000），并释放占用

set -e  # 遇到错误立即退出

# 端口参数（默认 8000）
PORT=${1:-8000}

# 设置 UTF-8 环境
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo ""
echo "[1/6] 检查并释放 $PORT 端口占用..."
# 查找并终止占用端口的进程（lsof → fuser → ss 三重兜底）
PID=""
if command -v lsof >/dev/null 2>&1; then
    PID=$(lsof -ti:$PORT 2>/dev/null || true)
elif command -v fuser >/dev/null 2>&1; then
    PID=$(fuser -n tcp $PORT 2>/dev/null | awk '{print $1}' || true)
else
    if command -v ss >/dev/null 2>&1; then
        PID=$(ss -ltnp 2>/dev/null | awk -v p=:$PORT '$4 ~ p {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | head -n1 || true)
    fi
fi
if [ -n "$PID" ]; then
    echo "  - 终止进程 PID: $PID"
    kill -9 $PID 2>/dev/null || true
    sleep 1
fi

echo ""
echo "[2/6] 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "  - 错误: 未找到 python3，请先安装 Python 3.8+"
    echo "  - Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    echo "  - 使用国内镜像: sudo apt update -o Acquire::http::Proxy=\"http://mirrors.aliyun.com\""
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  - Python 版本: $PYTHON_VERSION"

echo ""
echo "[3/6] 检查虚拟环境..."
# 固定使用项目内 .venv 目录
VENV_DIR=${VENV_DIR:-"$(pwd)/.venv"}
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "  - 创建虚拟环境 $VENV_DIR"
    mkdir -p "$VENV_DIR" || true
    # 优先使用内置 venv（包含 ensurepip 的系统可直接用）
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        # 回退：尝试安装 virtualenv 后创建
        python3 -m pip --version >/dev/null 2>&1 || true
        python3 -m pip install --user -U virtualenv >/dev/null 2>&1 || true
        if command -v virtualenv >/dev/null 2>&1; then
            virtualenv "$VENV_DIR" || true
        fi
    fi
    if [ ! -f "$VENV_DIR/bin/activate" ]; then
        echo "  - 无法创建虚拟环境（缺少 ensurepip/pip）。请先安装 python3-venv 或 pip/virtualenv。"
        exit 1
    fi
fi

echo ""
echo "[4/6] 激活虚拟环境..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "  - 未找到 $VENV_DIR/bin/activate"
    exit 1
fi
source "$VENV_DIR/bin/activate"

echo ""
echo "[5/6] 安装依赖（如已安装将跳过）..."
# 确保 venv 内有 pip（若 ensurepip 缺失则跳过）
python -m pip --version >/dev/null 2>&1 || python -m ensurepip --upgrade 2>/dev/null || true

# 使用 pip 并配置镜像
python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
python -m pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn
python -m pip install -U pip setuptools wheel
if ! python -m pip install -r requirements.txt; then
    echo "requirements.txt 安装失败，回退安装核心依赖..."
    python -m pip install fastapi "uvicorn[standard]" python-dotenv requests urllib3 cryptography python-multipart
fi

echo ""
echo "[6/6] 启动服务（uvicorn）..."
# 允许通过环境变量覆盖 worker 数，默认为 2
UV_WORKERS=${UVICORN_WORKERS:-2}
UV_CMD="python -m uvicorn main:app --host 0.0.0.0 --port $PORT --workers $UV_WORKERS --reload --no-access-log --log-level warning"
echo "  - 命令: $UV_CMD"

echo ""
echo "========================================"
echo "服务启动完成！访问以下页面："
echo "========================================"
echo "API文档:      http://localhost:$PORT/docs"
echo "根路径:       http://localhost:$PORT/"
echo "管理界面:     http://localhost:$PORT/admin"
echo "同步状态:     http://localhost:$PORT/api/sync/status"
echo "数据库统计:   http://localhost:$PORT/api/sync/db-stats"
echo "========================================"

# 启动服务
exec $UV_CMD
