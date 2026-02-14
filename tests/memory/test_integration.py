"""集成测试"""

import pytest
import tempfile
from pathlib import Path

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import MemoryConfig, StorageConfig


class TestIntegration:
    """集成测试 - 端到端流程"""
    
    @pytest.fixture
    def integration_service(self):
        """集成测试用的 service"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MemoryConfig(
                storage=StorageConfig(
                    backend="sqlite",
                    db_path=str(Path(tmpdir) / "integration.db")
                )
            )
            service = MemoryService(config)
            service.initialize()
            yield service
            service.close()
            # 清理单例
            MemoryService._instance = None
    
    def test_full_workflow(self, integration_service):
        """测试完整工作流"""
        service = integration_service
        
        # 1. 创建多个会话
        sessions = [
            ("py-session", "Python Tutorial", "How to learn Python programming"),
            ("js-session", "JavaScript Guide", "JavaScript async/await tutorial"),
            ("db-session", "Database Design", "SQL optimization techniques"),
        ]
        
        for sid, title, first_msg in sessions:
            service.create_session(sid, title)
            service.add_message(sid, "user", first_msg, 20)
            service.add_message(sid, "assistant", f"Guide for {title}", 30)
        
        # 2. 批量索引
        count = service.batch_index()
        assert count >= 3
        
        # 3. 召回测试
        results = service.recall("Python programming", top_k=5)
        
        # 应该能找到 Python 相关会话
        assert len(results) > 0
        
        # 4. 检查统计
        stats = service.get_stats()
        assert stats["total_sessions"] == 3
        assert stats["total_messages"] == 6
    
    def test_persistence(self):
        """测试数据持久化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "persist.db"
            
            # 第一次：创建数据
            config = MemoryConfig(
                storage=StorageConfig(db_path=str(db_path))
            )
            service1 = MemoryService(config)
            service1.initialize()
            
            service1.create_session("persist-test", "Persistent Session")
            service1.add_message("persist-test", "user", "Test message", 10)
            
            service1.close()
            MemoryService._instance = None
            
            # 第二次：读取数据
            service2 = MemoryService(config)
            service2.initialize()
            
            session = service2.get_session("persist-test")
            assert session is not None
            assert session.title == "Persistent Session"
            
            messages = service2.storage.get_messages("persist-test")
            assert len(messages) == 1
            assert messages[0].content == "Test message"
            
            service2.close()
            MemoryService._instance = None
    
    def test_concurrent_sessions(self, integration_service):
        """测试多个会话同时存在"""
        service = integration_service
        
        # 创建10个会话
        for i in range(10):
            sid = f"concurrent-{i}"
            service.create_session(sid, f"Session {i}")
            
            # 每个会话多条消息
            for j in range(5):
                service.add_message(sid, "user" if j % 2 == 0 else "assistant", 
                                  f"Message {j}", 10)
        
        # 验证数量
        stats = service.get_stats()
        assert stats["total_sessions"] == 10
        assert stats["total_messages"] == 50
        
        # 验证可以分别获取
        for i in range(10):
            session = service.get_session(f"concurrent-{i}")
            assert session is not None
            assert session.title == f"Session {i}"
    
    def test_search_accuracy(self, integration_service):
        """测试搜索准确性"""
        service = integration_service
        
        # 创建特定内容的会话
        service.create_session("exact-match", "Python Programming Tips")
        service.add_message("exact-match", "user", "How to write clean Python code?", 20)
        
        service.create_session("partial-match", "Java Programming Tips")
        service.add_message("partial-match", "user", "Java best practices", 20)
        
        service.create_session("no-match", "Cooking Recipes")
        service.add_message("no-match", "user", "How to make pasta?", 20)
        
        # 索引
        service.index_session("exact-match")
        service.index_session("partial-match")
        service.index_session("no-match")
        
        # 搜索
        results = service.recall("Python clean code", top_k=5)
        
        # 应该能找到相关结果
        assert len(results) >= 1
        
        # 第一个结果应该相关性最高
        assert results[0].combined_score > 0


class TestEdgeCases:
    """边界情况测试"""
    
    def test_empty_database(self, integration_service):
        """测试空数据库"""
        results = integration_service.recall("test query", top_k=5)
        assert results == []
    
    def test_very_long_content(self, integration_service):
        """测试超长内容"""
        long_content = "A" * 10000
        
        integration_service.create_session("long-content", "Long Content")
        integration_service.add_message("long-content", "user", long_content, 2500)
        
        # 应该能正常处理
        messages = integration_service.storage.get_messages("long-content")
        assert len(messages[0].content) == 10000
    
    def test_special_characters(self, integration_service):
        """测试特殊字符"""
        special = "Hello \"World\" <script>alert('xss')</script> 中文 🎉"
        
        integration_service.create_session("special", "Special Chars")
        integration_service.add_message("special", "user", special, 20)
        
        retrieved = integration_service.storage.get_messages("special")
        assert retrieved[0].content == special
    
    def test_unicode_content(self, integration_service):
        """测试 Unicode 内容"""
        unicode_content = "你好世界 🌍 Привет мир مرحبا بالعالم"
        
        integration_service.create_session("unicode", "Unicode Test")
        integration_service.add_message("unicode", "user", unicode_content, 30)
        
        retrieved = integration_service.storage.get_messages("unicode")
        assert retrieved[0].content == unicode_content
