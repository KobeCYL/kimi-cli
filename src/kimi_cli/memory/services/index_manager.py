"""索引管理器 - 负责会话的索引和向量化"""

from __future__ import annotations

import re
from typing import List, Optional, Set
from datetime import datetime

from kimi_cli.memory.adapters.storage.base import StorageBackend
from kimi_cli.memory.adapters.embedding.base import EmbeddingProvider
from kimi_cli.memory.models.data import Session, Message


class IndexManager:
    """索引管理器
    
    职责:
    - 提取关键词
    - 生成会话摘要
    - 创建和更新向量索引
    - 批量索引处理
    """
    
    def __init__(
        self,
        storage: StorageBackend,
        embedding: Optional[EmbeddingProvider] = None,
    ):
        self.storage = storage
        self.embedding = embedding
    
    def index_session(self, session_id: str, force: bool = False) -> bool:
        """索引指定会话
        
        Args:
            session_id: 会话ID
            force: 是否强制重新索引
            
        Returns:
            是否成功
        """
        session = self.storage.get_session(session_id)
        if not session:
            return False
        
        # 获取会话的所有消息
        messages = self.storage.get_messages(session_id, limit=1000)
        if not messages:
            return False
        
        # 提取关键词
        keywords = self._extract_keywords(messages)
        session.keywords = keywords
        
        # 生成摘要
        summary = self._generate_summary(messages)
        session.summary = summary
        
        # 计算token数
        total_tokens = sum(m.token_count for m in messages)
        session.token_count = total_tokens
        
        # 更新会话元数据
        self.storage.update_session(session)
        
        # 生成并更新向量索引
        if self.embedding:
            embedding = self._generate_embedding(session, messages)
            if embedding:
                self.storage.update_embedding(session_id, embedding)
        
        return True
    
    def should_index(self, session_id: str) -> bool:
        """判断会话是否需要索引
        
        策略:
        - 从未索引过
        - 消息数达到阈值 (每5条)
        - 距离上次索引超过10分钟
        """
        session = self.storage.get_session(session_id)
        if not session:
            return False
        
        # 如果没有关键词，说明从未索引过
        if not session.keywords:
            return True
        
        # 获取消息数
        messages = self.storage.get_messages(session_id)
        message_count = len(messages)
        
        # 每5条消息触发一次
        if message_count % 5 == 0 and message_count > 0:
            return True
        
        # 距离上次更新超过10分钟
        now = datetime.now().timestamp()
        if now - session.updated_at > 600:  # 10分钟
            return True
        
        return False
    
    def _extract_keywords(self, messages: List[Message], max_keywords: int = 10) -> List[str]:
        """从消息中提取关键词
        
        简单实现：基于词频和TF-IDF启发式
        """
        # 合并所有用户消息
        user_text = " ".join([
            m.content for m in messages 
            if m.role == "user"
        ])
        
        if not user_text:
            return []
        
        # 简单的关键词提取
        # 1. 提取英文技术词汇
        tech_words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', user_text)
        
        # 2. 提取中文词汇 (2-4字)
        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', user_text)
        
        # 3. 统计频率
        from collections import Counter
        word_counts = Counter(tech_words + chinese_words)
        
        # 4. 过滤停用词
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can',
            'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for',
            'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'between',
            '你', '我', '他', '她', '它', '的', '了', '在', '是', '有',
            '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很',
            '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
            '自己', '这', '那', '怎么', '什么', '吗', '呢', '吧', '啊',
        }
        
        filtered_counts = {
            word: count for word, count in word_counts.items()
            if word.lower() not in stop_words and len(word) > 1
        }
        
        # 5. 取Top-K
        top_words = Counter(filtered_counts).most_common(max_keywords)
        return [word for word, _ in top_words]
    
    def _generate_summary(self, messages: List[Message], max_length: int = 200) -> str:
        """生成会话摘要
        
        简单实现：取前3条用户消息拼接
        """
        user_messages = [m for m in messages if m.role == "user"]
        
        if not user_messages:
            return "Empty session"
        
        # 取前3条
        preview_messages = user_messages[:3]
        
        summaries = []
        for msg in preview_messages:
            content = msg.content[:100]  # 每条取前100字符
            if len(msg.content) > 100:
                content += "..."
            summaries.append(content)
        
        summary = " | ".join(summaries)
        
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        
        return summary
    
    def _generate_embedding(
        self, 
        session: Session, 
        messages: List[Message]
    ) -> Optional[List[float]]:
        """生成会话的向量表示"""
        if not self.embedding:
            return None
        
        # 构建文本表示
        # 1. 标题和摘要
        text_parts = [session.title]
        if session.summary:
            text_parts.append(session.summary)
        
        # 2. 关键词
        if session.keywords:
            text_parts.extend(session.keywords)
        
        # 3. 用户消息摘要
        user_messages = [m.content[:100] for m in messages if m.role == "user"]
        text_parts.extend(user_messages[:5])  # 前5条
        
        # 合并并向量化
        combined_text = " ".join(text_parts)
        
        try:
            embedding = self.embedding.embed(combined_text)
            return embedding
        except Exception:
            return None
    
    def batch_index(self, limit: int = 100) -> int:
        """批量索引未索引的会话
        
        Returns:
            索引的会话数
        """
        sessions = self.storage.list_sessions(limit=limit)
        count = 0
        
        for session in sessions:
            if not session.keywords:  # 未索引
                if self.index_session(session.id):
                    count += 1
        
        return count
