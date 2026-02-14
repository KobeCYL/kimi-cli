"""MemoryService 测试"""

import pytest

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import Session, Message


class TestMemoryService:
    """MemoryService 测试类"""
    
    def test_initialization(self, memory_service):
        """测试初始化"""
        assert memory_service.is_ready
        assert memory_service.storage is not None
    
    def test_create_session(self, memory_service):
        """测试创建会话"""
        session = memory_service.create_session(
            session_id="svc-test-001",
            title="Service Test",
            work_dir="/tmp"
        )
        
        assert session.id == "svc-test-001"
        assert session.title == "Service Test"
        
        # 验证可以获取
        retrieved = memory_service.get_session("svc-test-001")
        assert retrieved is not None
        assert retrieved.title == "Service Test"
    
    def test_add_message(self, memory_service):
        """测试添加消息"""
        # 先创建会话
        memory_service.create_session("msg-test", "Message Test")
        
        # 添加消息
        msg = memory_service.add_message(
            session_id="msg-test",
            role="user",
            content="Hello",
            token_count=10
        )
        
        assert msg.session_id == "msg-test"
        assert msg.role == "user"
        assert msg.content == "Hello"
    
    def test_get_stats(self, memory_service):
        """测试获取统计"""
        # 创建一些数据
        memory_service.create_session("stats-1", "Stats 1")
        memory_service.create_session("stats-2", "Stats 2")
        
        memory_service.add_message("stats-1", "user", "Hello", 10)
        memory_service.add_message("stats-1", "assistant", "Hi", 5)
        
        stats = memory_service.get_stats()
        
        assert stats["total_sessions"] == 2
        assert stats["total_messages"] == 2
    
    def test_singleton(self, temp_db_path):
        """测试单例模式"""
        from kimi_cli.memory.models.data import MemoryConfig, StorageConfig
        
        config = MemoryConfig(
            storage=StorageConfig(db_path=str(temp_db_path))
        )
        
        service1 = MemoryService(config)
        service2 = MemoryService(config)
        
        # 应该是同一个实例
        assert service1 is service2
        
        service1.close()


class TestIndexManager:
    """索引管理器测试"""
    
    def test_index_session(self, memory_service):
        """测试索引会话"""
        # 创建带消息的会话
        memory_service.create_session("idx-test", "Index Test")
        memory_service.add_message("idx-test", "user", "Hello world", 10)
        memory_service.add_message("idx-test", "assistant", "Hi there", 8)
        
        # 索引
        result = memory_service.index_session("idx-test")
        assert result is True
        
        # 验证会话已更新
        session = memory_service.get_session("idx-test")
        assert session.token_count > 0
    
    def test_should_index(self, memory_service):
        """测试是否应该索引"""
        memory_service.create_session("should-idx", "Should Index")
        
        # 没有消息时不应该索引
        should = memory_service._index_manager.should_index("should-idx")
        assert not should
        
        # 添加多条消息
        for i in range(6):
            memory_service.add_message("should-idx", "user", f"Message {i}", 10)
        
        # 现在有消息了，应该索引
        should = memory_service._index_manager.should_index("should-idx")
        assert should


class TestRecallEngine:
    """召回引擎测试"""
    
    def test_recall_with_mock_embedding(self, memory_service):
        """测试使用 MockEmbedding 的召回"""
        # 创建测试会话
        memory_service.create_session("recall-1", "Python Programming Guide")
        memory_service.add_message("recall-1", "user", "How to learn Python?", 20)
        memory_service.add_message("recall-1", "assistant", "Start with basics", 15)
        
        # 索引
        memory_service.index_session("recall-1")
        
        # 召回
        results = memory_service.recall(
            context_text="Python programming",
            current_session_id=None,
            top_k=3
        )
        
        # MockEmbedding 会产生确定性结果
        assert isinstance(results, list)
    
    def test_recall_excludes_current(self, memory_service):
        """测试召回排除当前会话"""
        # 创建两个会话
        memory_service.create_session("current", "Current Session")
        memory_service.create_session("other", "Other Session")
        
        memory_service.add_message("current", "user", "Current message", 10)
        memory_service.add_message("other", "user", "Other message", 10)
        
        memory_service.index_session("current")
        memory_service.index_session("other")
        
        # 召回时排除 current
        results = memory_service.recall(
            context_text="message",
            current_session_id="current",
            top_k=5
        )
        
        # 结果中不应该包含 current
        result_ids = [r.session.id for r in results]
        assert "current" not in result_ids
