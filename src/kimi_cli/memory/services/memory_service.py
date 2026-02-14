"""Memory Service - 对话记忆服务主入口"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict, Any
import json

from kimi_cli.memory.models.data import (
    MemoryConfig, 
    Session, 
    Message, 
    RecallResult,
    EmbeddingConfig,
    StorageConfig,
)
from kimi_cli.memory.adapters.storage.base import StorageBackend
from kimi_cli.memory.adapters.storage.sqlite import SQLiteStorage
from kimi_cli.memory.adapters.embedding.base import EmbeddingProvider
from kimi_cli.memory.adapters.embedding.onnx import ONNXEmbedding, MockEmbedding
from kimi_cli.memory.services.recall_engine import RecallEngine
from kimi_cli.memory.services.index_manager import IndexManager


class MemoryService:
    """对话记忆服务
    
    这是记忆系统的主入口，提供统一的操作接口。
    负责:
    - 配置管理
    - 组件初始化和生命周期
    - 会话管理
    - 消息存储
    - 记忆召回
    """
    
    _instance: Optional[MemoryService] = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        if self._initialized:
            return
        
        self.config = config or self._load_config()
        self._storage: Optional[StorageBackend] = None
        self._embedding: Optional[EmbeddingProvider] = None
        self._recall_engine: Optional[RecallEngine] = None
        self._index_manager: Optional[IndexManager] = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """初始化服务
        
        Returns:
            是否成功
        """
        if self._initialized:
            return True
        
        try:
            # 初始化存储
            self._storage = self._create_storage()
            self._storage.initialize()
            
            # 初始化 Embedding
            self._embedding = self._create_embedding()
            
            # 初始化召回引擎
            self._recall_engine = RecallEngine(
                storage=self._storage,
                embedding=self._embedding,
            )
            
            # 初始化索引管理器
            self._index_manager = IndexManager(
                storage=self._storage,
                embedding=self._embedding,
            )
            
            self._initialized = True
            return True
            
        except Exception as e:
            print(f"Memory service initialization failed: {e}")
            return False
    
    def _create_storage(self) -> StorageBackend:
        """创建存储后端"""
        backend = self.config.storage.backend
        
        if backend == "sqlite":
            return SQLiteStorage(self.config.storage.db_path)
        else:
            raise ValueError(f"Unsupported storage backend: {backend}")
    
    def _create_embedding(self) -> Optional[EmbeddingProvider]:
        """创建 Embedding 提供者"""
        provider = self.config.embedding.provider
        
        if provider == "local_onnx":
            try:
                return ONNXEmbedding(
                    model_path=None,  # 使用默认
                    device=self.config.embedding.device,
                    batch_size=self.config.embedding.batch_size,
                )
            except Exception as e:
                print(f"ONNX embedding failed, using mock: {e}")
                return MockEmbedding()
        elif provider == "mock":
            return MockEmbedding()
        else:
            # 其他提供者暂未实现
            print(f"Embedding provider '{provider}' not implemented, using mock")
            return MockEmbedding()
    
    def _load_config(self) -> MemoryConfig:
        """从文件加载配置"""
        config_path = Path.home() / ".kimi" / "memory" / "config.json"
        
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                return MemoryConfig.from_dict(data)
            except Exception:
                pass
        
        return MemoryConfig()  # 默认配置
    
    def save_config(self) -> None:
        """保存配置到文件"""
        config_path = Path.home() / ".kimi" / "memory" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
    
    # ==================== 会话管理 ====================
    
    def create_session(
        self, 
        session_id: str, 
        title: str,
        work_dir: Optional[str] = None
    ) -> Session:
        """创建新会话"""
        session = Session(
            id=session_id,
            title=title,
            work_dir=work_dir,
        )
        self._storage.create_session(session)
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        return self._storage.get_session(session_id)
    
    def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str,
        token_count: int = 0,
    ) -> Message:
        """添加消息到会话"""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            token_count=token_count,
        )
        self._storage.add_message(message)
        
        # 检查是否需要自动索引
        if self._index_manager.should_index(session_id):
            # 异步索引（不阻塞）
            import threading
            threading.Thread(
                target=self._index_manager.index_session,
                args=(session_id,),
                daemon=True
            ).start()
        
        return message
    
    # ==================== 记忆召回 ====================
    
    def recall(
        self,
        context_text: str,
        current_session_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[RecallResult]:
        """召回相关记忆"""
        return self._recall_engine.recall_for_session(
            session_id=current_session_id or "",
            context_text=context_text,
            top_k=top_k,
        )
    
    def get_recall_context(
        self,
        context_text: str,
        current_session_id: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> str:
        """获取用于 prompt 的召回上下文"""
        results = self.recall(
            context_text=context_text,
            current_session_id=current_session_id,
            top_k=5,
        )
        
        if not results:
            return ""
        
        return self._recall_engine.build_prompt_context(results, max_tokens)
    
    # ==================== 索引管理 ====================
    
    def index_session(self, session_id: str, force: bool = False) -> bool:
        """手动索引会话"""
        return self._index_manager.index_session(session_id, force)
    
    def batch_index(self, limit: int = 100) -> int:
        """批量索引"""
        return self._index_manager.batch_index(limit)
    
    # ==================== 统计信息 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._storage.get_stats()
    
    # ==================== 生命周期 ====================
    
    def close(self) -> None:
        """关闭服务"""
        if self._storage:
            self._storage.close()
        self._initialized = False
        MemoryService._instance = None
    
    def __enter__(self):
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    # ==================== 属性访问 ====================
    
    @property
    def storage(self) -> StorageBackend:
        """存储后端"""
        if self._storage is None:
            raise RuntimeError("Memory service not initialized")
        return self._storage
    
    @property
    def embedding(self) -> Optional[EmbeddingProvider]:
        """Embedding 提供者"""
        return self._embedding
    
    @property
    def is_ready(self) -> bool:
        """服务是否就绪"""
        return self._initialized
