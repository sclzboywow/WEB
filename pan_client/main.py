import sys
import os
import argparse
import asyncio
import logging
import signal
from typing import Optional

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from pan_client.ui.modern_pan import FileManagerUI
from pan_client.core.config import get_full_config, is_mcp_mode, setup_logging
from pan_client.core.client_factory import create_client_with_fallback
from pan_client.core.abstract_client import AbstractNetdiskClient

# Configure logging using config file
setup_logging()
logger = logging.getLogger(__name__)

# Global client instance for cleanup
_client: Optional[AbstractNetdiskClient] = None


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='云栈-您身边的共享资料库')
    parser.add_argument(
        '--use-mcp',
        action='store_true',
        help='Use MCP mode instead of REST mode'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--mcp-mode',
        choices=['local', 'ssh', 'tcp'],
        help='MCP connection mode (local=local stdio, ssh=SSH tunnel, tcp=TCP connection)'
    )
    parser.add_argument(
        '--mcp-host',
        type=str,
        help='MCP server host address'
    )
    parser.add_argument(
        '--mcp-port',
        type=int,
        help='MCP server port (TCP mode)'
    )
    return parser.parse_args()


def setup_config(args):
    """Setup configuration based on command line arguments."""
    config = get_full_config()
    
    # Override with MCP mode if requested
    if args.use_mcp:
        config['transport']['mode'] = 'mcp'
        logger.info("MCP mode enabled via command line")
    
    # CLI overrides for MCP mode
    if args.mcp_mode:
        mcp_mode = f"{args.mcp_mode}-stdio" if args.mcp_mode in ('local', 'ssh') else args.mcp_mode
        config['transport']['mcp']['mode'] = mcp_mode
        logger.info(f"MCP mode set to: {mcp_mode}")
    
    if args.mcp_host:
        if 'ssh' in config['transport']['mcp'].get('mode', ''):
            config['transport']['mcp']['ssh']['host'] = args.mcp_host
        else:
            config['transport']['mcp']['tcp']['host'] = args.mcp_host
        logger.info(f"MCP host set to: {args.mcp_host}")
    
    if args.mcp_port:
        config['transport']['mcp']['tcp']['port'] = args.mcp_port
        logger.info(f"MCP port set to: {args.mcp_port}")
    
    # Override config file if specified
    if args.config:
        import json
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                config.update(user_config)
                logger.info(f"Loaded configuration from {args.config}")
        except Exception as e:
            logger.error(f"Failed to load config from {args.config}: {e}")
    
    return config


def setup_logging(args):
    """Setup logging configuration."""
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")


async def cleanup_client():
    """Cleanup client resources."""
    global _client
    if _client:
        try:
            await _client.close()
            logger.info("Client cleanup completed")
        except Exception as e:
            logger.error(f"Error during client cleanup: {e}")
        finally:
            _client = None


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    
    # Run cleanup in event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(cleanup_client())
        else:
            asyncio.run(cleanup_client())
    except Exception as e:
        logger.error(f"Error during signal handling: {e}")
    
    sys.exit(0)


def main():
    """Main application entry point."""
    args = parse_args()
    setup_logging(args)
    
    logger.info("Starting 云栈-您身边的共享资料库")
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Load configuration
        config = setup_config(args)
        
        # Validate MCP configuration if using MCP mode
        if is_mcp_mode(config):
            from pan_client.core.config import validate_mcp_config
            mcp_config = config['transport']['mcp']
            errors = validate_mcp_config(mcp_config)
            if errors:
                logger.error("MCP配置错误：")
                for error in errors:
                    logger.error(f"  - {error}")
                sys.exit(1)
            
            logger.info(f"使用MCP模式: {mcp_config.get('mode')}")
            if mcp_config.get('mode') == 'ssh-stdio':
                logger.info(f"远程主机: {mcp_config['ssh']['host']}")
            elif mcp_config.get('mode') in ('tcp', 'tcp-tls'):
                logger.info(f"远程端点: {mcp_config['tcp']['host']}:{mcp_config['tcp']['port']}")
        
        # Create client
        global _client
        _client = create_client_with_fallback(config)
        
        # Log client info
        client_info = _client.get_client_info()
        logger.info(f"Created client: {client_info['type']} mode")
        
        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName('云栈-您身边的共享资料库')
        app.setQuitOnLastWindowClosed(False)
        
        # Create and show UI
        window = FileManagerUI(client=_client)
        window.show()
        
        logger.info("Application started successfully")
        
        # Run application
        sys.exit(app.exec())
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)
    
    finally:
        # Ensure cleanup
        try:
            asyncio.run(cleanup_client())
        except Exception as e:
            logger.error(f"Error during final cleanup: {e}")


if __name__ == '__main__':
    main()