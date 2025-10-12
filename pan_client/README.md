# 云栈 - 共享资料库应用程序 (V1.0.1)

## 项目简介

云栈是一个现代化的资料库共享应用程序，提供友好的界面展示和强大的文件管理功能。支持两种传输模式：传统的REST API模式和基于Model Context Protocol (MCP) 的高性能模式。

### 新增功能 (V1.0.1)

- **MCP模式支持**：基于本地子进程的高性能文件操作
- **双模式架构**：REST和MCP模式无缝切换
- **抽象客户端接口**：统一的API接口设计
- **智能错误处理**：自动重试和回退机制
- **状态监控**：实时显示连接状态和性能指标

### 主要功能

- **资源浏览**：浏览各种类型的共享资料（演示模式）
- **现代化界面**：采用Material Design风格的UI元素
- **系统托盘支持**：最小化到系统托盘，双击图标恢复
- **自适应主题**：精心设计的界面样式和布局
- **用户信息展示**：查看用户信息和会员特权

## 技术架构

- **前端框架**：PySide6 (Qt for Python)
- **界面设计**：自定义Material组件、现代化UI风格
- **传输层**：REST API + MCP (Model Context Protocol)
- **客户端架构**：抽象接口 + 具体实现
- **项目结构**：模块化设计，分离UI组件与业务逻辑

## 项目结构

```
pan_client/
├── __init__.py              # 包初始化文件
├── main.py                  # 应用程序入口
├── config.json              # 配置文件
├── requirements.txt         # 依赖列表
├── core/                    # 核心模块
│   ├── __init__.py
│   ├── utils.py             # 工具函数
│   ├── config.py            # 配置管理
│   ├── token.py             # 令牌管理
│   ├── api.py               # REST API客户端
│   ├── abstract_client.py   # 抽象客户端接口
│   ├── mcp_session.py       # MCP会话管理
│   ├── mcp_client.py        # MCP客户端实现
│   ├── client_factory.py    # 客户端工厂
│   └── baidu_oauth.py       # OAuth认证
├── ui/                      # 用户界面模块
│   ├── __init__.py
│   ├── modern_pan.py        # 主界面实现
│   ├── dialogs/             # 对话框组件
│   │   ├── __init__.py
│   │   ├── user_info_dialog.py
│   │   ├── download_limit_dialog.py
│   │   ├── loading_dialog.py
│   │   └── login_dialog.py   # 登录对话框
│   └── widgets/             # 自定义界面组件
│       ├── __init__.py
│       ├── circular_progress_bar.py
│       ├── loading_spinner.py
│       ├── material_button.py
│       └── material_line_edit.py
├── tests/                   # 测试模块
│   ├── __init__.py
│   ├── conftest.py          # 测试配置
│   └── integration/         # 集成测试
│       └── test_mcp_flow.py
├── resources/               # 资源文件
│   └── icons/               # 图标资源
├── README.md                # 项目说明
├── README_MCP.md            # MCP模式详细说明
└── pytest.ini              # 测试配置
```

## 界面说明

应用程序提供以下主要界面：

1. **主界面**：左侧导航栏和右侧内容区
   - 顶部搜索栏
   - 文件列表区域
   - 状态栏

2. **对话框**：
   - 用户信息对话框：展示用户基本信息和会员特权
   - 下载限制对话框：用于展示下载限制提示
   - 加载对话框：展示操作进度

## 运行方法

### 环境要求
- Python 3.8+
- PySide6 6.0+
- MCP 0.9.0+ (MCP模式)

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行程序

#### REST模式（默认）
```bash
python main.py
```

#### MCP模式
```bash
python main.py --use-mcp
```

#### 其他选项
```bash
# 指定配置文件
python main.py --config custom_config.json

# 调试模式
python main.py --debug

# 查看帮助
python main.py --help
```

### MCP模式配置

编辑 `config.json` 文件：

```json
{
  "transport": {
    "mode": "mcp",
    "mcp": {
      "stdio_binary": "python",
      "entry": "../netdisk-mcp-server-stdio/netdisk.py",
      "args": ["--transport", "stdio"]
    }
  }
}
```

详细配置说明请参考 [README_MCP.md](README_MCP.md)。

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

- MCP会话管理测试
- 客户端功能测试
- 文件操作流程测试
- UI集成测试
- 错误处理测试

## 注意事项

1. **MCP模式**：需要确保MCP服务器可访问，否则会自动回退到REST模式
2. **网络环境**：REST模式需要稳定的网络连接
3. **性能优化**：MCP模式提供更好的性能和稳定性
4. **错误处理**：系统具有自动重试和回退机制

## 维护与贡献

- 界面优化：可以在 `ui/modern_pan.py` 和 `ui/widgets/` 目录下修改UI组件
- 添加新对话框：在 `ui/dialogs/` 目录下添加新的对话框类
- 资源管理：在 `resources/icons/` 目录中添加新的图标资源
- 功能扩展：根据需要在 `core/` 目录下添加更多实用工具

## 版本历史

- **V1.0.1**：MCP模式集成，双模式架构，抽象客户端接口，智能错误处理
- **V1.0.0**：初始版本，基础UI界面

## 相关文档

- [MCP模式详细说明](README_MCP.md)
- [API文档](docs/API.md)
- [开发指南](docs/DEVELOPMENT.md) 