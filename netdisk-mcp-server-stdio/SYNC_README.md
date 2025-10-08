# 目录同步功能使用说明

## 功能概述

目录同步功能允许您同步指定目录的所有文件信息，支持断点续传、频控和实时进度展示。

## 功能特性

- ✅ **断点续传**: 支持中断后继续同步
- ✅ **频控保护**: 自动控制API请求频率，避免触发限制
- ✅ **实时进度**: 前端实时显示同步进度和状态
- ✅ **任务管理**: 支持暂停、恢复、取消同步任务
- ✅ **日志记录**: 详细的同步日志和错误信息
- ✅ **数据库存储**: 使用SQLite存储同步进度和文件记录

## 使用方法

### 1. 前端管理界面

1. 打开管理后台 (`admin.html`)
2. 在侧边栏点击"目录同步"
3. 输入要同步的目录路径（如 `/` 或 `/某个文件夹`）
4. 点击"开始同步"按钮
5. 实时查看同步进度和日志

### 2. 独立同步脚本

```bash
# 基本用法
python sync_manager.py --path "/" --token "your_access_token" --client-id "your_client_id"

# 完整参数
python sync_manager.py \
  --path "/要同步的目录" \
  --token "your_access_token" \
  --client-id "your_client_id" \
  --base-url "http://localhost:8000" \
  --rate-limit 10
```

### 3. API接口

#### 启动同步
```http
POST /api/sync/start
Content-Type: application/json

{
  "path": "/",
  "client_id": "your_client_id"
}
```

#### 查询状态
```http
GET /api/sync/status/{sync_id}
```

#### 暂停同步
```http
POST /api/sync/pause/{sync_id}
```

#### 恢复同步
```http
POST /api/sync/resume/{sync_id}
```

#### 取消同步
```http
DELETE /api/sync/{sync_id}
```

## 配置参数

### 同步脚本配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--path` | 必需 | 要同步的目录路径 |
| `--token` | 必需 | 访问令牌 |
| `--client-id` | 必需 | 客户端ID |
| `--base-url` | `http://localhost:8000` | API服务器地址 |
| `--rate-limit` | `10` | 每分钟请求数限制 |

### 频控设置

- **默认限制**: 每分钟10个请求
- **时间窗口**: 60秒
- **自动等待**: 超出限制时自动等待

## 数据库结构

### sync_tasks 表
- `sync_id`: 同步任务ID
- `path`: 同步路径
- `status`: 任务状态 (running/completed/failed/paused)
- `total_files`: 总文件数
- `processed_files`: 已处理文件数
- `failed_files`: 失败文件数
- `start_time`: 开始时间
- `last_update`: 最后更新时间

### file_records 表
- `id`: 记录ID
- `sync_id`: 关联的同步任务ID
- `file_path`: 文件路径
- `file_size`: 文件大小
- `file_md5`: 文件MD5
- `modify_time`: 修改时间
- `status`: 处理状态
- `error_msg`: 错误信息

## 错误处理

### 常见错误

1. **频控错误 (31034)**: 自动重试，指数退避
2. **网络超时**: 自动重试，最多3次
3. **认证失败**: 检查token是否有效
4. **路径不存在**: 检查目录路径是否正确

### 日志文件

- 同步日志: `sync_manager.log`
- 数据库文件: `sync_progress.db`

## 注意事项

1. **首次同步**: 大目录首次同步可能需要较长时间
2. **网络稳定**: 确保网络连接稳定，避免中断
3. **存储空间**: 确保有足够的磁盘空间存储数据库
4. **权限问题**: 确保有读取目标目录的权限

## 故障排除

### 同步卡住
1. 检查网络连接
2. 查看日志文件
3. 尝试暂停后恢复
4. 检查API服务器状态

### 进度不更新
1. 刷新页面
2. 检查浏览器控制台错误
3. 确认API服务器正常运行

### 数据库错误
1. 检查文件权限
2. 确保磁盘空间充足
3. 尝试删除数据库文件重新开始

## 技术架构

- **后端**: FastAPI + SQLite
- **前端**: HTML + JavaScript + Tailwind CSS
- **同步脚本**: Python + requests + sqlite3
- **频控**: 自定义RateLimiter类
- **进度跟踪**: 数据库 + 轮询机制
