"""Embedding 提供者测试"""

import pytest

from kimi_cli.memory.adapters.embedding.onnx import MockEmbedding


class TestMockEmbedding:
    """MockEmbedding 测试"""
    
    @pytest.fixture
    def embedder(self):
        return MockEmbedding()
    
    def test_dimensions(self, embedder):
        """测试维度"""
        assert embedder.dimensions == 384
    
    def test_embed_single(self, embedder):
        """测试单文本编码"""
        text = "Hello world"
        embedding = embedder.embed(text)
        
        assert len(embedding) == 384
        
        # 检查归一化 (L2 norm ≈ 1)
        import math
        norm = math.sqrt(sum(x*x for x in embedding))
        assert 0.99 < norm < 1.01
    
    def test_embed_batch(self, embedder):
        """测试批量编码"""
        texts = ["Hello", "World", "Test"]
        embeddings = embedder.embed_batch(texts)
        
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 384
    
    def test_deterministic(self, embedder):
        """测试确定性 (相同文本产生相同向量)"""
        text = "Test text"
        emb1 = embedder.embed(text)
        emb2 = embedder.embed(text)
        
        assert emb1 == emb2
    
    def test_different_texts(self, embedder):
        """测试不同文本产生不同向量"""
        emb1 = embedder.embed("Hello")
        emb2 = embedder.embed("World")
        
        assert emb1 != emb2
    
    def test_is_available(self, embedder):
        """测试可用性检查"""
        assert embedder.is_available()
    
    def test_model_info(self, embedder):
        """测试模型信息"""
        info = embedder.get_model_info()
        assert "provider" in info
        assert "dimensions" in info
