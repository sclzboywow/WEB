#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Netdisk Client Implementation

This module implements the MCP-based netdisk client using the McpSession.
"""

import logging
from typing import Any, Dict, List, Optional

from .abstract_client import (
    AbstractNetdiskClient,
    normalize_file_info,
    normalize_error,
    ClientError,
    AuthenticationError,
    FileNotFoundError,
    PermissionError,
    RateLimitError,
    NetworkError,
    ValidationError,
)
from .mcp_session import McpSession, McpSessionError

logger = logging.getLogger(__name__)


class McpNetdiskClient(AbstractNetdiskClient):
    """
    MCP-based netdisk client implementation.
    
    Uses MCP tools to interact with the netdisk server instead of direct REST calls.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MCP netdisk client.
        
        Args:
            config: Configuration dict containing MCP settings
        """
        self.config = config
        self.mcp_session: Optional[McpSession] = None
        self._is_initialized = False
        
        logger.info("McpNetdiskClient initialized")
    
    async def _ensure_initialized(self) -> None:
        """Ensure MCP session is initialized."""
        if not self._is_initialized:
            self.mcp_session = McpSession(self.config)
            await self.mcp_session.ensure_started()
            self._is_initialized = True
            logger.info("MCP session initialized")
    
    async def list_files(self, path: str, **kwargs) -> Dict[str, Any]:
        """List files in a directory using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'list_files',
                path=path,
                **kwargs
            )
            
            # Normalize file information
            if 'list' in result:
                normalized_files = []
                for file_data in result['list']:
                    normalized_files.append(normalize_file_info(file_data))
                result['list'] = normalized_files
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to list files in {path}: {e}")
            raise normalize_error(e) from e
    
    async def download_file(self, path: str, local_path: str, **kwargs) -> str:
        """Download a file using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'download_file',
                path=path,
                local_path=local_path,
                **kwargs
            )
            
            return result.get('local_path', local_path)
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to download file {path}: {e}")
            raise normalize_error(e) from e
    
    async def upload_file(self, local_path: str, remote_dir: str, **kwargs) -> Dict[str, Any]:
        """Upload a file using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'upload_file',
                local_path=local_path,
                remote_dir=remote_dir,
                **kwargs
            )
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to upload file {local_path}: {e}")
            raise normalize_error(e) from e
    
    async def create_directory(self, path: str, **kwargs) -> Dict[str, Any]:
        """Create a directory using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'create_directory',
                path=path,
                **kwargs
            )
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            raise normalize_error(e) from e
    
    async def delete_file(self, path: str, **kwargs) -> Dict[str, Any]:
        """Delete a file using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'delete_file',
                path=path,
                **kwargs
            )
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to delete file {path}: {e}")
            raise normalize_error(e) from e
    
    async def move_file(self, src_path: str, dest_path: str, **kwargs) -> Dict[str, Any]:
        """Move a file using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'move_file',
                src_path=src_path,
                dest_path=dest_path,
                **kwargs
            )
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to move file {src_path} to {dest_path}: {e}")
            raise normalize_error(e) from e
    
    async def copy_file(self, src_path: str, dest_path: str, **kwargs) -> Dict[str, Any]:
        """Copy a file using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'copy_file',
                src_path=src_path,
                dest_path=dest_path,
                **kwargs
            )
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to copy file {src_path} to {dest_path}: {e}")
            raise normalize_error(e) from e
    
    async def get_file_info(self, path: str, **kwargs) -> Dict[str, Any]:
        """Get file information using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'get_file_info',
                path=path,
                **kwargs
            )
            
            # Normalize file information
            if 'file_info' in result:
                result['file_info'] = normalize_file_info(result['file_info'])
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to get file info for {path}: {e}")
            raise normalize_error(e) from e
    
    async def search_files(self, query: str, **kwargs) -> Dict[str, Any]:
        """Search files using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'search_files',
                query=query,
                **kwargs
            )
            
            # Normalize file information
            if 'list' in result:
                normalized_files = []
                for file_data in result['list']:
                    normalized_files.append(normalize_file_info(file_data))
                result['list'] = normalized_files
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to search files with query '{query}': {e}")
            raise normalize_error(e) from e
    
    async def get_user_info(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Get user information using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'get_user_info',
                **kwargs
            )
            
            return result.get('user_info')
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            raise normalize_error(e) from e
    
    async def get_auth_status(self, **kwargs) -> Dict[str, Any]:
        """Get authentication status using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'check_auth_status',
                **kwargs
            )
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to get auth status: {e}")
            raise normalize_error(e) from e
    
    async def refresh_token(self, **kwargs) -> Dict[str, Any]:
        """Refresh access token using MCP."""
        try:
            await self._ensure_initialized()
            
            result = await self.mcp_session.invoke_tool(
                'refresh_access_token',
                **kwargs
            )
            
            return result
            
        except McpSessionError as e:
            raise normalize_error(e) from e
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            raise normalize_error(e) from e
    
    def get_client_info(self) -> Dict[str, Any]:
        """Get client information and status."""
        info = {
            'type': 'mcp',
            'is_initialized': self._is_initialized,
            'config': self.config,
        }
        
        if self.mcp_session:
            info.update(self.mcp_session.get_session_info())
        
        return info
    
    async def close(self) -> None:
        """Close the client and cleanup resources."""
        if self.mcp_session:
            await self.mcp_session.dispose()
            self.mcp_session = None
            self._is_initialized = False
            logger.info("McpNetdiskClient closed")
