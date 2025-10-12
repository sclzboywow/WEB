#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client Factory for pan_client

This module provides a factory function to create the appropriate
netdisk client based on configuration.
"""

import logging
from typing import Any, Dict, Optional

from .abstract_client import AbstractNetdiskClient
from .rest_client import RestNetdiskClient
from .mcp_client import McpNetdiskClient

logger = logging.getLogger(__name__)


def create_client(config: Optional[Dict[str, Any]] = None) -> AbstractNetdiskClient:
    """
    Create a netdisk client based on configuration.
    
    Args:
        config: Configuration dict. If None, uses default REST mode.
        
    Returns:
        Configured netdisk client instance
        
    Raises:
        ValueError: If configuration is invalid
        ImportError: If MCP dependencies are missing
    """
    if config is None:
        config = {}
    
    # Determine transport mode
    transport_config = config.get('transport', {})
    mode = transport_config.get('mode', 'rest')
    
    logger.info(f"Creating netdisk client in {mode} mode")
    
    if mode == 'mcp':
        try:
            return McpNetdiskClient(config)
        except ImportError as e:
            logger.error(f"MCP dependencies not available: {e}")
            logger.info("Falling back to REST mode")
            return RestNetdiskClient(config)
        except Exception as e:
            logger.error(f"Failed to create MCP client: {e}")
            logger.info("Falling back to REST mode")
            return RestNetdiskClient(config)
    
    elif mode == 'rest':
        return RestNetdiskClient(config)
    
    else:
        raise ValueError(f"Unknown transport mode: {mode}")


def is_mcp_mode(config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Check if configuration specifies MCP mode.
    
    Args:
        config: Configuration dict
        
    Returns:
        True if MCP mode is configured
    """
    if config is None:
        return False
    
    transport_config = config.get('transport', {})
    return transport_config.get('mode', 'rest') == 'mcp'


def get_client_capabilities(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get capabilities of the configured client.
    
    Args:
        config: Configuration dict
        
    Returns:
        Dict containing client capabilities
    """
    if config is None:
        config = {}
    
    transport_config = config.get('transport', {})
    mode = transport_config.get('mode', 'rest')
    
    capabilities = {
        'mode': mode,
        'supports_async': True,
        'supports_streaming': mode == 'rest',
        'supports_batch_operations': mode == 'rest',
        'supports_real_time_status': mode == 'mcp',
        'supports_tool_invocation': mode == 'mcp',
    }
    
    if mode == 'mcp':
        mcp_config = transport_config.get('mcp', {})
        capabilities.update({
            'mcp_server_path': mcp_config.get('entry'),
            'mcp_binary': mcp_config.get('stdio_binary'),
            'mcp_args': mcp_config.get('args', []),
        })
    
    elif mode == 'rest':
        capabilities.update({
            'base_url': config.get('base_url'),
            'timeout': config.get('timeout', 15),
        })
    
    return capabilities


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize configuration.
    
    Args:
        config: Configuration dict to validate
        
    Returns:
        Normalized configuration dict
        
    Raises:
        ValueError: If configuration is invalid
    """
    normalized = config.copy()
    
    # Validate transport configuration
    transport_config = normalized.get('transport', {})
    mode = transport_config.get('mode', 'rest')
    
    if mode not in ['rest', 'mcp']:
        raise ValueError(f"Invalid transport mode: {mode}")
    
    if mode == 'mcp':
        mcp_config = transport_config.get('mcp', {})
        
        # Validate required MCP settings
        if 'entry' not in mcp_config:
            raise ValueError("MCP mode requires 'entry' path in transport.mcp")
        
        # Set defaults
        mcp_config.setdefault('stdio_binary', 'python')
        mcp_config.setdefault('args', ['--transport', 'stdio'])
        
        transport_config['mcp'] = mcp_config
    
    elif mode == 'rest':
        # Set REST defaults
        normalized.setdefault('timeout', 15)
    
    normalized['transport'] = transport_config
    
    return normalized


def create_client_with_fallback(config: Optional[Dict[str, Any]] = None) -> AbstractNetdiskClient:
    """
    Create a client with automatic fallback to REST mode if MCP fails.
    
    Args:
        config: Configuration dict
        
    Returns:
        Configured netdisk client instance (always succeeds)
    """
    if config is None:
        config = {}
    
    try:
        # Try to create client with specified mode
        return create_client(config)
    
    except Exception as e:
        logger.warning(f"Failed to create client with specified mode: {e}")
        
        # Fallback to REST mode
        fallback_config = config.copy()
        fallback_config.setdefault('transport', {})['mode'] = 'rest'
        
        logger.info("Creating fallback REST client")
        return RestNetdiskClient(fallback_config)
