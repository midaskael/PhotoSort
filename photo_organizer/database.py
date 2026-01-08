# -*- coding: utf-8 -*-
"""SQLite 数据库操作模块"""

import sqlite3
import time
from pathlib import Path
from typing import Optional


class Database:
    """数据库操作类"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = self._init_db()
    
    def _init_db(self) -> sqlite3.Connection:
        """初始化数据库"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        
        # 创建 hash_lib 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hash_lib (
                md5 TEXT NOT NULL,
                size INTEGER NOT NULL,
                method TEXT NOT NULL,
                first_path TEXT,
                added_at INTEGER NOT NULL,
                PRIMARY KEY (md5, size, method)
            );
        """)
        
        # 创建 file_state 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_state (
                src_path TEXT PRIMARY KEY,
                size INTEGER,
                mtime INTEGER,
                capture_time INTEGER,
                md5 TEXT,
                method TEXT,
                status TEXT NOT NULL,
                dest_path TEXT,
                dest_aae_path TEXT,
                dest_live_path TEXT,
                error TEXT,
                run_id TEXT,
                updated_at INTEGER NOT NULL
            );
        """)
        
        # 轻量迁移（兼容旧版数据库）
        self._migrate(conn)
        conn.commit()
        return conn
    
    def _migrate(self, conn: sqlite3.Connection):
        """数据库迁移：添加缺失的列"""
        columns_to_add = [
            ("capture_time", "INTEGER"),
            ("dest_aae_path", "TEXT"),
            ("dest_live_path", "TEXT"),
            ("run_id", "TEXT"),
        ]
        
        for col, coldef in columns_to_add:
            try:
                conn.execute(f"ALTER TABLE file_state ADD COLUMN {col} {coldef};")
            except sqlite3.OperationalError:
                pass  # 列已存在
        
        # 创建索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_state_status ON file_state(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_state_run_id ON file_state(run_id);")
    
    def is_processed(self, src_path: str) -> bool:
        """检查文件是否已处理"""
        cur = self.conn.execute(
            "SELECT status FROM file_state WHERE src_path=?", 
            (src_path,)
        )
        row = cur.fetchone()
        return bool(row and row[0] in ("moved", "duplicate"))
    
    def hash_exists(self, md5: str, size: int, method: str) -> bool:
        """检查 hash 是否存在于库中"""
        cur = self.conn.execute(
            "SELECT 1 FROM hash_lib WHERE md5=? AND size=? AND method=? LIMIT 1",
            (md5, size, method)
        )
        return cur.fetchone() is not None
    
    def get_hash_path(self, md5: str, size: int, method: str) -> Optional[str]:
        """获取 hash 对应的原始文件路径"""
        cur = self.conn.execute(
            "SELECT first_path FROM hash_lib WHERE md5=? AND size=? AND method=? LIMIT 1",
            (md5, size, method)
        )
        row = cur.fetchone()
        return row[0] if row else None
    
    def add_hash(self, md5: str, size: int, method: str, first_path: str):
        """添加 hash 到库中"""
        now = int(time.time())
        self.conn.execute("""
            INSERT OR IGNORE INTO hash_lib (md5, size, method, first_path, added_at)
            VALUES (?, ?, ?, ?, ?)
        """, (md5, size, method, first_path, now))
        self.conn.commit()
    
    def upsert_state(
        self,
        src_path: str,
        size: int,
        mtime: int,
        capture_time: int,
        md5: Optional[str],
        method: Optional[str],
        status: str,
        dest_path: Optional[str],
        dest_aae_path: Optional[str],
        dest_live_path: Optional[str],
        error: Optional[str],
        run_id: str
    ):
        """插入或更新文件状态"""
        now = int(time.time())
        self.conn.execute("""
            INSERT INTO file_state 
                (src_path, size, mtime, capture_time, md5, method, status, 
                 dest_path, dest_aae_path, dest_live_path, error, run_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(src_path) DO UPDATE SET
                size=excluded.size,
                mtime=excluded.mtime,
                capture_time=excluded.capture_time,
                md5=excluded.md5,
                method=excluded.method,
                status=excluded.status,
                dest_path=excluded.dest_path,
                dest_aae_path=excluded.dest_aae_path,
                dest_live_path=excluded.dest_live_path,
                error=excluded.error,
                run_id=excluded.run_id,
                updated_at=excluded.updated_at
        """, (src_path, size, mtime, capture_time, md5, method, status,
              dest_path, dest_aae_path, dest_live_path, error, run_id, now))
        self.conn.commit()
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
