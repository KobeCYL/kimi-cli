"""测试配置和 Fixtures"""

import pytest
import tempfile
from pathlib import Path

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import MemoryConfig, StorageConfig


@pytest.fixture
def temp_db_path(tmp_path):
    """临时数据库路径"""
    yield tmp_path / "test_memory.db"


@pytest.fixture
def memory_service(temp_db_path):
    """Memory Service Fixture"""
    # 禁用单例模式（测试用）
    MemoryService._disable_singleton = True
    
    config = MemoryConfig(
        storage=StorageConfig(
            backend="sqlite",
            db_path=str(temp_db_path)
        )
    )
    service = MemoryService(config)
    service.initialize()
    yield service
    # 确保正确关闭
    service.close()
    # 给 SQLite 一点时间释放文件
    import time
    time.sleep(0.01)


@pytest.fixture
def sample_session_data():
    """示例会话数据"""
    return {
        "session_id": "test-session-001",
        "title": "Test Session",
        "messages": [
            {"role": "user", "content": "Hello, how are you?", "timestamp": 1700000000},
            {"role": "assistant", "content": "I'm doing well, thank you!", "timestamp": 1700000010},
        ]
    }
