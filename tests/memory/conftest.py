"""测试配置和 Fixtures"""

import pytest
import tempfile
from pathlib import Path

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import MemoryConfig, StorageConfig


@pytest.fixture
def temp_db_path():
    """临时数据库路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_memory.db"


@pytest.fixture
def memory_service(temp_db_path):
    """Memory Service Fixture"""
    config = MemoryConfig(
        storage=StorageConfig(
            backend="sqlite",
            db_path=str(temp_db_path)
        )
    )
    service = MemoryService(config)
    service.initialize()
    yield service
    service.close()


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
