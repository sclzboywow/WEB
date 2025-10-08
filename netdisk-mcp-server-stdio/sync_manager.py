#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目录同步管理器
支持断点续传、频控、进度跟踪
"""

import os
import json
import time
import hashlib
import sqlite3
import threading
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class SyncConfig:
    """同步配置"""
    base_url: str = "http://localhost:8000"
    access_token: str = ""
    client_id: str = ""
    rate_limit: int = 10  # 每分钟请求数
    batch_size: int = 100  # 每批处理文件数
    retry_times: int = 3  # 重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）
    db_path: str = "sync_progress.db"

class RateLimiter:
    """频控器"""
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
        self.lock = threading.Lock()
    
    def acquire(self) -> bool:
        """获取请求许可"""
        with self.lock:
            now = time.time()
            # 清理过期请求
            self.requests = [req_time for req_time in self.requests 
                           if now - req_time < self.time_window]
            
            if len(self.requests) >= self.max_requests:
                return False
            
            self.requests.append(now)
            return True
    
    def wait_if_needed(self):
        """如果需要等待，则等待"""
        while not self.acquire():
            time.sleep(1)

class SyncProgressDB:
    """同步进度数据库"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建同步任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_tasks (
                sync_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                status TEXT NOT NULL,
                total_files INTEGER DEFAULT 0,
                processed_files INTEGER DEFAULT 0,
                failed_files INTEGER DEFAULT 0,
                start_time REAL,
                last_update REAL,
                config TEXT
            )
        ''')
        
        # 创建文件记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                file_md5 TEXT,
                modify_time REAL,
                status TEXT DEFAULT 'pending',
                error_msg TEXT,
                FOREIGN KEY (sync_id) REFERENCES sync_tasks (sync_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_task(self, sync_id: str, path: str, config: Dict) -> bool:
        """创建同步任务"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO sync_tasks 
                (sync_id, path, status, start_time, last_update, config)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (sync_id, path, 'running', time.time(), time.time(), json.dumps(config)))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            return False
    
    def update_progress(self, sync_id: str, processed: int, failed: int = 0):
        """更新进度"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE sync_tasks 
                SET processed_files = ?, failed_files = ?, last_update = ?
                WHERE sync_id = ?
            ''', (processed, failed, time.time(), sync_id))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"更新进度失败: {e}")
    
    def get_task(self, sync_id: str) -> Optional[Dict]:
        """获取任务信息"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM sync_tasks WHERE sync_id = ?', (sync_id,))
            row = cursor.fetchone()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                task = dict(zip(columns, row))
                task['config'] = json.loads(task['config']) if task['config'] else {}
                return task
            
            conn.close()
            return None
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return None
    
    def add_file_record(self, sync_id: str, file_path: str, file_size: int = 0, 
                       file_md5: str = "", modify_time: float = 0):
        """添加文件记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO file_records 
                (sync_id, file_path, file_size, file_md5, modify_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (sync_id, file_path, file_size, file_md5, modify_time))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"添加文件记录失败: {e}")
            return False

