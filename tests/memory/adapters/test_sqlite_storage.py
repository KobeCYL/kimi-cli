"""SQLite 存储后端测试"""

import pytest
from datetime import datetime

from kimi_cli.memory.adapters.storage.sqlite import SQLiteStorage
from kimi_cli.memory.models.data import Session, Message


class TestSQLiteStorage:
    """SQLiteStorage 测试类"""
    
    @pytest.fixture
    def storage(self, temp_db_path):
        """Storage fixture"""
        storage = SQLiteStorage(str(temp_db_path))
        storage.initialize()
        yield storage
        storage.close()
    
    def test_initialization(self, storage):
        """测试初始化"""
        stats = storage.get_stats()
        assert stats["total_sessions"] == 0
        assert stats["total_messages"] == 0
    
    def test_create_and_get_session(self, storage):
        """测试创建和获取会话"""
        session = Session(
            id="test-001",
            title="Test Session",
            work_dir="/tmp/test"
        )
        
        storage.create_session(session)
        retrieved = storage.get_session("test-001")
        
        assert retrieved is not None
        assert retrieved.id == "test-001"
        assert retrieved.title == "Test Session"
    
    def test_get_nonexistent_session(self, storage):
        """测试获取不存在的会话"""
        result = storage.get_session("nonexistent")
        assert result is None
    
    def test_update_session(self, storage):
        """测试更新会话"""
        session = Session(id="test-002", title="Original")
        storage.create_session(session)
        
        session.title = "Updated"
        session.token_count = 100
        storage.update_session(session)
        
        retrieved = storage.get_session("test-002")
        assert retrieved.title == "Updated"
        assert retrieved.token_count == 100
    
    def test_list_sessions(self, storage):
        """测试列会话"""
        # 创建多个会话
        for i in range(5):
            session = Session(id=f"test-{i}", title=f"Session {i}")
            storage.create_session(session)
        
        sessions = storage.list_sessions(limit=10)
        assert len(sessions) == 5
    
    def test_archive_session(self, storage):
        """测试归档会话"""
        session = Session(id="test-003", title="To Archive")
        storage.create_session(session)
        
        storage.archive_session("test-003", True)
        retrieved = storage.get_session("test-003")
        assert retrieved.is_archived
    
    def test_delete_session(self, storage):
        """测试删除会话"""
        session = Session(id="test-004", title="To Delete")
        storage.create_session(session)
        
        storage.delete_session("test-004")
        retrieved = storage.get_session("test-004")
        assert retrieved is None
    
    def test_add_and_get_messages(self, storage):
        """测试添加和获取消息"""
        # 先创建会话
        session = Session(id="msg-test", title="Message Test")
        storage.create_session(session)
        
        # 添加消息
        msg1 = Message(
            session_id="msg-test",
            role="user",
            content="Hello",
            timestamp=1700000000
        )
        msg2 = Message(
            session_id="msg-test",
            role="assistant",
            content="Hi there!",
            timestamp=1700000010
        )
        
        storage.add_message(msg1)
        storage.add_message(msg2)
        
        # 获取消息
        messages = storage.get_messages("msg-test")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
    
    def test_get_recent_messages(self, storage):
        """测试获取最近消息"""
        session = Session(id="recent-test", title="Recent Test")
        storage.create_session(session)
        
        # 添加多条消息
        for i in range(10):
            msg = Message(
                session_id="recent-test",
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                timestamp=1700000000 + i * 10
            )
            storage.add_message(msg)
        
        recent = storage.get_recent_messages("recent-test", n=3)
        assert len(recent) == 3
        # 应该是最后3条
        assert recent[-1].content == "Message 9"
    
    def test_search_by_keywords(self, storage):
        """测试关键词搜索"""
        # 创建带关键词的会话
        session = Session(
            id="search-test",
            title="Python Programming",
            summary="Learn Python basics",
            keywords=["python", "programming", "tutorial"]
        )
        storage.create_session(session)
        
        # 等待FTS索引更新
        import time
        time.sleep(0.1)
        
        # 搜索
        results = storage.search_by_keywords("python", top_k=5)
        assert len(results) > 0
        assert results[0][0] == "search-test"  # session_id
    
    def test_stats(self, storage):
        """测试统计信息"""
        # 创建会话和消息
        session = Session(id="stats-test", title="Stats")
        storage.create_session(session)
        
        msg = Message(session_id="stats-test", role="user", content="test")
        storage.add_message(msg)
        
        stats = storage.get_stats()
        assert stats["total_sessions"] == 1
        assert stats["total_messages"] == 1
