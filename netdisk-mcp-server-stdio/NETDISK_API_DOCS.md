# 网盘API文档

## 概述

网盘API提供了完整的百度网盘文件管理功能，包括文件上传、下载、搜索、用户信息查询等。所有API都支持频率限制和错误处理。

## 基础信息

- **基础URL**: `http://localhost:8000/api/netdisk`
- **认证方式**: 需要配置百度网盘API密钥和访问令牌
- **频率限制**: 内置智能频率控制，避免API调用超限
- **错误处理**: 完整的错误处理和重试机制

## API端点

### 1. 文件管理

#### 1.1 列出文件
```http
GET /api/netdisk/files
```

**参数:**
- `path` (string, 可选): 网盘路径，默认为根目录 "/"
- `start` (int, 可选): 起始位置，默认为0
- `limit` (int, 可选): 返回数量限制，默认为100，最大200

**响应示例:**
```json
{
  "status": "success",
  "message": "获取文件列表成功",
  "path": "/",
  "total": 10,
  "files": [
    {
      "name": "文档.pdf",
      "path": "/文档.pdf",
      "size": 1024000,
      "isdir": 0,
      "fs_id": "1234567890",
      "create_time": 1640995200,
      "modify_time": 1640995200,
      "md5": "abc123def456",
      "category": "4"
    }
  ],
  "has_more": false,
  "page_info": {
    "start": 0,
    "limit": 100,
    "page_full": false
  }
}
```

#### 1.2 列出目录
```http
GET /api/netdisk/directories
```

**参数:**
- `path` (string, 可选): 网盘路径，默认为根目录 "/"
- `start` (int, 可选): 起始位置，默认为0
- `limit` (int, 可选): 返回数量限制，默认为100，最大200

**响应示例:**
```json
{
  "status": "success",
  "message": "获取目录列表成功",
  "path": "/",
  "total": 3,
  "directories": [
    {
      "name": "我的文档",
      "path": "/我的文档",
      "size": 0,
      "isdir": 1,
      "fs_id": "1234567891",
      "create_time": 1640995200,
      "modify_time": 1640995200,
      "md5": "",
      "category": "0"
    }
  ],
  "has_more": false
}
```

#### 1.3 上传文件
```http
POST /api/netdisk/upload
```

**参数:**
- `file` (file, 必需): 要上传的文件（multipart/form-data）
- `remote_path` (string, 可选): 网盘存储路径，如不指定将使用默认路径

**响应示例:**
```json
{
  "status": "success",
  "message": "文件上传成功",
  "filename": "test.pdf",
  "size": 1024000,
  "remote_path": "/来自：mcp_server/test.pdf",
  "fs_id": "1234567890",
  "md5": "abc123def456"
}
```

#### 1.4 搜索文件
```http
GET /api/netdisk/search
```

**参数:**
- `keyword` (string, 必需): 搜索关键词
- `path` (string, 可选): 搜索路径，默认为根目录 "/"
- `start` (int, 可选): 起始位置，默认为0
- `limit` (int, 可选): 返回数量限制，默认为100，最大200

**响应示例:**
```json
{
  "status": "success",
  "message": "文件搜索成功",
  "keyword": "test",
  "search_path": "/",
  "total": 5,
  "files": [
    {
      "name": "test.pdf",
      "path": "/test.pdf",
      "size": 1024000,
      "isdir": 0,
      "fs_id": "1234567890",
      "create_time": 1640995200,
      "modify_time": 1640995200,
      "md5": "abc123def456",
      "category": "4"
    }
  ],
  "has_more": false
}
```

### 2. 用户信息

#### 2.1 获取用户信息
```http
GET /api/netdisk/user/info
```

**响应示例:**
```json
{
  "status": "success",
  "message": "获取用户信息成功",
  "user_info": {
    "baidu_name": "用户名",
    "netdisk_name": "网盘用户名",
    "avatar_url": "https://example.com/avatar.jpg",
    "vip_type": 1,
    "vip_level": 3,
    "uk": 123456789
  }
}
```

