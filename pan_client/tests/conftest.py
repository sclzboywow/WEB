"""
测试配置文件

提供测试用的配置和fixture。
"""
import pytest
import tempfile
import os
from unittest.mock import MagicMock

from pan_client.core.mcp_session import McpSession
from pan_client.core.mcp_client import McpNetdiskClient
from pan_client.core.abstract_client import AbstractNetdiskClient


@pytest.fixture
def temp_config():
    """临时配置文件"""
    config = {
        "base_url": "http://localhost:5000",
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
    return config


@pytest.fixture
def mock_mcp_session():
    """模拟MCP会话"""
    session = MagicMock()
    session.is_alive.return_value = True
    session.run_in_loop.return_value = {"ok": True}
    return session


@pytest.fixture
def mock_mcp_client(mock_mcp_session):
    """模拟MCP客户端"""
    config = {"transport": {"mode": "mcp"}}
    client = McpNetdiskClient(mock_mcp_session, config)
    return client


@pytest.fixture
def temp_file():
    """临时文件"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
        f.write(b"test content")
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def temp_directory():
    """临时目录"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir
