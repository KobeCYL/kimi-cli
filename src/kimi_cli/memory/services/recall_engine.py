"""召回引擎 - 负责智能召回相关对话"""

from __future__ import annotations

import math
from typing import List, Optional
from datetime import datetime

from kimi_cli.memory.adapters.storage.base import StorageBackend
from kimi_cli.memory.adapters.embedding.base import EmbeddingProvider
from kimi_cli.memory.models.data import RecallResult, SearchQuery


class RecallEngine:
    """召回引擎
    
    职责:
    - 构建搜索查询
    - 执行混合检索 (向量 + 关键词)
    - 结果排序和过滤
    - 上下文组装
    """
    
    def __init__(
        self,
        storage: StorageBackend,
        embedding: Optional[EmbeddingProvider] = None,
    ):
        self.storage = storage
        self.embedding = embedding
    
    def recall(
        self,
        query_text: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        current_session_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.75,
    ) -> List[RecallResult]:
        """执行召回
        
        Args:
            query_text: 关键词查询文本
            query_embedding: 向量查询
            current_session_id: 当前会话ID (排除)
            top_k: 返回结果数
            min_score: 最低相似度阈值
            
        Returns:
            召回结果列表
        """
        # 如果没有提供embedding但有text和embedding服务，自动生成
        if query_embedding is None and query_text and self.embedding:
            query_embedding = self.embedding.embed(query_text)
        
        # 构建搜索查询
        search_query = SearchQuery(
            text=query_text,
            embedding=query_embedding,
            session_id_to_exclude=current_session_id,
            top_k=top_k * 2,  # 多取一些用于过滤
            min_score=min_score,
        )
        
        # 执行混合搜索
        results = self.storage.search_hybrid(search_query)
        
        # 应用时间衰减
        results = self._apply_time_decay(results)
        
        # 过滤低分结果
        results = [r for r in results if r.combined_score >= min_score]
        
        # 重新排序
        results.sort(key=lambda x: x.combined_score, reverse=True)
        
        return results[:top_k]
    
    def recall_for_session(
        self,
        session_id: str,
        context_text: str,
        top_k: int = 5,
    ) -> List[RecallResult]:
        """为指定会话召回相关历史
        
        这是主要的使用入口，基于当前会话上下文召回相关历史
        """
        # 生成embedding
        embedding = None
        if self.embedding:
            embedding = self.embedding.embed(context_text)
        
        return self.recall(
            query_text=context_text[:200],  # 取前200字符做关键词搜索
            query_embedding=embedding,
            current_session_id=session_id,
            top_k=top_k,
        )
    
    def _apply_time_decay(self, results: List[RecallResult]) -> List[RecallResult]:
        """应用时间衰减因子"""
        now = datetime.now().timestamp()
        
        for result in results:
            days_old = (now - result.session.updated_at) / 86400
            # 指数衰减
            time_factor = math.exp(-0.001 * days_old)
            
            # 调整综合分数
            result.combined_score *= time_factor
            
        return results
    
    def build_prompt_context(
        self,
        results: List[RecallResult],
        max_tokens: int = 2000,
    ) -> str:
        """构建用于 prompt 的上下文文本
        
        Returns:
            格式化的上下文字符串
        """
        if not results:
            return ""
        
        lines = [
            "📚 [系统提示] 发现以下相关历史对话，可能对您有帮助：",
            "",
        ]
        
        current_tokens = 0
        
        for i, result in enumerate(results, 1):
            # 格式化日期
            from datetime import datetime
            dt = datetime.fromtimestamp(result.session.updated_at)
            date_str = dt.strftime("%Y-%m-%d")
            
            # 构建摘要
            section_lines = [
                f"--- 相关对话 #{i} ({result.session.title}) [{date_str}] ---",
                f"相似度: {result.combined_score:.2%}",
                "",
            ]
            
            # 添加上下文消息
            for msg in result.context_messages:
                role_display = "用户" if msg.role == "user" else "AI"
                content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                section_lines.append(f"{role_display}: {content}")
            
            section_lines.append("")
            
            # 估算token数 (粗略估计：1 token ≈ 4 字符)
            section_text = "\n".join(section_lines)
            section_tokens = len(section_text) // 4
            
            if current_tokens + section_tokens > max_tokens:
                lines.append("... (更多相关对话已省略) ...")
                break
            
            lines.extend(section_lines)
            current_tokens += section_tokens
        
        lines.append("--- 历史对话结束 ---")
        lines.append("")
        
        return "\n".join(lines)
