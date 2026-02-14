"""集成测试"""

import pytest

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import MemoryConfig, StorageConfig


class TestIntegration:
    """集成测试 - 端到端流程"""
    
    def test_full_workflow(self, tmp_path):
        """测试完整工作流"""
        # 禁用单例
        MemoryService._disable_singleton = True
        
        config = MemoryConfig(
            storage=StorageConfig(
                backend="sqlite",
                db_path=str(tmp_path / "integration.db")
            )
        )
        service = MemoryService(config)
        service.initialize()
        
        try:
            # 1. 创建多个会话
            sessions = [
                ("py-session", "Python Tutorial", "How to learn Python programming"),
                ("js-session", "JavaScript Guide", "JavaScript async/await tutorial"),
            ]
            
            for sid, title, first_msg in sessions:
                service.create_session(sid, title)
                service.add_message(sid, "user", first_msg, 20)
                service.add_message(sid, "assistant", f"Guide for {title}", 30)
            
            # 2. 检查统计
            stats = service.get_stats()
            assert stats["total_sessions"] == 2
            assert stats["total_messages"] == 4
            
            # 3. 召回测试
            results = service.recall("Python programming", top_k=5)
            assert isinstance(results, list)
            
        finally:
            service.close()
    
    def test_persistence(self, tmp_path):
        """测试数据持久化"""
        db_path = tmp_path / "persist.db"
        
        # 禁用单例
        MemoryService._disable_singleton = True
        
        # 第一次：创建数据
        config = MemoryConfig(
            storage=StorageConfig(db_path=str(db_path))
        )
        service1 = MemoryService(config)
        service1.initialize()
        
        service1.create_session("persist-test", "Persistent Session")
        service1.add_message("persist-test", "user", "Test message", 10)
        
        service1.close()
        
        # 第二次：读取数据
        service2 = MemoryService(config)
        service2.initialize()
        
        try:
            session = service2.get_session("persist-test")
            assert session is not None
            assert session.title == "Persistent Session"
            
            messages = service2.storage.get_messages("persist-test")
            assert len(messages) == 1
            assert messages[0].content == "Test message"
        finally:
            service2.close()


class TestEdgeCases:
    """边界情况测试"""
    
    def test_empty_database(self, tmp_path):
        """测试空数据库"""
        MemoryService._disable_singleton = True
        
        config = MemoryConfig(
            storage=StorageConfig(db_path=str(tmp_path / "empty.db"))
        )
        service = MemoryService(config)
        service.initialize()
        
        try:
            results = service.recall("test query", top_k=5)
            assert results == []
        finally:
            service.close()
    
    def test_very_long_content(self, tmp_path):
        """测试超长内容"""
        MemoryService._disable_singleton = True
        
        config = MemoryConfig(
            storage=StorageConfig(db_path=str(tmp_path / "long.db"))
        )
        service = MemoryService(config)
        service.initialize()
        
        try:
            long_content = "A" * 10000
            
            service.create_session("long-content", "Long Content")
            service.add_message("long-content", "user", long_content, 2500)
            
            # 应该能正常处理
            messages = service.storage.get_messages("long-content")
            assert len(messages[0].content) == 10000
        finally:
            service.close()
    
    def test_special_characters(self, tmp_path):
        """测试特殊字符"""
        MemoryService._disable_singleton = True
        
        config = MemoryConfig(
            storage=StorageConfig(db_path=str(tmp_path / "special.db"))
        )
        service = MemoryService(config)
        service.initialize()
        
        try:
            special = "Hello \"World\" <script>alert('xss')</script> 中文 🎉"
            
            service.create_session("special", "Special Chars")
            service.add_message("special", "user", special, 20)
            
            retrieved = service.storage.get_messages("special")
            assert retrieved[0].content == special
        finally:
            service.close()
    
    def test_unicode_content(self, tmp_path):
        """测试 Unicode 内容"""
        MemoryService._disable_singleton = True
        
        config = MemoryConfig(
            storage=StorageConfig(db_path=str(tmp_path / "unicode.db"))
        )
        service = MemoryService(config)
        service.initialize()
        
        try:
            unicode_content = "你好世界 🌍 Привет мир مرحبا بالعالم"
            
            service.create_session("unicode", "Unicode Test")
            service.add_message("unicode", "user", unicode_content, 30)
            
            retrieved = service.storage.get_messages("unicode")
            assert retrieved[0].content == unicode_content
        finally:
            service.close()
