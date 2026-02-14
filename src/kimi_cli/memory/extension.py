"""Memory 系统扩展入口

将 Memory 系统集成到 Kimi CLI 的扩展系统中
"""

from __future__ import annotations

# 导入命令以便注册
from kimi_cli.memory.commands.recall_cmd import recall_command
from kimi_cli.memory.commands.memory_cmd import memory_command

# 导出命令函数供装饰器使用
# 这些函数会在命令文件被导入时自动注册

__all__ = [
    "recall_command",
    "memory_command",
]
