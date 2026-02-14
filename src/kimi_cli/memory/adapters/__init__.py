"""适配器层 - 存储、Embedding、同步的抽象接口"""

from kimi_cli.memory.adapters.storage.base import StorageBackend
from kimi_cli.memory.adapters.embedding.base import EmbeddingProvider
from kimi_cli.memory.adapters.sync.base import SyncBackend

__all__ = ["StorageBackend", "EmbeddingProvider", "SyncBackend"]
