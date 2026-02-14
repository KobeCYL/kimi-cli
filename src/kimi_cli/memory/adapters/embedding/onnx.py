"""ONNX Runtime Embedding 实现

使用本地 ONNX 模型进行文本向量化，无需网络，隐私友好
默认使用 all-MiniLM-L6-v2 (80MB, 384维)
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import List, Optional
import hashlib

from kimi_cli.memory.adapters.embedding.base import EmbeddingProvider


class ONNXEmbedding(EmbeddingProvider):
    """ONNX Embedding 提供者
    
    特性:
    - 本地运行，无需网络
    - 支持 CPU/GPU
    - 自动下载模型
    - 批处理优化
    """
    
    # 默认模型配置
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    DEFAULT_DIM = 384
    MODEL_URL = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx"
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cpu",
        batch_size: int = 32,
        cache_dir: Optional[str] = None,
    ):
        """
        Args:
            model_path: ONNX 模型路径，None 则自动下载
            device: cpu | cuda | mps
            batch_size: 批处理大小
            cache_dir: 模型缓存目录
        """
        self.model_name = self.DEFAULT_MODEL
        self.dimensions = self.DEFAULT_DIM
        self.device = device
        self.batch_size = batch_size
        
        # 设置缓存目录
        if cache_dir is None:
            cache_dir = Path.home() / ".kimi" / "models"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 模型路径
        if model_path is None:
            self.model_path = self.cache_dir / f"{self.model_name}.onnx"
        else:
            self.model_path = Path(model_path)
        
        # 运行时和tokenizer (延迟加载)
        self._session = None
        self._tokenizer = None
        self._available = None
    
    def is_available(self) -> bool:
        """检查是否可用"""
        if self._available is not None:
            return self._available
        
        try:
            import onnxruntime as ort
            self._available = True
            return True
        except ImportError:
            self._available = False
            return False
    
    def _ensure_model(self) -> bool:
        """确保模型文件存在"""
        if self.model_path.exists():
            return True
        
        # 模型不存在，尝试下载
        return self._download_model()
    
    def _download_model(self) -> bool:
        """下载预训练模型"""
        try:
            import urllib.request
            import urllib.error
            
            print(f"Downloading embedding model {self.model_name}...")
            print(f"URL: {self.MODEL_URL}")
            print(f"Destination: {self.model_path}")
            
            # 下载
            urllib.request.urlretrieve(self.MODEL_URL, self.model_path)
            
            print(f"Model downloaded successfully!")
            return True
            
        except Exception as e:
            warnings.warn(f"Failed to download model: {e}")
            return False
    
    def _load_model(self):
        """加载 ONNX 模型和 Tokenizer"""
        if self._session is not None:
            return
        
        if not self.is_available():
            raise RuntimeError("onnxruntime not installed. Run: pip install onnxruntime")
        
        if not self._ensure_model():
            raise RuntimeError(f"Model not found and download failed: {self.model_path}")
        
        import onnxruntime as ort
        
        # 配置推理会话
        providers = ["CPUExecutionProvider"]
        if self.device == "cuda":
            providers = ["CUDAExecutionProvider"] + providers
        
        self._session = ort.InferenceSession(
            str(self.model_path),
            providers=providers
        )
        
        # 加载 tokenizer
        # 对于 MiniLM，我们使用简单的空格分词 + 词汇表
        # 实际项目中可以使用 transformers 的 tokenizer
        self._tokenizer = self._simple_tokenizer
    
    def _simple_tokenizer(self, text: str) -> dict:
        """简化版 tokenizer (实际应使用 transformers)"""
        # 这里使用简单的字符编码作为 fallback
        # 生产环境应该使用 transformers.AutoTokenizer
        tokens = text.lower().split()[:256]  # 截断到256个词
        input_ids = [hash(token) % 10000 for token in tokens]
        
        # Padding
        max_len = 256
        attention_mask = [1] * len(input_ids) + [0] * (max_len - len(input_ids))
        input_ids = input_ids + [0] * (max_len - len(input_ids))
        
        return {
            "input_ids": input_ids[:max_len],
            "attention_mask": attention_mask[:max_len],
        }
    
    def embed(self, text: str) -> List[float]:
        """编码单个文本"""
        results = self.embed_batch([text])
        return results[0] if results else [0.0] * self.dimensions
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量编码文本"""
        self._load_model()
        
        if not self._session:
            # Fallback: 返回零向量
            return [[0.0] * self.dimensions for _ in texts]
        
        results = []
        
        # 分批处理
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_results = self._embed_batch_impl(batch)
            results.extend(batch_results)
        
        return results
    
    def _embed_batch_impl(self, texts: List[str]) -> List[List[float]]:
        """实际批量编码实现"""
        # Tokenize
        tokenized = [self._tokenizer(t) for t in texts]
        
        # 构建输入
        import numpy as np
        input_ids = np.array([t["input_ids"] for t in tokenized], dtype=np.int64)
        attention_mask = np.array([t["attention_mask"] for t in tokenized], dtype=np.int64)
        
        # 推理
        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
        )
        
        # 获取 embedding (通常是第一个输出)
        embeddings = outputs[0]
        
        # Mean pooling (如果输出是序列)
        if len(embeddings.shape) == 3:
            # [batch, seq_len, hidden_dim] -> [batch, hidden_dim]
            mask_expanded = np.expand_dims(attention_mask, -1).astype(np.float32)
            sum_embeddings = np.sum(embeddings * mask_expanded, axis=1)
            embeddings = sum_embeddings / np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        
        # L2 归一化
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.clip(norms, a_min=1e-12, a_max=None)
        
        return embeddings.tolist()
    
    def get_model_info(self) -> dict:
        """获取模型信息"""
        info = super().get_model_info()
        info.update({
            "model_name": self.model_name,
            "device": self.device,
            "model_path": str(self.model_path),
            "available": self.is_available(),
        })
        return info


class MockEmbedding(EmbeddingProvider):
    """Mock Embedding 用于测试和 fallback"""
    
    dimensions = 384
    
    def embed(self, text: str) -> List[float]:
        """使用哈希生成确定性向量"""
        # 使用文本哈希生成伪向量
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        import random
        rng = random.Random(hash_val)
        vec = [rng.uniform(-1, 1) for _ in range(self.dimensions)]
        
        # L2 归一化
        import math
        norm = math.sqrt(sum(x*x for x in vec))
        if norm > 0:
            vec = [x/norm for x in vec]
        return vec
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]
    
    def is_available(self) -> bool:
        return True
