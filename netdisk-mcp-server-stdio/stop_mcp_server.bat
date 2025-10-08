@echo off
REM 关闭 MCP 回调服务（Windows）
chcp 65001 >nul

echo 查找占用 8000 端口的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  echo 终止进程 PID: %%a
  taskkill /PID %%a /F >nul 2>nul
)

echo 同时尝试按进程名结束（uvicorn/auth_server.py）...
taskkill /F /IM uvicorn.exe >nul 2>nul
taskkill /F /IM python.exe /T >nul 2>nul

echo 完成。如仍占用，请手动检查：netstat -ano ^| findstr :8000
pause


