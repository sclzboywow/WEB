#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库服务层
包含数据库初始化、连接和基础操作
"""

import os
import sqlite3

def init_sync_db():
    """
    初始化同步数据库
    创建所有必要的表结构
    """
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sync_data.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 确保初始化即切换到 WAL/启用外键/设置超时
    try:
        conn.execute('PRAGMA journal_mode=WAL')
    except Exception:
        pass
    try:
        conn.execute('PRAGMA foreign_keys=ON')
    except Exception:
        pass
    try:
        conn.execute('PRAGMA busy_timeout=5000')
    except Exception:
        pass
    
    # 创建同步任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_tasks (
            sync_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            status TEXT NOT NULL,
            total_files INTEGER DEFAULT 0,
            processed_files INTEGER DEFAULT 0,
            failed_files INTEGER DEFAULT 0,
            max_pages INTEGER DEFAULT 0,
            current_page INTEGER DEFAULT 0,
            start_time REAL,
            last_update REAL,
            client_id TEXT,
            is_resume INTEGER DEFAULT 0
        )
    ''')
    
    # 检查并添加 is_resume 字段（仅对旧数据库进行一次迁移）
    cursor.execute("PRAGMA table_info(sync_tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'is_resume' not in columns:
        try:
            cursor.execute('ALTER TABLE sync_tasks ADD COLUMN is_resume INTEGER DEFAULT 0')
            print("数据库迁移: 已添加 is_resume 字段")
        except sqlite3.OperationalError as e:
            print(f"数据库迁移失败: {e}")
    
    # 创建文件记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_name TEXT,
            file_size INTEGER,
            file_md5 TEXT,
            modify_time REAL,
            create_time REAL,
            category INTEGER,
            isdir INTEGER,
            fs_id INTEGER,
            status TEXT DEFAULT 'pending',
            error_msg TEXT,
            FOREIGN KEY (sync_id) REFERENCES sync_tasks (sync_id)
        )
    ''')

    # 为 file_path 增加索引，优化基于路径前缀的统计/查询
    try:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_records_path ON file_records(file_path)')
    except Exception:
        pass
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            avatar_url TEXT,
            role TEXT DEFAULT 'basic',
            registered_at REAL,
            last_login_at REAL
        )
    ''')
    
    # 创建支付绑定表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            account_no TEXT NOT NULL,
            account_name TEXT,
            status TEXT DEFAULT 'pending',
            verified_at REAL,
            deleted_at REAL,
            created_at REAL DEFAULT (strftime('%s','now')),
            updated_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # 数据库迁移：移除旧的密钥字段（如果存在）
    try:
        cursor.execute("PRAGMA table_info(payment_accounts)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'public_key' in columns or 'private_key' in columns:
            print("进行数据库迁移，移除密钥字段...")
            
            cursor.execute('''
                CREATE TABLE payment_accounts_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_no TEXT NOT NULL,
                    account_name TEXT,
                    status TEXT DEFAULT 'pending',
                    verified_at REAL,
                    deleted_at REAL,
                    created_at REAL DEFAULT (strftime('%s','now')),
                    updated_at REAL DEFAULT (strftime('%s','now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            cursor.execute('''
                INSERT INTO payment_accounts_new 
                (id, user_id, provider, account_no, account_name, status, verified_at, deleted_at, created_at, updated_at)
                SELECT id, user_id, provider, account_no, account_name, status, verified_at, deleted_at, created_at, updated_at
                FROM payment_accounts
            ''')
            
            cursor.execute('DROP TABLE payment_accounts')
            cursor.execute('ALTER TABLE payment_accounts_new RENAME TO payment_accounts')
            
            print("数据库迁移完成：已移除密钥字段")
            
    except Exception as e:
        print(f"数据库迁移过程中出现错误: {e}")
    
    # 创建会话表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            created_at REAL,
            expires_at REAL,
            user_agent TEXT,
            ip_address TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # 创建支付账户审计日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_account_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            remark TEXT,
            operator_id TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (account_id) REFERENCES payment_accounts(id)
        )
    ''')
    
    # 创建平台支付配置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS platform_payment_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL UNIQUE,
            public_key TEXT NOT NULL,
            private_key TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at REAL DEFAULT (strftime('%s','now')),
            updated_at REAL DEFAULT (strftime('%s','now'))
        )
    ''')
    
    # 创建交易相关表
    # 商品上架相关
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            listing_type TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            currency TEXT DEFAULT 'CNY',
            min_price_cents INTEGER,
            max_price_cents INTEGER,
            platform_split REAL DEFAULT 0.4,
            seller_split REAL DEFAULT 0.6,
            status TEXT DEFAULT 'draft',
            review_status TEXT DEFAULT 'pending',
            review_remark TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            updated_at REAL DEFAULT (strftime('%s','now')),
            published_at REAL,
            FOREIGN KEY (seller_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listing_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_name TEXT,
            file_size INTEGER,
            file_md5 TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listing_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            reviewer_id TEXT,
            status TEXT NOT NULL,
            remark TEXT,
            reviewed_at REAL,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        )
    ''')
    
    # 订单、支付、交付
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            buyer_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            total_amount_cents INTEGER NOT NULL,
            platform_fee_cents INTEGER NOT NULL,
            seller_amount_cents INTEGER NOT NULL,
            currency TEXT DEFAULT 'CNY',
            status TEXT DEFAULT 'pending',
            payment_status TEXT DEFAULT 'pending',
            created_at REAL DEFAULT (strftime('%s','now')),
            updated_at REAL DEFAULT (strftime('%s','now')),
            paid_at REAL,
            delivered_at REAL,
            completed_at REAL,
            remark TEXT,
            -- 退款相关（迁移时按需补齐）
            refund_status TEXT,                -- pending/approved/rejected/processed
            refund_requested_at REAL,
            refund_processed_at REAL,
            refund_reason TEXT,
            FOREIGN KEY (buyer_id) REFERENCES users(user_id),
            FOREIGN KEY (seller_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            price_cents INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            deliver_path TEXT,
            delivered_at REAL,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            transaction_id TEXT,
            amount_cents INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            payload TEXT,
            paid_at REAL,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    ''')

    # 退款申请表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS refund_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            buyer_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL DEFAULT (strftime('%s','now')),
            processed_at REAL,
            reviewer_id TEXT,
            remark TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (buyer_id) REFERENCES users(user_id),
            FOREIGN KEY (seller_id) REFERENCES users(user_id)
        )
    ''')

    # 风控事件表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS risk_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            reference_id TEXT,
            details TEXT,
            score INTEGER DEFAULT 0,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            buyer_id TEXT NOT NULL,
            file_path TEXT,
            download_count INTEGER DEFAULT 0,
            last_accessed_at REAL,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (listing_id) REFERENCES listings(id),
            FOREIGN KEY (buyer_id) REFERENCES users(user_id)
        )
    ''')
    
    # 钱包 / 提现 / 审计
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_wallets (
            user_id TEXT PRIMARY KEY,
            balance_cents INTEGER DEFAULT 0,
            pending_settlement_cents INTEGER DEFAULT 0,
            updated_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payout_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            method TEXT,
            account_info TEXT,
            remark TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            processed_at REAL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # 钱包流水表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallet_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            change_cents INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            type TEXT NOT NULL,
            reference_id TEXT,
            remark TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # 提现审核日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payout_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payout_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            reviewer_id TEXT,
            remark TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (payout_id) REFERENCES payout_requests(id)
        )
    ''')
    
    # 频控日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rate_limit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # 订单操作日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            user_id TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # 支付回调日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_callback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            transaction_id TEXT,
            status TEXT NOT NULL,
            payload TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    ''')
    
    # 通知表（基础）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            type TEXT DEFAULT 'info',
            status TEXT DEFAULT 'unread',
            sender_role TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            read_at REAL,
            -- 迭代1新增字段（兼容新增）
            target_scope TEXT DEFAULT 'user', -- user/role/all
            target_role TEXT,
            channel TEXT DEFAULT 'inbox',
            metadata TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    # 兼容迁移：如果旧表缺少新增列，则补齐
    try:
        cursor.execute("PRAGMA table_info(notifications)")
        cols = {row[1] for row in cursor.fetchall()}
        if 'target_scope' not in cols:
            cursor.execute("ALTER TABLE notifications ADD COLUMN target_scope TEXT DEFAULT 'user'")
        if 'target_role' not in cols:
            cursor.execute("ALTER TABLE notifications ADD COLUMN target_role TEXT")
        if 'channel' not in cols:
            cursor.execute("ALTER TABLE notifications ADD COLUMN channel TEXT DEFAULT 'inbox'")
        if 'metadata' not in cols:
            cursor.execute("ALTER TABLE notifications ADD COLUMN metadata TEXT")
    except Exception:
        pass

    # 索引（目标范围+时间）
    try:
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_notifications_target_scope_created_at
            ON notifications(target_scope, created_at DESC)
        ''')
    except Exception:
        pass

    # 事件表：用于点击/阅读追踪
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            event TEXT NOT NULL, -- read/view/click
            read_at REAL,
            viewed_at REAL,
            extra TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (notification_id) REFERENCES notifications(id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    # ===== 兼容性迁移：为旧库补齐 orders 表的退款相关字段 =====
    try:
        cursor.execute("PRAGMA table_info(orders)")
        ocols = {row[1] for row in cursor.fetchall()}
        if 'refund_status' not in ocols:
            cursor.execute("ALTER TABLE orders ADD COLUMN refund_status TEXT")
        if 'refund_requested_at' not in ocols:
            cursor.execute("ALTER TABLE orders ADD COLUMN refund_requested_at REAL")
        if 'refund_processed_at' not in ocols:
            cursor.execute("ALTER TABLE orders ADD COLUMN refund_processed_at REAL")
        if 'refund_reason' not in ocols:
            cursor.execute("ALTER TABLE orders ADD COLUMN refund_reason TEXT")
    except Exception:
        pass

    # ===== 索引补充 =====
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_refund_status ON orders(refund_status)")
    except Exception:
        pass
    # 财务对账相关索引
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status_completed ON orders(status, completed_at DESC)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_refund_combo ON orders(status, refund_status)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_refund_requests_status_created ON refund_requests(status, created_at DESC)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_refund_requests_status_processed ON refund_requests(status, processed_at DESC)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_events_user_created ON risk_events(user_id, created_at DESC)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payout_requests_status_processed ON payout_requests(status, processed_at DESC)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_logs_created ON wallet_logs(created_at DESC)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_logs_type ON wallet_logs(type)")
    except Exception:
        pass
    # 幂等与唯一性约束
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_order_payments_txnid ON order_payments(transaction_id)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_wallet_logs_dedupe ON wallet_logs(user_id, type, reference_id)")
    except Exception:
        pass
    
    conn.commit()
    conn.close()
    return db_path

def get_db_connection():
    """获取数据库连接"""
    db_path = init_sync_db()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
    except Exception:
        pass
    try:
        conn.execute('PRAGMA foreign_keys=ON')
    except Exception:
        pass
    try:
        conn.execute('PRAGMA busy_timeout=5000')
    except Exception:
        pass
    return conn
