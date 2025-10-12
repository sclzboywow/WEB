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

from .mcp_metrics import McpMetrics

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
        
        # Extract connection mode
        self.mode = self.mcp_config.get('mode', 'local-stdio')
        
        # Extract configuration based on mode
        if self.mode == 'local-stdio':
            self.stdio_binary = self.mcp_config.get('stdio_binary', 'python')
            self.entry_point = self.mcp_config.get('entry', '../netdisk-mcp-server-stdio/netdisk.py')
            self.args = self.mcp_config.get('args', ['--transport', 'stdio'])
        elif self.mode == 'ssh-stdio':
            self.ssh_config = self.mcp_config.get('ssh', {})
            self.ssh_host = self.ssh_config.get('host')
            self.ssh_user = self.ssh_config.get('user', 'netdisk')
            self.ssh_identity_file = self.ssh_config.get('identity_file')
            self.ssh_command = self.ssh_config.get('command', 'python3 /srv/netdisk/netdisk.py --transport stdio')
        elif self.mode in ('tcp', 'tcp-tls'):
            self.tcp_config = self.mcp_config.get('tcp', {})
            self.tcp_host = self.tcp_config.get('host', 'localhost')
            self.tcp_port = self.tcp_config.get('port', 8765)
            self.tcp_tls = self.tcp_config.get('tls', False)
            self.tcp_cert_file = self.tcp_config.get('cert_file')
            self.tcp_key_file = self.tcp_config.get('key_file')
        else:
            raise McpSessionError(f"Unsupported MCP mode: {self.mode}")
        
        # Environment setup
        self.env = os.environ.copy()
        self._setup_environment()
        
        # Initialize metrics collection
        self.metrics = McpMetrics()
        
        logger.info("McpSession initialized", extra={
            "mode": self.mode,
            "entry_point": getattr(self, 'entry_point', None),
            "stdio_binary": getattr(self, 'stdio_binary', None),
            "args": getattr(self, 'args', None),
            "ssh_host": getattr(self, 'ssh_host', None),
            "tcp_endpoint": f"{getattr(self, 'tcp_host', None)}:{getattr(self, 'tcp_port', None)}" if hasattr(self, 'tcp_host') else None
        })
    
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
    
    async def _start_local_stdio(self):
        """Start local stdio subprocess."""
        if not self.entry_point:
            raise McpSessionError("Entry point not configured")
        
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
        
        start_time = time.time()
        logger.info("Starting local MCP server", extra={
            "command": ' '.join(cmd),
            "entry_path": str(entry_path),
            "working_dir": str(entry_path.parent),
            "timestamp": start_time
        })
        
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
        
        startup_duration = time.time() - start_time
        logger.info("Local stdio MCP session started", extra={
            "startup_duration": startup_duration,
            "process_id": self._process.pid if self._process else None,
            "timestamp": time.time()
        })

    async def _start_ssh_stdio(self):
        """Start SSH stdio connection to remote server."""
        if not self.ssh_host:
            raise McpSessionError("SSH host not configured")
        
        # Determine identity file
        identity_file = self.ssh_identity_file
        if not identity_file:
            # Try common SSH key locations
            for key_name in ['id_ed25519', 'id_rsa']:
                key_path = os.path.expanduser(f'~/.ssh/{key_name}')
                if os.path.exists(key_path):
                    identity_file = key_path
                    break
        
        if not identity_file or not os.path.exists(identity_file):
            raise McpSessionError(f"SSH identity file not found: {identity_file}")
        
        # Build SSH command
        ssh_cmd = ['ssh', '-i', identity_file, f'{self.ssh_user}@{self.ssh_host}', self.ssh_command]
        
        start_time = time.time()
        logger.info("Starting SSH stdio MCP connection", extra={
            "ssh_host": self.ssh_host,
            "ssh_user": self.ssh_user,
            "identity_file": identity_file,
            "remote_command": self.ssh_command,
            "timestamp": start_time
        })
        
        # Prepare server parameters
        server_params = StdioServerParameters(
            command=ssh_cmd[0],
            args=ssh_cmd[1:],
            env=self.env
        )
        
        # Create stdio transport
        self._exit_stack = AsyncExitStack()
        self._session = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        
        # Initialize the session
        await self._session.initialize()
        
        startup_duration = time.time() - start_time
        logger.info("SSH stdio MCP session started", extra={
            "startup_duration": startup_duration,
            "ssh_host": self.ssh_host,
            "ssh_user": self.ssh_user,
            "timestamp": time.time()
        })

    async def _start_tcp(self):
        """Start TCP connection to remote server."""
        try:
            start_time = time.time()
            logger.info("Starting TCP MCP connection", extra={
                "tcp_host": self.tcp_host,
                "tcp_port": self.tcp_port,
                "tls_enabled": self.tcp_tls,
                "timestamp": start_time
            })
            
            if self.tcp_tls:
                # TLS mode
                import ssl
                ssl_context = ssl.create_default_context()
                
                if self.tcp_cert_file and self.tcp_key_file:
                    ssl_context.load_cert_chain(self.tcp_cert_file, self.tcp_key_file)
                
                # Use MCP's TLS TCP client
                from mcp.client.tcp import tcp_client_tls
                tcp_transport = await tcp_client_tls(self.tcp_host, self.tcp_port, ssl_context)
            else:
                # Pure TCP mode
                from mcp.client.tcp import tcp_client
                tcp_transport = await tcp_client(self.tcp_host, self.tcp_port)
            
            read, write = tcp_transport
            self._session = ClientSession(read, write)
            await self._session.initialize()
            
            startup_duration = time.time() - start_time
            logger.info("TCP MCP session started", extra={
                "startup_duration": startup_duration,
                "tcp_host": self.tcp_host,
                "tcp_port": self.tcp_port,
                "tls_enabled": self.tcp_tls,
                "cert_file": self.tcp_cert_file,
                "timestamp": time.time()
            })
            
        except ImportError as e:
            raise McpSessionError(f"MCP TCP client not available: {e}")
        except Exception as e:
            raise McpSessionError(f"Failed to establish TCP connection: {e}")

    async def ensure_started(self) -> None:
        """
        Ensure MCP session is started.
        
        Launches the MCP server subprocess or establishes remote connection based on mode.
        """
        if self._is_started:
            return
        
        try:
            # Start event loop thread first
            if not self._loop:
                self._start_event_loop_thread()
            
            # Start based on mode
            if self.mode == 'local-stdio':
                await self._start_local_stdio()
            elif self.mode == 'ssh-stdio':
                await self._start_ssh_stdio()
            elif self.mode in ('tcp', 'tcp-tls'):
                await self._start_tcp()
            else:
                raise McpSessionError(f"Unsupported MCP mode: {self.mode}")
            
            self._is_started = True
            logger.info(f"MCP session started successfully in {self.mode} mode")
            
        except Exception as e:
            logger.error(f"Failed to start MCP session in {self.mode} mode", extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "mode": self.mode,
                "timestamp": time.time()
            })
            await self.dispose()
            raise McpSessionError(f"MCP连接失败 ({self.mode}): {str(e)}") from e
    
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
        params_count = len(kwargs)
        
        # Log tool invocation start
        logger.info("MCP tool invocation started", extra={
            "tool": name,
            "params_count": params_count,
            "params_keys": list(kwargs.keys()),
            "timestamp": start_time
        })
        
        try:
            # Call the tool
            result = await self._session.call_tool(name, kwargs)
            
            duration = time.time() - start_time
            result_size = len(str(result)) if result else 0
            
            # Record successful call metrics
            self.metrics.record_call(
                tool_name=name,
                duration=duration,
                success=True,
                params_count=params_count,
                result_size=result_size
            )
            
            # Record network latency for remote connections
            if self.mode in ('ssh-stdio', 'tcp', 'tcp-tls'):
                self.metrics.record_network_latency(duration * 1000)  # Convert to ms
            
            # Log successful completion
            logger.info("MCP tool completed successfully", extra={
                "tool": name,
                "duration": duration,
                "result_size": result_size,
                "mode": self.mode,
                "timestamp": time.time()
            })
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            error_type = type(e).__name__
            error_message = str(e)
            
            # Record failed call metrics
            self.metrics.record_call(
                tool_name=name,
                duration=duration,
                success=False,
                error_type=error_type,
                error_message=error_message,
                params_count=params_count
            )
            
            # Log error
            logger.error("MCP tool failed", extra={
                "tool": name,
                "duration": duration,
                "error_type": error_type,
                "error_message": error_message,
                "timestamp": time.time()
            })
            
            raise self._map_mcp_error(e)
    
    async def dispose(self) -> None:
        """Clean shutdown of MCP session."""
        dispose_start = time.time()
        logger.info("Disposing MCP session", extra={
            "timestamp": dispose_start,
            "session_duration": dispose_start - self.metrics.session_start_time
        })
        
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
            
            # Log final metrics
            final_stats = self.metrics.get_stats()
            dispose_duration = time.time() - dispose_start
            
            logger.info("MCP session disposed successfully", extra={
                "dispose_duration": dispose_duration,
                "total_calls": final_stats['call_count'],
                "total_errors": final_stats['error_count'],
                "error_rate": final_stats['error_rate'],
                "avg_duration": final_stats['avg_duration'],
                "session_duration": final_stats['session_duration'],
                "timestamp": time.time()
            })
            
        except Exception as e:
            logger.error("Error disposing MCP session", extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": time.time()
            })
    
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
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current MCP session metrics.
        
        Returns:
            Dictionary containing performance metrics and statistics
        """
        return self.metrics.get_stats()
    
    def get_metrics_summary(self) -> str:
        """
        Get a human-readable summary of current metrics.
        
        Returns:
            String summary of current metrics
        """
        return self.metrics.get_summary()
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information."""
        info = {
            'mode': self.mode,
            'is_connected': self.is_alive(),
            'session_start_time': self.metrics.session_start_time
        }
        
        if self.mode == 'ssh-stdio':
            info['remote_host'] = f"{self.ssh_user}@{self.ssh_host}"
        elif self.mode in ('tcp', 'tcp-tls'):
            info['remote_endpoint'] = f"{self.tcp_host}:{self.tcp_port}"
            info['encrypted'] = self.tcp_tls
        
        return info

    def get_session_info(self) -> Dict[str, Any]:
        """
        Get session information.
        
        Returns:
            Dict containing session status and configuration
        """
        return {
            'is_started': self._is_started,
            'is_alive': self.is_alive(),
            'entry_point': getattr(self, 'entry_point', None),
            'stdio_binary': getattr(self, 'stdio_binary', None),
            'args': getattr(self, 'args', None),
            'process_pid': self._process.pid if self._process else None,
            'mode': self.mode,
            'session_start_time': self.metrics.session_start_time,
            'call_count': self.metrics.call_count,
            'error_count': self.metrics.error_count,
            'health_score': self.metrics.get_summary().get('health_score', 0)
        }

    async def _check_connection(self) -> bool:
        """Check if connection is alive by pinging server."""
        if not self._session:
            return False
        
        try:
            # Try to get available tools as a ping
            await self._session.list_tools()
            return True
        except Exception:
            return False

    async def _reconnect(self, max_retries: int = 3) -> bool:
        """Reconnect with exponential backoff."""
        # Record connection drop
        self.metrics.record_connection_event('drop')
        
        for attempt in range(max_retries):
            wait_time = 2 ** attempt  # 2s, 4s, 8s
            self.metrics.record_connection_event('reconnect_attempt')
            
            logger.info(f"尝试重连MCP服务器 (第{attempt+1}次)，等待{wait_time}秒...", extra={
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "wait_time": wait_time,
                "mode": self.mode,
                "timestamp": time.time()
            })
            await asyncio.sleep(wait_time)
            
            try:
                await self.dispose()
                self._is_started = False
                await self.ensure_started()
                
                # Record successful reconnection
                self.metrics.record_connection_event('reconnect_success')
                
                logger.info("MCP重连成功", extra={
                    "attempt": attempt + 1,
                    "mode": self.mode,
                    "timestamp": time.time()
                })
                return True
            except Exception as e:
                logger.warning(f"重连失败: {e}", extra={
                    "attempt": attempt + 1,
                    "error": str(e),
                    "mode": self.mode,
                    "timestamp": time.time()
                })
        
        logger.error("MCP重连失败，已达到最大重试次数", extra={
            "max_retries": max_retries,
            "mode": self.mode,
            "timestamp": time.time()
        })
        return False
