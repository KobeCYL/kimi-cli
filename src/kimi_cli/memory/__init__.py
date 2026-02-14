"""Kimi CLI Memory System - 对话记忆召回系统

一个轻量级、可插拔、可扩展的对话记忆系统，支持：
- 向量相似度检索
- 关键词全文检索
- 混合排序召回
- 多后端存储 (SQLite/ES)
- 多源Embedding (Local/Remote)
"""

from __future__ import annotations

__version__ = "1.0.0"

from kimi_cli.memory.models.data import Session, Message, RecallResult, SearchQuery
from kimi_cli.memory.services.memory_service import MemoryService

__all__ = [
    "Session",
    "Message", 
    "RecallResult",
    "SearchQuery",
    "MemoryService",
]