class SyncManager:
    """同步管理器"""
    def __init__(self, config: SyncConfig):
        self.config = config
        self.db = SyncProgressDB(config.db_path)
        self.rate_limiter = RateLimiter(config.rate_limit)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'pan.baidu.com',
            'Content-Type': 'application/json'
        })
    
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        """发送请求（带频控）"""
        self.rate_limiter.wait_if_needed()
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            return None
    
    def get_file_list(self, path: str, start: int = 0, limit: int = 100) -> Optional[Dict]:
        """获取文件列表"""
        url = f"{self.config.base_url}/api/files"
        params = {
            'path': path,
            'start': start,
            'limit': limit,
            'client_id': self.config.client_id
        }
        
        return self._make_request('GET', url, params=params)
    
    def get_file_metas(self, fs_ids: List[int]) -> Optional[Dict]:
        """获取文件元数据"""
        url = f"{self.config.base_url}/api/multimedia/metas"
        data = {
            'fsids': fs_ids,
            'client_id': self.config.client_id
        }
        
        return self._make_request('POST', url, json=data)
    
    def scan_directory(self, path: str, sync_id: str) -> int:
        """扫描目录，获取所有文件信息"""
        logger.info(f"开始扫描目录: {path}")
        
        all_files = []
        start = 0
        limit = self.config.batch_size
        
        while True:
            result = self.get_file_list(path, start, limit)
            if not result or result.get('status') != 'success':
                logger.error(f"获取文件列表失败: {result}")
                break
            
            files = result.get('files', [])
            if not files:
                break
            
            # 只处理文件，跳过目录
            file_list = [f for f in files if f.get('isdir', 1) == 0]
            all_files.extend(file_list)
            
            # 添加文件记录到数据库
            for file_info in file_list:
                self.db.add_file_record(
                    sync_id=sync_id,
                    file_path=file_info.get('path', ''),
                    file_size=file_info.get('size', 0),
                    file_md5=file_info.get('md5', ''),
                    modify_time=file_info.get('server_mtime', 0)
                )
            
            start += limit
            
            # 检查是否还有更多文件
            if not result.get('has_more', False):
                break
            
            logger.info(f"已扫描 {len(all_files)} 个文件...")
        
        # 更新总文件数
        conn = sqlite3.connect(self.config.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sync_tasks 
            SET total_files = ? 
            WHERE sync_id = ?
        ''', (len(all_files), sync_id))
        conn.commit()
        conn.close()
        
        logger.info(f"目录扫描完成，共发现 {len(all_files)} 个文件")
        return len(all_files)
    
    def sync_directory(self, path: str) -> str:
        """同步指定目录"""
        sync_id = f"sync_{int(time.time())}_{hashlib.md5(path.encode()).hexdigest()[:8]}"
        
        # 创建同步任务
        config_dict = {
            'base_url': self.config.base_url,
            'access_token': self.config.access_token,
            'client_id': self.config.client_id,
            'rate_limit': self.config.rate_limit,
            'batch_size': self.config.batch_size
        }
        
        if not self.db.create_task(sync_id, path, config_dict):
            raise Exception("创建同步任务失败")
        
        logger.info(f"开始同步目录: {path} (任务ID: {sync_id})")
        
        try:
            # 扫描目录
            total_files = self.scan_directory(path, sync_id)
            
            # 更新任务状态为完成
            conn = sqlite3.connect(self.config.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sync_tasks 
                SET status = 'completed', last_update = ?
                WHERE sync_id = ?
            ''', (time.time(), sync_id))
            conn.commit()
            conn.close()
            
            logger.info(f"同步完成: {path} (共 {total_files} 个文件)")
            return sync_id
            
        except Exception as e:
            logger.error(f"同步失败: {e}")
            
            # 更新任务状态为失败
            conn = sqlite3.connect(self.config.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sync_tasks 
                SET status = 'failed', last_update = ?
                WHERE sync_id = ?
            ''', (time.time(), sync_id))
            conn.commit()
            conn.close()
            
            raise e
    
    def get_sync_status(self, sync_id: str) -> Optional[Dict]:
        """获取同步状态"""
        task = self.db.get_task(sync_id)
        if not task:
            return None
        
        # 计算进度
        total = task['total_files']
        processed = task['processed_files']
        progress = processed / total if total > 0 else 0.0
        
        return {
            'sync_id': sync_id,
            'path': task['path'],
            'status': task['status'],
            'progress': progress,
            'total_files': total,
            'processed_files': processed,
            'failed_files': task['failed_files'],
            'start_time': task['start_time'],
            'last_update': task['last_update']
        }

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='目录同步管理器')
    parser.add_argument('--path', required=True, help='要同步的目录路径')
    parser.add_argument('--token', required=True, help='访问令牌')
    parser.add_argument('--client-id', required=True, help='客户端ID')
    parser.add_argument('--base-url', default='http://localhost:8000', help='API基础URL')
    parser.add_argument('--rate-limit', type=int, default=10, help='每分钟请求数限制')
    
    args = parser.parse_args()
    
    # 创建配置
    config = SyncConfig(
        base_url=args.base_url,
        access_token=args.token,
        client_id=args.client_id,
        rate_limit=args.rate_limit
    )
    
    # 创建同步管理器
    sync_manager = SyncManager(config)
    
    try:
        # 开始同步
        sync_id = sync_manager.sync_directory(args.path)
        print(f"同步任务已创建: {sync_id}")
        
        # 监控进度
        while True:
            status = sync_manager.get_sync_status(sync_id)
            if not status:
                print("无法获取同步状态")
                break
            
            print(f"进度: {status['processed_files']}/{status['total_files']} "
                  f"({status['progress']:.1%}) - {status['status']}")
            
            if status['status'] in ['completed', 'failed']:
                break
            
            time.sleep(5)
        
        print(f"同步完成，状态: {status['status']}")
        
    except KeyboardInterrupt:
        print("\n同步被用户中断")
    except Exception as e:
        print(f"同步失败: {e}")

if __name__ == '__main__':
    main()
