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

def get_mcp_transport_config() -> Dict[str, Any]:
    """Get MCP transport configuration based on mode."""
    config = load_config()
    mcp_config = config.get('transport', {}).get('mcp', {})
    
    mode = mcp_config.get('mode', 'local-stdio')
    
    if mode == 'ssh-stdio':
        ssh = mcp_config.get('ssh', {})
        return {
            'mode': mode,
            'ssh': {
                'host': ssh.get('host'),
                'user': ssh.get('user', 'netdisk'),
                'identity_file': ssh.get('identity_file'),
                'command': ssh.get('command', 'python3 /srv/netdisk/netdisk.py --transport stdio')
            }
        }
    elif mode in ('tcp', 'tcp-tls'):
        tcp = mcp_config.get('tcp', {})
        return {
            'mode': mode,
            'tcp': {
                'host': tcp.get('host', 'localhost'),
                'port': tcp.get('port', 8765),
                'tls': tcp.get('tls', False),
                'cert_file': tcp.get('cert_file'),
                'key_file': tcp.get('key_file')
            }
        }
    else:
        return {
            'mode': 'local-stdio',
            'stdio_binary': mcp_config.get('stdio_binary', 'python'),
            'entry': mcp_config.get('entry', '../netdisk-mcp-server-stdio/netdisk.py'),
            'args': mcp_config.get('args', ['--transport', 'stdio'])
        }

def validate_mcp_config(config: Dict) -> List[str]:
    """Validate MCP configuration and return list of errors."""
    errors = []
    mode = config.get('mode', 'local-stdio')
    
    if mode == 'ssh-stdio':
        ssh = config.get('ssh', {})
        if not ssh.get('host'):
            errors.append("SSH模式需要配置 ssh.host")
        identity_file = ssh.get('identity_file') or os.path.expanduser('~/.ssh/id_rsa')
        if not os.path.exists(identity_file):
            # Try alternative key locations
            found_key = False
            for key_name in ['id_ed25519', 'id_rsa']:
                key_path = os.path.expanduser(f'~/.ssh/{key_name}')
                if os.path.exists(key_path):
                    found_key = True
                    break
            if not found_key:
                errors.append(f"SSH密钥文件不存在: {identity_file}")
    elif mode in ('tcp', 'tcp-tls'):
        tcp = config.get('tcp', {})
        if not tcp.get('host'):
            errors.append("TCP模式需要配置 tcp.host")
        if tcp.get('tls'):
            if tcp.get('cert_file') and not os.path.exists(tcp.get('cert_file')):
                errors.append(f"TLS证书文件不存在: {tcp.get('cert_file')}")
            if tcp.get('key_file') and not os.path.exists(tcp.get('key_file')):
                errors.append(f"TLS私钥文件不存在: {tcp.get('key_file')}")
    
    return errors


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


def get_logging_config() -> Dict[str, Any]:
    """
    Get logging configuration.
    
    Returns:
        Dictionary containing logging settings
    """
    config = load_config()
    return config.get('logging', {
        'level': 'INFO',
        'format': 'text',  # 'text' or 'json'
        'file': None,  # Optional log file path
        'mcp_debug': False  # Enable detailed MCP logging
    })


def get_mcp_logging_config() -> Dict[str, Any]:
    """
    Get MCP-specific logging configuration.
    
    Returns:
        Dictionary containing MCP logging settings
    """
    logging_config = get_logging_config()
    return {
        'level': logging_config.get('level', 'INFO'),
        'format': logging_config.get('format', 'text'),
        'debug': logging_config.get('mcp_debug', False),
        'file': logging_config.get('file')
    }


def setup_logging() -> None:
    """
    Setup logging configuration based on config file.
    """
    config = get_logging_config()
    
    # Set logging level
    level = getattr(logging, config['level'].upper(), logging.INFO)
    logging.basicConfig(level=level)
    
    # Configure MCP logger specifically
    mcp_logger = logging.getLogger('pan_client.core.mcp_session')
    mcp_config = get_mcp_logging_config()
    
    if mcp_config['debug']:
        mcp_logger.setLevel(logging.DEBUG)
    else:
        mcp_logger.setLevel(logging.INFO)
    
    # Set up formatter
    if config['format'] == 'json':
        import json
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    'timestamp': self.formatTime(record),
                    'level': record.levelname,
                    'logger': record.name,
                    'message': record.getMessage(),
                }
                if hasattr(record, 'extra') and record.extra:
                    log_entry.update(record.extra)
                return json.dumps(log_entry, ensure_ascii=False)
        
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Apply formatter to handlers
    for handler in logging.root.handlers:
        handler.setFormatter(formatter)
    
    # Configure file logging if specified
    if config['file']:
        file_handler = logging.FileHandler(config['file'], encoding='utf-8')
        file_handler.setFormatter(formatter)
        logging.root.addHandler(file_handler)


def clear_config_cache() -> None:
    """Clear the configuration cache."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
    logger.debug("Configuration cache cleared")