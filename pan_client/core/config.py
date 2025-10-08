import os
import json
from typing import Any, Dict

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
    except Exception:
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