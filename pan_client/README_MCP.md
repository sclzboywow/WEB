# 云栈客户端 MCP 模式使用指南

## 概述

云栈客户端现在支持两种传输模式：
- **REST模式**：传统的HTTP API调用方式
- **MCP模式**：基于Model Context Protocol的本地子进程通信方式

MCP模式提供了更好的性能、更低的延迟和更稳定的连接，特别适合需要频繁文件操作的场景。

## MCP模式特性

### 优势
- **低延迟**：本地子进程通信，无需网络往返
- **高稳定性**：避免网络中断和超时问题
- **更好的错误处理**：本地进程更容易监控和恢复
- **资源优化**：减少网络带宽使用

### 适用场景
- 频繁的文件上传下载操作
- 大批量文件处理
- 网络环境不稳定的情况
- 需要高性能文件操作的场景

## 安装和配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

确保安装了MCP相关依赖：
- `mcp>=0.9.0`
- `pytest>=7.0.0` (用于测试)
- `pytest-asyncio>=0.21.0` (用于异步测试)

### 2. 配置MCP模式

编辑 `config.json` 文件：

```json
{
  "base_url": "http://124.223.185.27",
  "transport": {
    "mode": "mcp",
    "mcp": {
      "stdio_binary": "python",
      "entry": "../netdisk-mcp-server-stdio/netdisk.py",
      "args": ["--transport", "stdio"]
    }
  },
  "download_dir": "./downloads",
  "rate_limit": {
    "requests_per_minute": 20,
    "burst_size": 5
  },
  "timeout": 15
}
```

### 3. 启动MCP服务器

确保MCP服务器可访问：
```bash
cd ../netdisk-mcp-server-stdio
python netdisk.py --transport stdio
```

## 使用方法

### 命令行启动

#### REST模式（默认）
```bash
python main.py
```

#### MCP模式
```bash
python main.py --use-mcp
```

#### 指定配置文件
```bash
python main.py --config custom_config.json
```

#### 调试模式
```bash
python main.py --debug
```

### 编程方式使用

```python
from pan_client.core.client_factory import create_client_with_fallback
from pan_client.core.mcp_session import McpSession

# 创建MCP会话
config = {
    "transport": {
        "mode": "mcp",
        "mcp": {
            "stdio_binary": "python",
            "entry": "../netdisk-mcp-server-stdio/netdisk.py",
            "args": ["--transport", "stdio"]
        }
    }
}

mcp_session = McpSession(config)
await mcp_session.ensure_started()

# 创建客户端
client = create_client_with_fallback(config, mcp_session)

# 使用客户端
files = await client.list_files("/")
print(f"找到 {len(files.get('list', []))} 个文件")
```

## 配置选项

### 传输模式配置

```json
{
  "transport": {
    "mode": "mcp",  // 或 "rest"
    "mcp": {
      "stdio_binary": "python",  // MCP服务器可执行文件
      "entry": "../netdisk-mcp-server-stdio/netdisk.py",  // MCP服务器入口
      "args": ["--transport", "stdio"],  // 启动参数
      "env": {}  // 环境变量
    }
  }
}
```

### 其他配置选项

- `download_dir`: 下载目录
- `rate_limit`: 速率限制配置
- `timeout`: 超时设置（秒）

## 错误处理

### 常见错误

#### 1. MCP服务器启动失败
```
McpSessionError: Failed to start MCP server
```
**解决方案**：
- 检查MCP服务器路径是否正确
- 确保Python环境可用
- 检查MCP服务器依赖是否安装

#### 2. 连接超时
```
McpTimeoutError: MCP operation timed out
```
**解决方案**：
- 增加timeout配置值
- 检查MCP服务器是否正常运行
- 重启MCP会话

#### 3. 工具调用失败
```
McpRateLimitError: Rate limit exceeded
```
**解决方案**：
- 调整rate_limit配置
- 减少并发操作
- 等待限流重置

### 错误恢复

MCP模式具有自动恢复机制：

1. **会话检测**：定期检查MCP会话状态
2. **自动重启**：检测到会话断开时自动重启
3. **回退机制**：MCP不可用时自动回退到REST模式

## 性能优化

### 1. 连接池配置
```json
{
  "transport": {
    "mode": "mcp",
    "mcp": {
      "max_connections": 10,
      "connection_timeout": 30
    }
  }
}
```

### 2. 批处理操作
```python
# 批量上传
files = ["file1.txt", "file2.txt", "file3.txt"]
result = await client.upload_to_shared_batch(files)

# 批量下载
file_list = [{"fs_id": "123", "name": "file1.txt"}]
result = await client.download_multiple(file_list, "/downloads")
```

### 3. 异步操作
```python
import asyncio

async def process_files():
    tasks = []
    for file_path in file_paths:
        task = client.upload_file(file_path, "/")
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    return results
```

## 监控和调试

### 1. 状态监控

UI界面显示MCP连接状态：
- 绿色：MCP已连接
- 红色：MCP未连接

### 2. 日志记录

启用调试日志：
```bash
python main.py --debug
```

日志级别：
- `DEBUG`: 详细调试信息
- `INFO`: 一般信息
- `WARNING`: 警告信息
- `ERROR`: 错误信息

### 3. 性能指标

MCP模式提供以下性能指标：
- 连接延迟
- 操作响应时间
- 错误率统计
- 吞吐量监控

## 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行MCP相关测试
pytest tests/integration/test_mcp_flow.py

# 运行异步测试
pytest -m asyncio

# 运行集成测试
pytest -m integration
```

### 测试覆盖

测试包括：
- MCP会话管理
- 客户端初始化
- 文件操作流程
- 错误处理
- UI集成

## 故障排除

### 1. MCP服务器无法启动

检查项目：
- Python环境是否正确
- MCP服务器依赖是否安装
- 路径配置是否正确
- 权限是否足够

### 2. 连接不稳定

解决方案：
- 检查系统资源使用情况
- 调整timeout配置
- 重启MCP会话
- 检查防火墙设置

### 3. 性能问题

优化建议：
- 使用批处理操作
- 调整并发设置
- 优化网络配置
- 监控资源使用

## 开发指南

### 添加新的MCP工具

1. 在MCP服务器中实现工具
2. 在`McpNetdiskClient`中添加对应方法
3. 更新抽象接口`AbstractNetdiskClient`
4. 添加测试用例

### 扩展错误处理

1. 定义新的错误类型
2. 在`McpSession`中映射错误
3. 更新UI错误显示
4. 添加错误恢复逻辑

## 版本兼容性

- Python 3.8+
- PySide6 6.0+
- MCP 0.9.0+

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 添加测试用例
4. 提交Pull Request

## 许可证

本项目采用MIT许可证，详见LICENSE文件。
