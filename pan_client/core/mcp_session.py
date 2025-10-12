#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Session Management for pan_client

This module provides a wrapper around the MCP client session pattern
from netdisk-mcp-server-stdio/client_demo_stdio.py for use in pan_client.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, Optional, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class McpSessionError(Exception):
    """Base exception for MCP session errors."""
    pass


class McpSessionNotStartedError(McpSessionError):
    """Raised when trying to use MCP session before it's started."""
    pass


class McpTimeoutError(McpSessionError):
    """Raised when MCP tool call times out."""
    pass


class McpRateLimitError(McpSessionError):
    """Raised when MCP rate limit is exceeded."""
    pass


class McpAuthError(McpSessionError):
    """Raised when MCP authentication fails."""
    pass


class McpSession:
    """
    MCP Session wrapper for pan_client.
    
    Manages a long-lived subprocess running the MCP server and provides
    async helpers for tool invocation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MCP session with configuration.
        
        Args:
            config: Configuration dict containing MCP server settings
        """
        self.config = config
        self.mcp_config = config.get('mcp', {})
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._process: Optional[subprocess.Popen] = None
        self._is_started = False
        
        # Event loop for thread-safe operations
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        
        # Extract configuration
        self.stdio_binary = self.mcp_config.get('stdio_binary', 'python')
        self.entry_point = self.mcp_config.get('entry', '../netdisk-mcp-server-stdio/netdisk.py')
        self.args = self.mcp_config.get('args', ['--transport', 'stdio'])
        
        # Environment setup
        self.env = os.environ.copy()
        self._setup_environment()
        
        logger.info(f"McpSession initialized with entry: {self.entry_point}")
    
    def _setup_environment(self) -> None:
        """Setup environment variables for MCP subprocess."""
        # Pass access token if available
        access_token = os.getenv('BAIDU_NETDISK_ACCESS_TOKEN')
        if access_token:
            self.env['BAIDU_NETDISK_ACCESS_TOKEN'] = access_token
        
        # Configure download directory
        download_dir = self.config.get('download_dir', './downloads')
        self.env['DOWNLOAD_DIR'] = download_dir
        
        # Set rate-limit parameters
        rate_limit = self.config.get('rate_limit', {})
        if 'requests_per_minute' in rate_limit:
            self.env['RATE_LIMIT_REQUESTS_PER_MINUTE'] = str(rate_limit['requests_per_minute'])
        if 'burst_size' in rate_limit:
            self.env['RATE_LIMIT_BURST_SIZE'] = str(rate_limit['burst_size'])
        
        logger.debug(f"Environment setup complete. Download dir: {download_dir}")
    
    def run_in_loop(self, coro):
        """
        Run a coroutine in the MCP event loop from a synchronous thread.
        
        Args:
            coro: Coroutine to run
            
        Returns:
            Result of the coroutine
            
        Raises:
            McpSessionNotStartedError: If event loop not started
        """
        if not self._loop:
            raise McpSessionNotStartedError("Event loop not started")
        
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)
    
    def _start_event_loop_thread(self) -> None:
        """Start the event loop in a separate thread."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
        
        # Wait for loop to be ready
        while self._loop is None:
            time.sleep(0.01)
        
        logger.info("MCP event loop thread started")
    
    async def ensure_started(self) -> None:
        """
        Ensure MCP session is started.
        
        Launches the MCP server subprocess if not already running.
        """
        if self._is_started:
            return
        
        try:
            # Start event loop thread first
            if not self._loop:
                self._start_event_loop_thread()
            # Resolve entry point path
            entry_path = Path(self.entry_point)
            if not entry_path.is_absolute():
                # Relative to pan_client directory
                pan_client_dir = Path(__file__).parent.parent
                entry_path = pan_client_dir / entry_path
            
            if not entry_path.exists():
                raise McpSessionError(f"MCP server entry point not found: {entry_path}")
            
            # Prepare command
            cmd = [self.stdio_binary, str(entry_path)] + self.args
            
            logger.info(f"Starting MCP server: {' '.join(cmd)}")
            
            # Start subprocess
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.env,
                cwd=entry_path.parent
            )
            
            # Create MCP client session
            server_params = StdioServerParameters(
                command=self.stdio_binary,
                args=[str(entry_path)] + self.args,
                env=self.env
            )
            
            self._exit_stack = AsyncExitStack()
            self._session = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            # Initialize the session
            await self._session.initialize()
            
            self._is_started = True
            logger.info("MCP session started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start MCP session: {e}")
            await self.dispose()
            raise McpSessionError(f"Failed to start MCP session: {e}") from e
    
    def _map_mcp_error(self, error: Exception) -> McpSessionError:
        """
        Map MCP tool errors to specific exception types.
        
        Args:
            error: Original error
            
        Returns:
            Mapped exception
        """
        error_str = str(error).lower()
        
        if 'timeout' in error_str or 'timed out' in error_str:
            return McpTimeoutError(f"Tool call timed out: {error}")
        elif 'rate limit' in error_str or 'rate_limit' in error_str or '429' in error_str:
            return McpRateLimitError(f"Rate limit exceeded: {error}")
        elif 'unauthorized' in error_str or 'auth' in error_str or '401' in error_str:
            return McpAuthError(f"Authentication failed: {error}")
        else:
            return McpSessionError(f"MCP tool error: {error}")
    
    async def invoke_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Invoke an MCP tool and return results.
        
        Args:
            name: Tool name to invoke
            **kwargs: Tool arguments
            
        Returns:
            Tool result as dict
            
        Raises:
            McpSessionNotStartedError: If session not started
            McpSessionError: If tool invocation fails
        """
        if not self._is_started or not self._session:
            raise McpSessionNotStartedError("MCP session not started")
        
        start_time = time.time()
        logger.info(f"Invoking MCP tool: {name}, args: {list(kwargs.keys())}")
        
        try:
            # Call the tool
            result = await self._session.call_tool(name, kwargs)
            
            duration = time.time() - start_time
            logger.info(f"MCP tool {name} completed in {duration:.2f}s")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"MCP tool {name} failed after {duration:.2f}s: {e}")
            raise self._map_mcp_error(e)
    
    async def dispose(self) -> None:
        """Clean shutdown of MCP session."""
        logger.info("Disposing MCP session")
        
        try:
            if self._exit_stack:
                await self._exit_stack.aclose()
                self._exit_stack = None
            
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
                self._process = None
            
            # Stop event loop
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._loop.stop)
            
            # Wait for loop thread to finish
            if self._loop_thread and self._loop_thread.is_alive():
                self._loop_thread.join(timeout=5)
            
            self._session = None
            self._loop = None
            self._loop_thread = None
            self._is_started = False
            
            logger.info("MCP session disposed successfully")
            
        except Exception as e:
            logger.error(f"Error disposing MCP session: {e}")
    
    def is_alive(self) -> bool:
        """
        Check if MCP session is alive.
        
        Returns:
            True if session is started and process is running
        """
        if not self._is_started or not self._process:
            return False
        
        return self._process.poll() is None
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available MCP tools.
        
        Returns:
            List of tool definitions
        """
        if not self._is_started or not self._session:
            raise McpSessionNotStartedError("MCP session not started")
        
        try:
            tools = await self._session.list_tools()
            return tools.tools
        except Exception as e:
            logger.error(f"Failed to get available tools: {e}")
            raise McpSessionError(f"Failed to get available tools: {e}") from e
    
    def get_session_info(self) -> Dict[str, Any]:
        """
        Get session information.
        
        Returns:
            Dict containing session status and configuration
        """
        return {
            'is_started': self._is_started,
            'is_alive': self.is_alive(),
            'entry_point': self.entry_point,
            'stdio_binary': self.stdio_binary,
            'args': self.args,
            'process_pid': self._process.pid if self._process else None,
        }
