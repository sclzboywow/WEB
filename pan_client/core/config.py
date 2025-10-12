import os
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_CONFIG_CACHE: Dict[str, Any] = {}

_DEF_BASE_URL = 'http://127.0.0.1:5000'


def _config_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'config.json')


def load_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE:
        return _CONFIG_CACHE
    cfg_path = _config_path()
    data: Dict[str, Any] = {}
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load config from {cfg_path}: {e}")
        data = {}
    _CONFIG_CACHE = data
    return _CONFIG_CACHE


def get_server_base_url() -> str:
    # 优先环境变量，其次配置文件，最后默认值
    env_url = os.environ.get('PAN_SERVER_BASE_URL')
    if env_url:
        return env_url
    cfg = load_config()
    return (cfg.get('base_url') or _DEF_BASE_URL).rstrip('/')


def is_mcp_mode() -> bool:
    """
    Check if MCP mode is enabled in configuration.
    
    Returns:
        True if MCP mode is configured
    """
    cfg = load_config()
    transport_config = cfg.get('transport', {})
    return transport_config.get('mode', 'rest') == 'mcp'


def get_mcp_config() -> Dict[str, Any]:
    """
    Get MCP configuration.
    
    Returns:
        Dict containing MCP configuration
    """
    cfg = load_config()
    transport_config = cfg.get('transport', {})
    return transport_config.get('mcp', {})


def get_transport_config() -> Dict[str, Any]:
    """
    Get transport configuration.
    
    Returns:
        Dict containing transport configuration
    """
    cfg = load_config()
    return cfg.get('transport', {'mode': 'rest'})


def get_download_dir() -> str:
    """
    Get download directory configuration.
    
    Returns:
        Download directory path
    """
    cfg = load_config()
    return cfg.get('download_dir', './downloads')


def get_rate_limit_config() -> Dict[str, Any]:
    """
    Get rate limit configuration.
    
    Returns:
        Dict containing rate limit settings
    """
    cfg = load_config()
    return cfg.get('rate_limit', {
        'requests_per_minute': 20,
        'burst_size': 5
    })


def get_timeout() -> int:
    """
    Get timeout configuration.
    
    Returns:
        Timeout in seconds
    """
    cfg = load_config()
    return cfg.get('timeout', 15)


def get_full_config() -> Dict[str, Any]:
    """
    Get full configuration with defaults applied.
    
    Returns:
        Complete configuration dict
    """
    cfg = load_config()
    
    # Apply defaults
    defaults = {
        'base_url': _DEF_BASE_URL,
        'transport': {
            'mode': 'rest',
            'mcp': {
                'stdio_binary': 'python',
                'entry': '../netdisk-mcp-server-stdio/netdisk.py',
                'args': ['--transport', 'stdio']
            }
        },
        'download_dir': './downloads',
        'rate_limit': {
            'requests_per_minute': 20,
            'burst_size': 5
        },
        'timeout': 15
    }
    
    # Merge with defaults
    merged = defaults.copy()
    merged.update(cfg)
    
    # Ensure nested dicts are merged properly
    if 'transport' in cfg:
        merged['transport'] = defaults['transport'].copy()
        merged['transport'].update(cfg['transport'])
        
        if 'mcp' in cfg['transport']:
            merged['transport']['mcp'] = defaults['transport']['mcp'].copy()
            merged['transport']['mcp'].update(cfg['transport']['mcp'])
    
    if 'rate_limit' in cfg:
        merged['rate_limit'] = defaults['rate_limit'].copy()
        merged['rate_limit'].update(cfg['rate_limit'])
    
    return merged


def clear_config_cache() -> None:
    """Clear the configuration cache."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
    logger.debug("Configuration cache cleared")