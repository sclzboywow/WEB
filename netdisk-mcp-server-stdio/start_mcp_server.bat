@echo off
REM 一键启动 MCP 回调服务（Windows）
REM - 使用 UTF-8 控制台，避免中文乱码
REM - 自动创建/启用虚拟环境
REM - 自动安装依赖
REM - 支持自定义端口（默认 8000），并释放占用

chcp 65001 >nul
setlocal enabledelayedexpansion

REM 端口参数（默认 8000）
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"

REM Python UTF-8 环境
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM 切换到当前脚本所在目录（即 netdisk-mcp-server-stdio）
cd /d "%~dp0"

echo.
echo [1/5] 检查并释放 %PORT% 端口占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
  echo  - 终止进程 PID: %%a
  taskkill /PID %%a /F >nul 2>nul
)

echo.
echo [2/5] 检查虚拟环境...
if not exist .venv\Scripts\python.exe (
  echo  - 创建虚拟环境 .venv
  python -m venv .venv
)

echo.
echo [3/5] 激活虚拟环境...
call .venv\Scripts\activate.bat

echo.
echo [4/5] 安装依赖（如已安装将跳过）...
REM 确保 venv 内有 pip
".venv\Scripts\python.exe" -m pip --version >nul 2>nul || ".venv\Scripts\python.exe" -m ensurepip --upgrade
".venv\Scripts\python.exe" -m pip install -U pip setuptools wheel

REM 优先用 requirements.txt；如果失败（例如 mcp 不支持当前平台），回退安装核心依赖
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (
  echo requirements.txt 安装失败，回退安装核心依赖...
  ".venv\Scripts\python.exe" -m pip install fastapi "uvicorn[standard]" python-dotenv requests urllib3 cryptography python-multipart
)

echo.
echo [5/5] 启动服务（uvicorn）...
set "UV_CMD=.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port %PORT% --workers 1 --reload --no-access-log --log-level warning"
echo  - 命令: %UV_CMD%

REM 在新控制台窗口中启动，便于查看日志；如需当前窗口前台运行，改为直接执行 %UV_CMD%
start "MCP Server" cmd /k "%UV_CMD%"

echo.
echo 启动命令已发送。在新打开的控制台窗口中查看运行日志。
echo.
echo ========================================
echo 服务启动完成！访问以下页面：
echo ========================================
echo 商品市场:     http://localhost:%PORT%/market.html
echo 我的订单:     http://localhost:%PORT%/user.html  
echo 卖家中心:     http://localhost:%PORT%/seller.html
echo 管理后台:     http://localhost:%PORT%/admin
echo 登录页面:     http://localhost:%PORT%/login
echo API文档:      http://localhost:%PORT%/docs
echo 功能测试:     http://localhost:%PORT%/test_buyer_complete.html
echo 系统状态:     http://localhost:%PORT%/status.html
echo 对账报告API:  http://localhost:%PORT%/api/reports/finance/reconcile
echo DB统计API:    http://localhost:%PORT%/api/sync/db-stats
echo ========================================
echo.
echo 新功能说明：
echo - 商品市场：浏览商品、下单购买、查看订单
echo - 卖家中心：上架商品、管理订单、收益提现
echo - 管理后台：审核商品、处理提现、系统管理
echo - 通知系统：支付成功、审核结果等实时通知
echo.
pause


