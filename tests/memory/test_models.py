"""数据模型测试"""

import pytest
from datetime import datetime

from kimi_cli.memory.models.data import (
    Session, Message, RecallResult, SearchQuery,
    MemoryConfig, EmbeddingConfig, StorageConfig
)


class TestSession:
    """Session 模型测试"""
    
    def test_session_creation(self):
        """测试会话创建"""
        session = Session(
            id="test-123",
            title="Test Session",
            work_dir="/tmp/test"
        )
        
        assert session.id == "test-123"
        assert session.title == "Test Session"
        assert session.work_dir == "/tmp/test"
        assert session.created_at > 0
        assert session.updated_at > 0
        assert session.token_count == 0
        assert not session.is_archived
    
    def test_session_keywords_default(self):
        """测试关键词默认值"""
        session = Session(id="test", title="Test")
        assert session.keywords == []
    
    def test_session_timestamps(self):
        """测试时间戳自动设置"""
        before = int(datetime.now().timestamp())
        session = Session(id="test", title="Test")
        after = int(datetime.now().timestamp())
        
        assert before <= session.created_at <= after


class TestMessage:
    """Message 模型测试"""
    
    def test_message_creation(self):
        """测试消息创建"""
        msg = Message(
            session_id="session-1",
            role="user",
            content="Hello",
            token_count=10
        )
        
        assert msg.session_id == "session-1"
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.token_count == 10
        assert msg.timestamp > 0
    
    def test_message_roles(self):
        """测试不同角色"""
        roles = ["user", "assistant", "system"]
        for role in roles:
            msg = Message(session_id="s1", role=role, content="test")
            assert msg.role == role


class TestSearchQuery:
    """SearchQuery 模型测试"""
    
    def test_default_values(self):
        """测试默认值"""
        query = SearchQuery()
        
        assert query.text is None
        assert query.embedding is None
        assert query.session_id_to_exclude is None
        assert query.top_k == 5
        assert query.min_score == 0.75


class TestMemoryConfig:
    """MemoryConfig 测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = MemoryConfig()
        
        assert config.embedding.provider == "local_onnx"
        assert config.storage.backend == "sqlite"
        assert config.sync.mode == "disabled"
    
    def test_config_serialization(self):
        """测试配置序列化"""
        config = MemoryConfig()
        config.embedding.dimensions = 768
        
        data = config.to_dict()
        restored = MemoryConfig.from_dict(data)
        
        assert restored.embedding.dimensions == 768
