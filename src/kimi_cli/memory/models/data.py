"""数据模型定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class SyncStatus(str, Enum):
    """同步状态"""
    LOCAL = "local"
    SYNCING = "syncing"
    SYNCED = "synced"
    ERROR = "error"


@dataclass
class Message:
    """消息记录"""
    id: Optional[int] = None
    session_id: Optional[str] = None
    role: str = ""  # 'user' | 'assistant' | 'system'
    content: str = ""
    token_count: int = 0
    timestamp: int = 0
    has_code: bool = False
    code_language: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = int(datetime.now().timestamp())


@dataclass
class Session:
    """会话记录"""
    id: str = ""
    title: str = ""
    summary: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0
    token_count: int = 0
    work_dir: Optional[str] = None
    is_archived: bool = False
    sync_status: SyncStatus = SyncStatus.LOCAL
    sync_version: int = 1
    
    def __post_init__(self):
        now = int(datetime.now().timestamp())
        if self.created_at == 0:
            self.created_at = now
        if self.updated_at == 0:
            self.updated_at = now


@dataclass
class RecallResult:
    """召回结果"""
    session: Session
    vector_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0
    context_messages: List[Message] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class SearchQuery:
    """搜索查询"""
    text: Optional[str] = None
    embedding: Optional[List[float]] = None
    session_id_to_exclude: Optional[str] = None
    top_k: int = 5
    min_score: float = 0.75
    time_decay_factor: float = 0.001
    # 混合检索权重
    vector_weight: float = 0.6
    keyword_weight: float = 0.4


@dataclass
class EmbeddingConfig:
    """Embedding配置"""
    provider: str = "local_onnx"  # local_onnx | openai | custom
    dimensions: int = 384
    model_name: str = "all-MiniLM-L6-v2"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    device: str = "cpu"
    batch_size: int = 32


@dataclass
class StorageConfig:
    """存储配置"""
    backend: str = "sqlite"  # sqlite | elasticsearch | chromadb
    db_path: str = "~/.kimi/memory/memory.db"
    max_size_mb: int = 2048
    # ES配置
    es_hosts: Optional[List[str]] = None
    es_index: str = "kimi_sessions"


@dataclass
class SyncConfig:
    """同步配置"""
    mode: str = "disabled"  # disabled | local | remote | saas
    auto_sync_interval: int = 300
    remote_endpoint: Optional[str] = None
    remote_token: Optional[str] = None


@dataclass
class RecallConfig:
    """召回配置"""
    auto_recall_enabled: bool = True
    vector_weight: float = 0.6
    keyword_weight: float = 0.4
    min_similarity: float = 0.75
    max_results: int = 5
    exclude_current_session: bool = True
    time_decay_factor: float = 0.001
    max_messages_per_session: int = 3


@dataclass
class MemoryConfig:
    """完整配置"""
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    recall: RecallConfig = field(default_factory=RecallConfig)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MemoryConfig:
        """从字典创建配置"""
        return cls(
            embedding=EmbeddingConfig(**data.get("embedding", {})),
            storage=StorageConfig(**data.get("storage", {})),
            sync=SyncConfig(**data.get("sync", {})),
            recall=RecallConfig(**data.get("recall", {})),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "embedding": self.embedding.__dict__,
            "storage": self.storage.__dict__,
            "sync": self.sync.__dict__,
            "recall": self.recall.__dict__,
        }
