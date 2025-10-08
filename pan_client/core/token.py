import os
import json
from typing import Optional, Dict, Any, List

_TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'token.json')


# -------------------- 基础读写 --------------------
def _load_store() -> Dict[str, Any]:
    """读取多账号存储结构；兼容旧格式。"""
    try:
        if os.path.exists(_TOKEN_FILE):
            with open(_TOKEN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
    except Exception:
        data = {}

    # 兼容旧版：root 上直接有 access_token
    if 'accounts' not in data and 'access_token' in data:
        legacy_token = data.get('access_token')
        user = data.get('user') or {}
        account_id = str(user.get('uk') or user.get('userid') or 'default')
        data = {
            'current': account_id,
            'accounts': {
                account_id: {
                    'access_token': legacy_token,
                    'refresh_token': data.get('refresh_token'),
                    'user': user,
                }
            }
        }
    # 初始空结构
    if 'accounts' not in data:
        data = {'current': None, 'accounts': {}}
    return data


def _save_store(store: Dict[str, Any]) -> None:
    try:
        with open(_TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# -------------------- 兼容旧API（指向当前账号） --------------------
def load_token() -> Dict[str, Any]:
    return _load_store()


def save_token(data: Dict[str, Any]) -> None:
    # 为保持兼容：若传入旧结构，则写到当前账号 default
    store = _load_store()
    if 'accounts' in data:
        _save_store(data)
        return
    token = data.get('access_token')
    if token:
        set_access_token(token)


def get_access_token(account_id: Optional[str] = None) -> Optional[str]:
    store = _load_store()
    account_id = account_id or store.get('current')
    if not account_id:
        return None
    acc = store.get('accounts', {}).get(account_id) or {}
    return acc.get('access_token')


def set_access_token(token: str, account_id: Optional[str] = None, user: Optional[Dict[str, Any]] = None) -> None:
    store = _load_store()
    # 默认账户 id
    if not account_id:
        account_id = str((user or {}).get('uk') or (user or {}).get('userid') or store.get('current') or 'default')
    acc = store.setdefault('accounts', {}).get(account_id) or {}
    acc['access_token'] = token
    if user:
        acc['user'] = user
    store['accounts'][account_id] = acc
    store['current'] = account_id
    _save_store(store)


def clear_token(account_id: Optional[str] = None) -> None:
    """清空指定账号令牌；若不指定则清空当前账号。"""
    store = _load_store()
    account_id = account_id or store.get('current')
    if not account_id:
        _save_store({'current': None, 'accounts': {}})
        return
    acc = store.get('accounts', {}).get(account_id)
    if acc is not None:
        acc['access_token'] = None
        store['accounts'][account_id] = acc
    _save_store(store)


# -------------------- 多账号管理 API --------------------
def upsert_account(account_id: str, access_token: str, user: Optional[Dict[str, Any]] = None, refresh_token: Optional[str] = None, set_current: bool = True) -> None:
    store = _load_store()
    acc = store.setdefault('accounts', {}).get(account_id) or {}
    if access_token is not None:
        acc['access_token'] = access_token
    if refresh_token is not None:
        acc['refresh_token'] = refresh_token
    if user is not None:
        acc['user'] = user
    store['accounts'][account_id] = acc
    if set_current:
        store['current'] = account_id
    _save_store(store)


def switch_account(account_id: str) -> bool:
    store = _load_store()
    if account_id in store.get('accounts', {}):
        store['current'] = account_id
        _save_store(store)
        return True
    return False


def remove_account(account_id: str) -> bool:
    store = _load_store()
    if account_id in store.get('accounts', {}):
        store['accounts'].pop(account_id, None)
        if store.get('current') == account_id:
            store['current'] = next(iter(store['accounts'].keys()), None)
        _save_store(store)
        return True
    return False


def list_accounts() -> List[Dict[str, Any]]:
    store = _load_store()
    current = store.get('current')
    results: List[Dict[str, Any]] = []
    for acc_id, acc in store.get('accounts', {}).items():
        user = acc.get('user') or {}
        name = (
            user.get('baidu_name')
            or user.get('netdisk_name')
            or user.get('user_name')
            or user.get('uname')
            or str(user.get('uk') or user.get('userid') or acc_id)
        )
        results.append({
            'id': acc_id,
            'name': name,
            'is_current': acc_id == current,
            'has_token': bool(acc.get('access_token')),
        })
    return results


def migrate_accounts() -> bool:
    """将旧的非UK账号（如 'default'）迁移为 uk 作为ID，合并重复账号。
    返回是否发生变更。
    """
    store = _load_store()
    accounts = dict(store.get('accounts', {}))
    changed = False
    for acc_id, acc in list(accounts.items()):
        user = acc.get('user') or {}
        uk = user.get('uk') or user.get('userid')
        if uk is None:
            continue
        target_id = str(uk)
        # 仅迁移旧账号ID：'default' 或 非纯数字的历史键，避免误把其他有效账号合并
        if acc_id == target_id or (acc_id != 'default' and acc_id.isdigit()):
            continue
        # 需要迁移到 target_id
        target = accounts.get(target_id)
        if target:
            # 合并信息：保留有token者、合并user
            if acc.get('access_token') and not target.get('access_token'):
                target['access_token'] = acc.get('access_token')
            if user and not target.get('user'):
                target['user'] = user
            accounts[target_id] = target
        else:
            accounts[target_id] = acc
        # 删除旧键
        if acc_id in accounts:
            del accounts[acc_id]
        if store.get('current') == acc_id:
            store['current'] = target_id
        changed = True
    if changed:
        store['accounts'] = accounts
        _save_store(store)
    return changed


def set_current_account(account_id: str) -> bool:
    """强制设置当前账号，不校验是否有token。"""
    store = _load_store()
    if account_id in store.get('accounts', {}):
        store['current'] = account_id
        _save_store(store)
        return True
    return False