#### 2.2 获取配额信息
```http
GET /api/netdisk/user/quota
```

**响应示例:**
```json
{
  "status": "success",
  "message": "获取配额信息成功",
  "quota_info": {
    "total": 2147483648,
    "used": 1073741824,
    "free": 1073741824,
    "usage_percent": 50.0,
    "total_gb": 2.0,
    "used_gb": 1.0,
    "free_gb": 1.0
  }
}
```

### 3. 多媒体文件

#### 3.1 列出多媒体文件
```http
GET /api/netdisk/multimedia
```

**参数:**
- `path` (string, 可选): 搜索路径，默认为根目录 "/"
- `recursion` (int, 可选): 是否递归搜索，1为是，0为否，默认为1
- `start` (int, 可选): 起始位置，默认为0
- `limit` (int, 可选): 返回数量限制，默认为100，最大200
- `order` (string, 可选): 排序字段，可选值：time（时间）、name（名称）、size（大小），默认为time
- `desc` (int, 可选): 是否降序排列，1为是，0为否，默认为1
- `category` (int, 可选): 文件类型：1视频、2音频、3图片、4文档、5应用、6其他、7种子

**响应示例:**
```json
{
  "status": "success",
  "message": "获取多媒体文件列表成功",
  "path": "/",
  "total": 10,
  "files": [
    {
      "fs_id": 1234567890,
      "path": "/图片/photo.jpg",
      "server_filename": "photo.jpg",
      "size": 1024000,
      "server_mtime": 1640995200,
      "server_ctime": 1640995200,
      "local_mtime": 1640995200,
      "local_ctime": 1640995200,
      "isdir": 0,
      "category": 3,
      "md5": "abc123def456",
      "thumbs": {
        "url1": "https://example.com/thumb1.jpg",
        "url2": "https://example.com/thumb2.jpg"
      },
      "media_type": 1,
      "width": 1920,
      "height": 1080,
      "duration": 0
    }
  ],
  "has_more": false,
  "routed_method": "imagelist",
  "selected_category": 3
}
```

### 4. 系统管理

#### 4.1 获取频率限制状态
```http
GET /api/netdisk/rate-limit/status
```

**响应示例:**
```json
{
  "status": "success",
  "message": "获取频率限制状态成功",
  "rate_limit_status": {
    "search": {
      "api_type": "search",
      "limits": {
        "daily": 2000,
        "per_minute": 20
      },
      "current_usage": {
        "per_minute": {
          "used": 5,
          "limit": 20,
          "remaining": 15
        },
        "daily": {
          "used": 100,
          "limit": 2000,
          "remaining": 1900
        }
      }
    }
  }
}
```

#### 4.2 检查授权状态
```http
GET /api/netdisk/auth/status
```

**响应示例:**
```json
{
  "status": "success",
  "message": "授权状态正常",
  "auth_status": "authorized",
  "access_token": "abc123def456...",
  "app_key": "your_app_key",
  "user_info": {
    "baidu_name": "用户名",
    "netdisk_name": "网盘用户名",
    "avatar_url": "https://example.com/avatar.jpg",
    "vip_type": 1,
    "vip_level": 3,
    "uk": 123456789
  }
}
```

#### 4.3 获取帮助信息
```http
GET /api/netdisk/help
```

