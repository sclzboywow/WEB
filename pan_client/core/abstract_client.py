#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abstract Client Interface for pan_client

This module defines the abstract base class for both REST and MCP
implementations of the netdisk client.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, BinaryIO


class AbstractNetdiskClient(ABC):
    """
    Abstract base class for netdisk clients.
    
    Defines the interface that both REST and MCP implementations must follow.
    This allows the UI layer to work with either implementation transparently.
    """
    
    @abstractmethod
    async def list_files(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        List files in a directory.
        
        Args:
            path: Directory path to list
            **kwargs: Additional parameters (limit, order, etc.)
            
        Returns:
            Dict containing file list and metadata
        """
        pass
    
    @abstractmethod
    async def download_file(self, path: str, local_path: str, **kwargs) -> str:
        """
        Download a file from netdisk.
        
        Args:
            path: Remote file path
            local_path: Local destination path
            **kwargs: Additional parameters (progress callback, etc.)
            
        Returns:
            Local path where file was downloaded
        """
        pass
    
    @abstractmethod
    async def upload_file(self, local_path: str, remote_dir: str, **kwargs) -> Dict[str, Any]:
        """
        Upload a file to netdisk.
        
        Args:
            local_path: Local file path to upload
            remote_dir: Remote directory destination
            **kwargs: Additional parameters (progress callback, etc.)
            
        Returns:
            Dict containing upload result and metadata
        """
        pass
    
    @abstractmethod
    async def create_directory(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        Create a directory.
        
        Args:
            path: Directory path to create
            **kwargs: Additional parameters
            
        Returns:
            Dict containing creation result
        """
        pass
    
    @abstractmethod
    async def delete_file(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        Delete a file or directory.
        
        Args:
            path: Path to delete
            **kwargs: Additional parameters
            
        Returns:
            Dict containing deletion result
        """
        pass
    
    @abstractmethod
    async def move_file(self, src_path: str, dest_path: str, **kwargs) -> Dict[str, Any]:
        """
        Move/rename a file or directory.
        
        Args:
            src_path: Source path
            dest_path: Destination path
            **kwargs: Additional parameters
            
        Returns:
            Dict containing move result
        """
        pass
    
    @abstractmethod
    async def copy_file(self, src_path: str, dest_path: str, **kwargs) -> Dict[str, Any]:
        """
        Copy a file or directory.
        
        Args:
            src_path: Source path
            dest_path: Destination path
            **kwargs: Additional parameters
            
        Returns:
            Dict containing copy result
        """
        pass
    
    @abstractmethod
    async def get_file_info(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        Get detailed information about a file or directory.
        
        Args:
            path: Path to get info for
            **kwargs: Additional parameters
            
        Returns:
            Dict containing file information
        """
        pass
    
    @abstractmethod
    async def search_files(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        Search for files.
        
        Args:
            query: Search query
            **kwargs: Additional parameters (path, file_type, etc.)
            
        Returns:
            Dict containing search results
        """
        pass
    
    @abstractmethod
    async def get_user_info(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Get current user information.
        
        Args:
            **kwargs: Additional parameters
            
        Returns:
            Dict containing user information, or None if not authenticated
        """
        pass
    
    @abstractmethod
    async def get_auth_status(self, **kwargs) -> Dict[str, Any]:
        """
        Get authentication status.
        
        Args:
            **kwargs: Additional parameters
            
        Returns:
            Dict containing auth status and hints
        """
        pass
    
    @abstractmethod
    async def refresh_token(self, **kwargs) -> Dict[str, Any]:
        """
        Refresh access token.
        
        Args:
            **kwargs: Additional parameters
            
        Returns:
            Dict containing new token information
        """
        pass
    
    @abstractmethod
    def get_client_info(self) -> Dict[str, Any]:
        """
        Get client information and status.
        
        Returns:
            Dict containing client type, status, and capabilities
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the client and cleanup resources.
        """
        pass


class ClientError(Exception):
    """Base exception for client errors."""
    pass


class AuthenticationError(ClientError):
    """Raised when authentication fails."""
    pass


class FileNotFoundError(ClientError):
    """Raised when a file or directory is not found."""
    pass


class PermissionError(ClientError):
    """Raised when permission is denied."""
    pass


class RateLimitError(ClientError):
    """Raised when rate limit is exceeded."""
    pass


class NetworkError(ClientError):
    """Raised when network operation fails."""
    pass


class ValidationError(ClientError):
    """Raised when input validation fails."""
    pass


def normalize_file_info(file_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize file information from different sources.
    
    This function ensures that file information returned by different
    client implementations has a consistent format.
    
    Args:
        file_data: Raw file data from client
        
    Returns:
        Normalized file information
    """
    normalized = {
        'fs_id': file_data.get('fs_id'),
        'path': file_data.get('path') or file_data.get('file_path'),
        'name': file_data.get('server_filename') or file_data.get('file_name'),
        'size': file_data.get('size', 0),
        'isdir': bool(file_data.get('isdir', 0)),
        'create_time': file_data.get('create_time'),
        'modify_time': file_data.get('modify_time'),
        'md5': file_data.get('md5'),
        'category': file_data.get('category'),
        'thumburl': file_data.get('thumburl'),
        'download_url': file_data.get('download_url'),
    }
    
    # Remove None values
    return {k: v for k, v in normalized.items() if v is not None}


def normalize_error(error: Exception) -> ClientError:
    """
    Normalize errors from different sources.
    
    Args:
        error: Original error
        
    Returns:
        Normalized ClientError
    """
    error_str = str(error).lower()
    
    if 'auth' in error_str or 'token' in error_str or 'login' in error_str:
        return AuthenticationError(str(error))
    elif 'not found' in error_str or '404' in error_str:
        return FileNotFoundError(str(error))
    elif 'permission' in error_str or '403' in error_str:
        return PermissionError(str(error))
    elif 'rate limit' in error_str or '429' in error_str:
        return RateLimitError(str(error))
    elif 'network' in error_str or 'timeout' in error_str or 'connection' in error_str:
        return NetworkError(str(error))
    elif 'validation' in error_str or 'invalid' in error_str:
        return ValidationError(str(error))
    else:
        return ClientError(str(error))
