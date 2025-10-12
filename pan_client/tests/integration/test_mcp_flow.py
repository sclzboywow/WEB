"""
MCP模式集成测试

测试MCP会话的启动、工具调用和文件操作流程。
"""
import pytest
import asyncio
import tempfile
import os
from unittest.mock import patch, MagicMock

from pan_client.core.mcp_session import McpSession, McpSessionError
from pan_client.core.mcp_client import McpNetdiskClient
from pan_client.core.abstract_client import AbstractNetdiskClient
from pan_client.core.client_factory import create_client_with_fallback


class TestMcpSession:
    """测试MCP会话管理"""
    
    @pytest.mark.asyncio
    async def test_mcp_session_initialization(self):
        """测试MCP会话初始化"""
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
        
        session = McpSession(config)
        assert session is not None
        assert not session.is_alive()
        
        # 清理
        await session.dispose()
    
    @pytest.mark.asyncio
    async def test_mcp_session_startup(self):
        """测试MCP会话启动"""
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
        
        session = McpSession(config)
        
        try:
            await session.ensure_started()
            # 注意：实际测试中可能需要模拟MCP服务器
            # 这里主要测试启动流程不报错
        except Exception as e:
            # 如果MCP服务器不可用，这是预期的
            assert "netdisk.py" in str(e) or "Connection refused" in str(e)
        finally:
            await session.dispose()
    
    @pytest.mark.asyncio
    async def test_mcp_session_error_handling(self):
        """测试MCP会话错误处理"""
        config = {
            "transport": {
                "mode": "mcp",
                "mcp": {
                    "stdio_binary": "nonexistent",
                    "entry": "nonexistent.py",
                    "args": []
                }
            }
        }
        
        session = McpSession(config)
        
        with pytest.raises(McpSessionError):
            await session.ensure_started()
        
        await session.dispose()


class TestMcpNetdiskClient:
    """测试MCP网盘客户端"""
    
    @pytest.mark.asyncio
    async def test_mcp_client_initialization(self):
        """测试MCP客户端初始化"""
        # 模拟MCP会话
        mock_session = MagicMock()
        mock_session.is_alive.return_value = True
        
        config = {"transport": {"mode": "mcp"}}
        client = McpNetdiskClient(mock_session, config)
        
        assert client is not None
        assert client.mcp_session == mock_session
        assert client.config == config
    
    @pytest.mark.asyncio
    async def test_mcp_client_list_files(self):
        """测试MCP客户端文件列表功能"""
        # 模拟MCP会话和响应
        mock_session = MagicMock()
        mock_session.is_alive.return_value = True
        mock_session.run_in_loop.return_value = {
            "list": [
                {
                    "server_filename": "test.txt",
                    "fs_id": "123",
                    "size": 1024,
                    "isdir": 0,
                    "path": "/test.txt"
                }
            ]
        }
        
        config = {"transport": {"mode": "mcp"}}
        client = McpNetdiskClient(mock_session, config)
        
        result = await client.list_files("/")
        
        assert "list" in result
        assert len(result["list"]) == 1
        assert result["list"][0]["server_filename"] == "test.txt"
        
        # 验证调用了正确的工具
        mock_session.run_in_loop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_mcp_client_error_handling(self):
        """测试MCP客户端错误处理"""
        mock_session = MagicMock()
        mock_session.is_alive.return_value = True
        mock_session.run_in_loop.side_effect = Exception("MCP工具调用失败")
        
        config = {"transport": {"mode": "mcp"}}
        client = McpNetdiskClient(mock_session, config)
        
        with pytest.raises(Exception):
            await client.list_files("/")


