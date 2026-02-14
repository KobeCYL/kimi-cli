"""存储后端抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from kimi_cli.memory.models.data import Session, Message, RecallResult, SearchQuery


class StorageBackend(ABC):
    """存储后端抽象基类
    
    实现类需要支持:
    - 会话和消息的 CRUD
    - 全文检索 (FTS)
    - 向量检索 (需要配合 EmbeddingProvider)
    - 混合检索
    """
    
    @abstractmethod
    def initialize(self) -> None:
        """初始化存储 (创建表、索引等)"""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """关闭存储连接"""
        pass
    
    # ==================== Session 操作 ====================
    
    @abstractmethod
    def create_session(self, session: Session) -> None:
        """创建会话"""
        pass
    
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        pass
    
    @abstractmethod
    def update_session(self, session: Session) -> None:
        """更新会话"""
        pass
    
    @abstractmethod
    def list_sessions(
        self, 
        limit: int = 100, 
        offset: int = 0,
        archived: Optional[bool] = None
    ) -> List[Session]:
        """列会话列表"""
        pass
    
    @abstractmethod
    def archive_session(self, session_id: str, archived: bool = True) -> None:
        """归档/取消归档会话"""
        pass
    
    @abstractmethod
    def delete_session(self, session_id: str) -> None:
        """删除会话"""
        pass
    
    # ==================== Message 操作 ====================
    
    @abstractmethod
    def add_message(self, message: Message) -> None:
        """添加消息"""
        pass
    
    @abstractmethod
    def get_messages(
        self, 
        session_id: str, 
        limit: int = 100,
        offset: int = 0
    ) -> List[Message]:
        """获取会话的消息列表"""
        pass
    
    @abstractmethod
    def get_recent_messages(self, session_id: str, n: int = 3) -> List[Message]:
        """获取最近n条消息"""
        pass
    
    # ==================== 检索操作 ====================
    
    @abstractmethod
    def search_by_keywords(
        self, 
        query: str, 
        top_k: int = 10
    ) -> List[tuple[str, float]]:
        """关键词搜索，返回 [(session_id, score), ...]"""
        pass
    
    @abstractmethod
    def search_by_vector(
        self, 
        embedding: List[float], 
        top_k: int = 10
    ) -> List[tuple[str, float]]:
        """向量搜索，返回 [(session_id, score), ...]"""
        pass
    
    @abstractmethod
    def update_embedding(self, session_id: str, embedding: List[float]) -> None:
        """更新会话的向量表示"""
        pass
    
    def search_hybrid(self, query: SearchQuery) -> List[RecallResult]:
        """混合搜索 (默认实现，子类可覆盖)"""
        # 子类可以实现更高效的混合搜索
        # 默认实现：分别搜索后合并
        results: Dict[str, RecallResult] = {}
        
        # 关键词搜索
        if query.text:
            keyword_results = self.search_by_keywords(query.text, query.top_k * 2)
            for session_id, score in keyword_results:
                if session_id == query.session_id_to_exclude:
                    continue
                if session_id not in results:
                    session = self.get_session(session_id)
                    if session:
                        results[session_id] = RecallResult(
                            session=session,
                            keyword_score=score,
                            context_messages=self.get_recent_messages(session_id, 3)
                        )
                else:
                    results[session_id].keyword_score = max(
                        results[session_id].keyword_score, score
                    )
        
        # 向量搜索
        if query.embedding:
            vector_results = self.search_by_vector(query.embedding, query.top_k * 2)
            for session_id, score in vector_results:
                if session_id == query.session_id_to_exclude:
                    continue
                if session_id not in results:
                    session = self.get_session(session_id)
                    if session:
                        results[session_id] = RecallResult(
                            session=session,
                            vector_score=score,
                            context_messages=self.get_recent_messages(session_id, 3)
                        )
                else:
                    results[session_id].vector_score = max(
                        results[session_id].vector_score, score
                    )
        
        # 计算综合分数 (使用动态权重)
        final_results = list(results.values())
        for result in final_results:
            # 归一化分数 (确保最大值接近1.0)
            vector_score = min(result.vector_score, 1.0)
            keyword_score = min(result.keyword_score, 1.0)
            
            # 加权平均 (使用查询指定的权重)
            result.combined_score = (
                vector_score * query.vector_weight + 
                keyword_score * query.keyword_weight
            )
        
        # 排序并截断
        final_results.sort(key=lambda x: x.combined_score, reverse=True)
        return final_results[:query.top_k]
    
    # ==================== 统计信息 ====================
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        pass
    
    @abstractmethod
    def vacuum(self) -> None:
        """清理/优化存储"""
        pass
