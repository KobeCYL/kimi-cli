"""SQLite 存储后端实现

使用 sqlite-vec 扩展支持向量检索，FTS5 支持全文检索
"""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import threading

from kimi_cli.memory.adapters.storage.base import StorageBackend
from kimi_cli.memory.models.data import Session, Message, RecallResult, SearchQuery


class SQLiteStorage(StorageBackend):
    """SQLite 存储后端
    
    特性:
    - 单文件存储
    - 支持FTS5全文检索
    - 支持sqlite-vec向量检索
    - 线程安全
    """
    
    def __init__(self, db_path: str = "~/.kimi/memory/memory.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._connection: Optional[sqlite3.Connection] = None
        self._vec_available = False
        
    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._enable_extensions()
        return self._local.conn
    
    def _enable_extensions(self):
        """启用SQLite扩展"""
        conn = self._local.conn
        try:
            # 尝试加载 sqlite-vec
            conn.enable_load_extension(True)
            conn.load_extension("vec0")
            self._vec_available = True
        except Exception:
            self._vec_available = False
    
    def initialize(self) -> None:
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 创建会话表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT,
                keywords TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                token_count INTEGER DEFAULT 0,
                work_dir TEXT,
                is_archived BOOLEAN DEFAULT 0,
                sync_status TEXT DEFAULT 'local',
                sync_version INTEGER DEFAULT 1
            )
        """)
        
        # 创建消息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER DEFAULT 0,
                timestamp INTEGER NOT NULL,
                has_code BOOLEAN DEFAULT 0,
                code_language TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_time 
            ON messages(session_id, timestamp)
        """)
        
        # 创建FTS5虚拟表 (全文搜索)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                title,
                summary,
                keywords,
                content='sessions',
                content_rowid='rowid'
            )
        """)
        
        # FTS5 同步触发器
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS sessions_fts_insert 
            AFTER INSERT ON sessions BEGIN
                INSERT INTO sessions_fts(rowid, title, summary, keywords)
                VALUES (new.rowid, new.title, new.summary, new.keywords);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS sessions_fts_update 
            AFTER UPDATE ON sessions BEGIN
                UPDATE sessions_fts SET 
                    title = new.title,
                    summary = new.summary,
                    keywords = new.keywords
                WHERE rowid = old.rowid;
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS sessions_fts_delete 
            AFTER DELETE ON sessions BEGIN
                DELETE FROM sessions_fts WHERE rowid = old.rowid;
            END
        """)
        
        # 创建向量表 (如果 sqlite-vec 可用)
        if self._vec_available:
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS session_vectors USING vec0(
                        session_id TEXT PRIMARY KEY,
                        embedding FLOAT[384]
                    )
                """)
            except Exception:
                self._vec_available = False
        
        # 同步日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                session_id TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                timestamp INTEGER NOT NULL
            )
        """)
        
        conn.commit()
    
    def close(self) -> None:
        """关闭连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
    
    # ==================== Session 操作 ====================
    
    def create_session(self, session: Session) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions 
            (id, title, summary, keywords, created_at, updated_at, token_count, 
             work_dir, is_archived, sync_status, sync_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.id, session.title, session.summary,
            json.dumps(session.keywords, ensure_ascii=False),
            session.created_at, session.updated_at, session.token_count,
            session.work_dir, session.is_archived, session.sync_status.value,
            session.sync_version
        ))
        conn.commit()
    
    def get_session(self, session_id: str) -> Optional[Session]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE id = ?", 
            (session_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_session(row)
        return None
    
    def update_session(self, session: Session) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        session.updated_at = int(__import__('time').time())
        cursor.execute("""
            UPDATE sessions SET
                title = ?,
                summary = ?,
                keywords = ?,
                updated_at = ?,
                token_count = ?,
                work_dir = ?,
                is_archived = ?,
                sync_status = ?,
                sync_version = ?
            WHERE id = ?
        """, (
            session.title, session.summary,
            json.dumps(session.keywords, ensure_ascii=False),
            session.updated_at, session.token_count,
            session.work_dir, session.is_archived,
            session.sync_status.value, session.sync_version,
            session.id
        ))
        conn.commit()
    
    def list_sessions(
        self, 
        limit: int = 100, 
        offset: int = 0,
        archived: Optional[bool] = None
    ) -> List[Session]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if archived is not None:
            cursor.execute(
                "SELECT * FROM sessions WHERE is_archived = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (archived, limit, offset)
            )
        else:
            cursor.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        
        return [self._row_to_session(row) for row in cursor.fetchall()]
    
    def archive_session(self, session_id: str, archived: bool = True) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET is_archived = ? WHERE id = ?",
            (archived, session_id)
        )
        conn.commit()
    
    def delete_session(self, session_id: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    
    # ==================== Message 操作 ====================
    
    def add_message(self, message: Message) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages 
            (session_id, role, content, token_count, timestamp, has_code, code_language)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            message.session_id, message.role, message.content,
            message.token_count, message.timestamp, message.has_code,
            message.code_language
        ))
        conn.commit()
        
        # 返回生成的ID
        message.id = cursor.lastrowid
    
    def get_messages(
        self, 
        session_id: str, 
        limit: int = 100,
        offset: int = 0
    ) -> List[Message]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM messages 
               WHERE session_id = ? 
               ORDER BY timestamp 
               LIMIT ? OFFSET ?""",
            (session_id, limit, offset)
        )
        return [self._row_to_message(row) for row in cursor.fetchall()]
    
    def get_recent_messages(self, session_id: str, n: int = 3) -> List[Message]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM messages 
               WHERE session_id = ? 
               ORDER BY timestamp DESC 
               LIMIT ?""",
            (session_id, n)
        )
        rows = cursor.fetchall()
        # 反转回时间正序
        return [self._row_to_message(row) for row in reversed(rows)]
    
    # ==================== 检索操作 ====================
    
    def search_by_keywords(
        self, 
        query: str, 
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """FTS5 全文搜索"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 构建FTS5查询 (使用BM25排序)
        # 转义特殊字符
        query_escaped = query.replace('"', '""')
        
        try:
            cursor.execute("""
                SELECT s.id, rank
                FROM sessions_fts fts
                JOIN sessions s ON s.rowid = fts.rowid
                WHERE sessions_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query_escaped, top_k))
            
            # rank 是 BM25 分数，越小越好，需要反转
            results = []
            for row in cursor.fetchall():
                # 将 BM25 分数转换为相似度分数 (0-1)
                # BM25 越小越好，所以取倒数并归一化
                bm25_score = row[1] if row[1] else 0
                similarity = 1.0 / (1.0 + abs(bm25_score))
                results.append((row[0], similarity))
            return results
        except sqlite3.Error:
            # FTS 查询失败，返回空列表
            return []
    
    def search_by_vector(
        self, 
        embedding: List[float], 
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """向量搜索 (需要 sqlite-vec)"""
        if not self._vec_available:
            return []
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # sqlite-vec 使用 cosine distance
            # 需要转换为二进制格式
            embedding_bytes = self._float_list_to_bytes(embedding)
            
            cursor.execute("""
                SELECT session_id, distance
                FROM session_vectors
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
            """, (embedding_bytes, top_k))
            
            results = []
            for row in cursor.fetchall():
                session_id = row[0]
                distance = row[1]  # cosine distance: 0 = 相同, 2 = 相反
                # 转换为相似度: 1 - distance/2
                similarity = 1.0 - (distance / 2.0)
                results.append((session_id, max(0.0, similarity)))
            return results
        except Exception:
            return []
    
    def update_embedding(self, session_id: str, embedding: List[float]) -> None:
        """更新会话的向量"""
        if not self._vec_available:
            return
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 先删除旧的
            cursor.execute(
                "DELETE FROM session_vectors WHERE session_id = ?",
                (session_id,)
            )
            
            # 插入新的
            embedding_bytes = self._float_list_to_bytes(embedding)
            cursor.execute(
                "INSERT INTO session_vectors (session_id, embedding) VALUES (?, ?)",
                (session_id, embedding_bytes)
            )
            conn.commit()
        except Exception:
            pass
    
    # ==================== 统计信息 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {
            "total_sessions": 0,
            "total_messages": 0,
            "total_tokens": 0,
            "archived_sessions": 0,
            "vec_available": self._vec_available,
        }
        
        try:
            cursor.execute("SELECT COUNT(*) FROM sessions")
            stats["total_sessions"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE is_archived = 1")
            stats["archived_sessions"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM messages")
            stats["total_messages"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COALESCE(SUM(token_count), 0) FROM sessions")
            stats["total_tokens"] = cursor.fetchone()[0]
            
            if self._vec_available:
                cursor.execute("SELECT COUNT(*) FROM session_vectors")
                stats["indexed_vectors"] = cursor.fetchone()[0]
        except Exception:
            pass
        
        return stats
    
    def vacuum(self) -> None:
        """清理数据库"""
        conn = self._get_connection()
        conn.execute("VACUUM")
        conn.commit()
    
    # ==================== 辅助方法 ====================
    
    def _row_to_session(self, row: sqlite3.Row) -> Session:
        """将行转换为 Session 对象"""
        keywords = []
        if row["keywords"]:
            try:
                keywords = json.loads(row["keywords"])
            except json.JSONDecodeError:
                pass
        
        from kimi_cli.memory.models.data import SyncStatus
        return Session(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            keywords=keywords,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            token_count=row["token_count"],
            work_dir=row["work_dir"],
            is_archived=bool(row["is_archived"]),
            sync_status=SyncStatus(row["sync_status"]),
            sync_version=row["sync_version"],
        )
    
    def _row_to_message(self, row: sqlite3.Row) -> Message:
        """将行转换为 Message 对象"""
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            token_count=row["token_count"],
            timestamp=row["timestamp"],
            has_code=bool(row["has_code"]),
            code_language=row["code_language"],
        )
    
    def _float_list_to_bytes(self, floats: List[float]) -> bytes:
        """将 float 列表转换为 bytes (用于 sqlite-vec)"""
        # sqlite-vec 期望的是 float32 数组
        return struct.pack(f'{len(floats)}f', *floats)
