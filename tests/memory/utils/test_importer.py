"""导入工具测试"""

import pytest
import json
import tempfile
from pathlib import Path

from kimi_cli.memory.utils.importer import SessionImporter
from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import MemoryConfig, StorageConfig


class TestSessionImporter:
    """SessionImporter 测试"""
    
    @pytest.fixture
    def importer_service(self):
        """创建带 importer 的 service"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MemoryConfig(
                storage=StorageConfig(
                    backend="sqlite",
                    db_path=str(Path(tmpdir) / "import.db")
                )
            )
            service = MemoryService(config)
            service.initialize()
            
            importer = SessionImporter(service)
            
            yield service, importer
            
            service.close()
            MemoryService._instance = None
    
    @pytest.fixture
    def mock_kimi_sessions(self):
        """创建模拟的 Kimi 会话目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / "sessions"
            work_dir = sessions_dir / "work123"
            work_dir.mkdir(parents=True)
            
            # 创建模拟会话
            session_dir = work_dir / "session-abc-001"
            session_dir.mkdir()
            
            # 创建 wire 文件
            wire_file = session_dir / "conversation.wire"
            with open(wire_file, 'w') as f:
                # 元数据
                f.write(json.dumps({"type": "metadata", "protocol_version": "1.0"}) + "\n")
                
                # 用户消息
                f.write(json.dumps({
                    "timestamp": 1700000000,
                    "message": {
                        "type": "turn_begin",
                        "user_input": "How to use Python?"
                    }
                }) + "\n")
                
                # AI 回复
                f.write(json.dumps({
                    "timestamp": 1700000010,
                    "message": {
                        "type": "text",
                        "text": "Python is easy to learn."
                    }
                }) + "\n")
            
            yield str(sessions_dir)
    
    def test_parse_wire_record_user(self, importer_service):
        """测试解析用户消息"""
        _, importer = importer_service
        
        record = {
            "timestamp": 1700000000,
            "message": {
                "type": "turn_begin",
                "user_input": "Hello world"
            }
        }
        
        result = importer._parse_wire_record(record)
        
        assert result is not None
        assert result["role"] == "user"
        assert result["content"] == "Hello world"
        assert result["timestamp"] == 1700000000
    
    def test_parse_wire_record_assistant(self, importer_service):
        """测试解析助手消息"""
        _, importer = importer_service
        
        record = {
            "timestamp": 1700000010,
            "message": {
                "type": "text",
                "text": "Hi there!"
            }
        }
        
        result = importer._parse_wire_record(record)
        
        assert result is not None
        assert result["role"] == "assistant"
        assert result["content"] == "Hi there!"
    
    def test_parse_session(self, importer_service, mock_kimi_sessions):
        """测试解析会话目录"""
        _, importer = importer_service
        
        session_dir = Path(mock_kimi_sessions) / "work123" / "session-abc-001"
        result = importer._parse_session(session_dir)
        
        assert result is not None
        assert result["session_id"] == "session-abc-001"
        assert "How to use Python?" in result["title"]
        assert len(result["messages"]) == 2
    
    def test_import_all(self, importer_service, mock_kimi_sessions):
        """测试完整导入流程"""
        service, importer = importer_service
        
        stats = importer.import_all(
            kimi_sessions_dir=mock_kimi_sessions,
            dry_run=False,
            skip_existing=False
        )
        
        assert stats["total_sessions"] == 1
        assert stats["imported_sessions"] == 1
        assert stats["imported_messages"] == 2
        
        # 验证数据已导入
        session = service.get_session("session-abc-001")
        assert session is not None
        assert "Python" in session.title
        
        messages = service.storage.get_messages("session-abc-001")
        assert len(messages) == 2
    
    def test_skip_existing(self, importer_service, mock_kimi_sessions):
        """测试跳过已存在会话"""
        service, importer = importer_service
        
        # 先导入一次
        importer.import_all(mock_kimi_sessions, skip_existing=False)
        
        # 重置统计
        importer.stats = {
            "total_sessions": 0,
            "imported_sessions": 0,
            "skipped_sessions": 0,
            "total_messages": 0,
            "imported_messages": 0,
            "errors": [],
        }
        
        # 再次导入，应该跳过
        stats = importer.import_all(mock_kimi_sessions, skip_existing=True)
        
        assert stats["total_sessions"] == 1
        assert stats["skipped_sessions"] == 1
        assert stats["imported_sessions"] == 0
    
    def test_dry_run(self, importer_service, mock_kimi_sessions):
        """测试试运行模式"""
        service, importer = importer_service
        
        stats = importer.import_all(
            mock_kimi_sessions,
            dry_run=True,
            skip_existing=False
        )
        
        # 统计显示导入，但数据未写入
        assert stats["imported_sessions"] == 1
        
        # 验证未写入
        session = service.get_session("session-abc-001")
        assert session is None
    
    def test_generate_report(self, importer_service, mock_kimi_sessions):
        """测试生成报告"""
        _, importer = importer_service
        
        importer.import_all(mock_kimi_sessions)
        
        report = importer.generate_report()
        
        assert "Import Report" in report
        assert "Total Sessions Found: 1" in report
        assert "Imported: 1" in report