**响应示例:**
```json
{
  "status": "success",
  "message": "网盘API帮助信息",
  "api_endpoints": {
    "GET /api/netdisk/files": "列出指定路径下的文件和文件夹",
    "GET /api/netdisk/directories": "获取指定路径下的子目录列表",
    "POST /api/netdisk/upload": "上传文件到网盘",
    "GET /api/netdisk/search": "搜索网盘文件",
    "GET /api/netdisk/user/info": "获取用户信息",
    "GET /api/netdisk/user/quota": "获取用户配额信息",
    "GET /api/netdisk/multimedia": "列出多媒体文件",
    "GET /api/netdisk/rate-limit/status": "获取API调用频率限制状态",
    "GET /api/netdisk/auth/status": "检查授权状态",
    "GET /api/netdisk/help": "获取API帮助信息"
  },
  "features": [
    "文件上传下载",
    "文件搜索",
    "目录浏览",
    "多媒体文件管理",
    "用户信息查询",
    "配额信息查询",
    "频率限制管理",
    "授权状态检查"
  ],
  "rate_limits": {
    "search": {"daily": 2000, "per_minute": 20},
    "listall": {"per_minute": 8},
    "fileinfo": {"per_minute": 30},
    "filemanager": {"per_minute": 20},
    "userinfo": {"per_minute": 10},
    "multimedia": {"per_minute": 15},
    "share": {"per_minute": 10},
    "upload": {"per_minute": 5},
    "download": {"per_minute": 10},
    "default": {"per_minute": 20}
  }
}
```

## 错误处理

### 常见错误码

- **400**: 请求参数错误
- **429**: 频率限制，API调用过于频繁
- **500**: 服务器内部错误

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

## 频率限制

### 限制配置

| API类型 | 每分钟限制 | 每日限制 | 说明 |
|---------|------------|----------|------|
| search | 20 | 2000 | 搜索接口 |
| listall | 8 | - | 全量列表接口 |
| fileinfo | 30 | - | 文件信息接口 |
| filemanager | 20 | - | 文件管理接口 |
| userinfo | 10 | - | 用户信息接口 |
| multimedia | 15 | - | 多媒体接口 |
| share | 10 | - | 分享接口 |
| upload | 5 | - | 上传接口 |
| download | 10 | - | 下载接口 |
| default | 20 | - | 默认限制 |

### 频率限制响应

当触发频率限制时，API会返回429状态码：

```json
{
  "detail": "API调用频率超限，每分钟最多20次，请等待30.5秒"
}
```

## 使用示例

### 1. 列出根目录文件

```bash
curl "http://localhost:8000/api/netdisk/files?path=/&limit=10"
```

### 2. 搜索文件

```bash
curl "http://localhost:8000/api/netdisk/search?keyword=test&limit=5"
```

### 3. 上传文件

```bash
curl -X POST "http://localhost:8000/api/netdisk/upload" \
  -F "file=@/path/to/local/file.pdf" \
  -F "remote_path=/我的文档/"
```

### 4. 获取用户信息

```bash
curl "http://localhost:8000/api/netdisk/user/info"
```

### 5. 获取配额信息

```bash
curl "http://localhost:8000/api/netdisk/user/quota"
```

### 6. 列出图片文件

```bash
curl "http://localhost:8000/api/netdisk/multimedia?category=3&limit=20"
```

## 配置要求

### 环境变量

需要在 `.env` 文件中配置以下环境变量：

```env
BAIDU_NETDISK_ACCESS_TOKEN=your_access_token
BAIDU_NETDISK_APP_KEY=your_app_key
BAIDU_NETDISK_REFRESH_TOKEN=your_refresh_token
BAIDU_NETDISK_SECRET_KEY=your_secret_key
```

### 获取API密钥

1. 访问 [百度网盘开放平台](https://pan.baidu.com/union/)
2. 注册并创建应用
3. 获取 App Key 和 Secret Key
4. 运行授权流程获取访问令牌

## 注意事项

1. **文件上传**: 大于4MB的文件会自动分片上传
2. **频率限制**: 内置智能频率控制，避免API调用超限
3. **错误处理**: 完整的错误处理和重试机制
4. **编码问题**: 自动处理UTF-8编码问题
5. **安全性**: 访问令牌不会在响应中完整显示

## 完整API文档

访问 `http://localhost:8000/docs` 查看完整的交互式API文档，包括：

- 所有端点的详细说明
- 参数类型和验证规则
- 请求/响应示例
- 在线测试功能

## 技术支持

如有问题，请检查：

1. 环境变量配置是否正确
2. 百度网盘API密钥是否有效
3. 网络连接是否正常
4. 频率限制是否触发

通过访问 `http://localhost:8000/api/netdisk/help` 获取最新的帮助信息。