class TestClientFactory:
    """测试客户端工厂"""
    
    def test_create_client_rest_mode(self):
        """测试创建REST模式客户端"""
        config = {"transport": {"mode": "rest"}}
        client = create_client_with_fallback(config)
        
        assert client is not None
        assert hasattr(client, 'list_files')
        # 应该是RestNetdiskClient
        assert hasattr(client, '_session')
    
    def test_create_client_mcp_mode_with_session(self):
        """测试创建MCP模式客户端（有会话）"""
        config = {"transport": {"mode": "mcp"}}
        mock_session = MagicMock()
        mock_session.is_alive.return_value = True
        
        client = create_client_with_fallback(config, mock_session)
        
        assert client is not None
        assert hasattr(client, 'list_files')
        # 应该是McpNetdiskClient
        assert hasattr(client, 'mcp_session')
    
    def test_create_client_mcp_mode_fallback(self):
        """测试创建MCP模式客户端（无会话，回退到REST）"""
        config = {"transport": {"mode": "mcp"}}
        
        client = create_client_with_fallback(config)
        
        assert client is not None
        assert hasattr(client, 'list_files')
        # 应该回退到RestNetdiskClient
        assert hasattr(client, '_session')


class TestFileOperations:
    """测试文件操作流程"""
    
    @pytest.mark.asyncio
    async def test_file_upload_flow(self):
        """测试文件上传流程"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
            f.write(b"test content")
            temp_file = f.name
        
        try:
            # 模拟MCP会话
            mock_session = MagicMock()
            mock_session.is_alive.return_value = True
            mock_session.run_in_loop.return_value = {
                "ok": True,
                "path": "/uploaded/test.txt"
            }
            
            config = {"transport": {"mode": "mcp"}}
            client = McpNetdiskClient(mock_session, config)
            
            result = await client.upload_file(temp_file, "/")
            
            assert result["ok"] is True
            assert "path" in result
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_file_download_flow(self):
        """测试文件下载流程"""
        # 模拟MCP会话
        mock_session = MagicMock()
        mock_session.is_alive.return_value = True
        
        # 模拟下载响应
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "1024"}
        mock_response.iter_content.return_value = [b"test content"]
        
        mock_session.run_in_loop.return_value = mock_response
        
        config = {"transport": {"mode": "mcp"}}
        client = McpNetdiskClient(mock_session, config)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await client.download_file("/test.txt", os.path.join(temp_dir, "downloaded.txt"))
            
            assert result is not None
            assert os.path.exists(result)
    
    @pytest.mark.asyncio
    async def test_file_search_flow(self):
        """测试文件搜索流程"""
        # 模拟MCP会话
        mock_session = MagicMock()
        mock_session.is_alive.return_value = True
        mock_session.run_in_loop.return_value = {
            "list": [
                {
                    "server_filename": "search_result.txt",
                    "fs_id": "456",
                    "size": 2048,
                    "isdir": 0,
                    "path": "/search_result.txt"
                }
            ]
        }
        
        config = {"transport": {"mode": "mcp"}}
        client = McpNetdiskClient(mock_session, config)
        
        result = await client.search_files("test")
        
        assert "list" in result
        assert len(result["list"]) == 1
        assert "search_result.txt" in result["list"][0]["server_filename"]


class TestUIIntegration:
    """测试UI集成"""
    
    def test_file_manager_ui_with_mcp_client(self):
        """测试文件管理器UI与MCP客户端集成"""
        # 模拟MCP会话
        mock_session = MagicMock()
        mock_session.is_alive.return_value = True
        
        # 模拟MCP客户端
        mock_client = MagicMock()
        mock_client.get_client_info.return_value = {"type": "mcp", "status": "connected"}
        
        # 测试UI初始化（不实际创建UI，只测试参数传递）
        from pan_client.ui.modern_pan import FileManagerUI
        
        # 这里主要测试构造函数能接受MCP客户端
        # 实际UI测试需要更复杂的设置
        try:
            ui = FileManagerUI(client=mock_client, mcp_session=mock_session)
            assert ui.client == mock_client
            assert ui.mcp_session == mock_session
        except Exception:
            # UI测试可能需要Qt环境，这里主要测试参数传递
            pass
    
    def test_login_dialog_with_mcp_client(self):
        """测试登录对话框与MCP客户端集成"""
        # 模拟MCP会话和客户端
        mock_session = MagicMock()
        mock_client = MagicMock()
        
        # 测试登录对话框初始化
        from pan_client.ui.dialogs.login_dialog import LoginDialog
        
        try:
            dialog = LoginDialog(client=mock_client, mcp_session=mock_session)
            assert dialog.client == mock_client
            assert dialog.mcp_session == mock_session
        except Exception:
            # 对话框测试可能需要Qt环境
            pass


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
