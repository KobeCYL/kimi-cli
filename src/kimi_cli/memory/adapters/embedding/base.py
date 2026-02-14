"""Embedding 提供者抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """Embedding 服务抽象基类
    
    实现类需要提供文本向量化能力
    """
    
    dimensions: int = 384  # 默认维度，子类应覆盖
    
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """将文本编码为向量
        
        Args:
            text: 输入文本
            
        Returns:
            向量表示 (长度为 self.dimensions)
        """
        pass
    
    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量编码文本
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        pass
    
    def is_available(self) -> bool:
        """检查服务是否可用 (默认True，子类可覆盖)"""
        return True
    
    def get_model_info(self) -> dict:
        """获取模型信息"""
        return {
            "provider": self.__class__.__name__,
            "dimensions": self.dimensions,
        }
