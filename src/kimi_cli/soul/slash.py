from __future__ import annotations

import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from kosong.message import Message
from loguru import logger

import kimi_cli.prompts as prompts
from kimi_cli.soul import wire_send
from kimi_cli.soul.agent import load_agents_md
from kimi_cli.soul.context import Context
from kimi_cli.soul.message import system
from kimi_cli.soul.slash_ext import SlashExtensionLoader
from kimi_cli.utils.slashcmd import SlashCommand, SlashCommandRegistry
from kimi_cli.wire.types import StatusUpdate, TextPart

if TYPE_CHECKING:
    from kimi_cli.soul.kimisoul import KimiSoul

type SoulSlashCmdFunc = Callable[[KimiSoul, str], None | Awaitable[None]]
"""
A function that runs as a KimiSoul-level slash command.

Raises:
    Any exception that can be raised by `Soul.run`.
"""

registry = SlashCommandRegistry[SoulSlashCmdFunc]()


def find_command(name: str) -> SlashCommand[SoulSlashCmdFunc] | None:
    """Find a command by name, checking built-in and custom commands."""
    # First check built-in registry
    cmd = registry.find_command(name)
    if cmd is not None:
        return cmd
    # Then check custom extension registry
    return SlashExtensionLoader.find_soul_command(name)


def list_commands() -> list[SlashCommand[SoulSlashCmdFunc]]:
    """List all commands including custom extensions."""
    built_in = registry.list_commands()
    custom = SlashExtensionLoader.get_soul_commands()
    return built_in + custom


@registry.command
async def init(soul: KimiSoul, args: str):
    """Analyze the codebase and generate an `AGENTS.md` file"""
    from kimi_cli.soul.kimisoul import KimiSoul

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_context = Context(file_backend=Path(temp_dir) / "context.jsonl")
        tmp_soul = KimiSoul(soul.agent, context=tmp_context)
        await tmp_soul.run(prompts.INIT)

    agents_md = await load_agents_md(soul.runtime.builtin_args.KIMI_WORK_DIR)
    system_message = system(
        "The user just ran `/init` slash command. "
        "The system has analyzed the codebase and generated an `AGENTS.md` file. "
        f"Latest AGENTS.md file content:\n{agents_md}"
    )
    await soul.context.append_message(Message(role="user", content=[system_message]))


@registry.command
async def compact(soul: KimiSoul, args: str):
    """Compact the context"""
    if soul.context.n_checkpoints == 0:
        wire_send(TextPart(text="The context is empty."))
        return

    logger.info("Running `/compact`")
    await soul.compact_context()
    wire_send(TextPart(text="The context has been compacted."))
    wire_send(StatusUpdate(context_usage=soul.status.context_usage))


@registry.command(aliases=["reset"])
async def clear(soul: KimiSoul, args: str):
    """Clear the context"""
    logger.info("Running `/clear`")
    await soul.context.clear()
    wire_send(TextPart(text="The context has been cleared."))
    wire_send(StatusUpdate(context_usage=soul.status.context_usage))


@registry.command
async def yolo(soul: KimiSoul, args: str):
    """Toggle YOLO mode (auto-approve all actions)"""
    if soul.runtime.approval.is_yolo():
        soul.runtime.approval.set_yolo(False)
        wire_send(TextPart(text="You only die once! Actions will require approval."))
    else:
        soul.runtime.approval.set_yolo(True)
        wire_send(TextPart(text="You only live once! All actions will be auto-approved."))


# Import and register memory system commands
from kimi_cli.memory.commands.memory_cmd import memory_command
from kimi_cli.memory.commands.recall_cmd import recall_command
from kimi_cli.memory.services.memory_service import MemoryService


@registry.command
async def memory(soul: KimiSoul, args: str):
    """Memory system management commands"""
    await memory_command(soul, args)


@registry.command
async def recall(soul: KimiSoul, args: str):
    """Recall relevant historical conversations"""
    await recall_command(soul, args)


@registry.command
async def session(soul: KimiSoul, args: str):
    """View a specific session by ID"""
    from kimi_cli.wire.types import TextPart
    
    session_id = args.strip()
    if not session_id:
        wire_send(TextPart(text="""
📋 Session Viewer

用法:
  /session <session_id>     - 查看指定会话的完整内容
  
获取 session_id:
  1. 使用 /recall 查看搜索结果中的 ID
  2. 使用 /recall --list 查看最近会话

示例:
  /session abc123           - 查看 ID 为 abc123 的会话
"""))
        return
    
    service = MemoryService()
    if not service.initialize():
        wire_send(TextPart(text="❌ 记忆服务初始化失败"))
        return
    
    try:
        session = service.get_session(session_id)
        if not session:
            wire_send(TextPart(text=f"❌ 未找到会话: {session_id}"))
            return
        
        from datetime import datetime
        dt = datetime.fromtimestamp(session.updated_at)
        
        lines = [
            f"📄 会话详情: {session.title}",
            f"🆔 ID: {session.id}",
            f"📅 更新: {dt.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        if session.work_dir:
            lines.append(f"📁 目录: {session.work_dir}")
        
        if session.keywords:
            lines.append(f"🏷️ 关键词: {', '.join(session.keywords)}")
        
        if session.summary:
            lines.append(f"📝 摘要: {session.summary}")
        
        lines.append("")
        lines.append("=" * 50)
        lines.append("")
        
        # 获取消息
        messages = service.storage.get_recent_messages(session_id, limit=100)
        if not messages:
            lines.append("(无消息)")
        else:
            for msg in messages:
                msg_dt = datetime.fromtimestamp(msg.timestamp)
                role_icon = "👤" if msg.role == "user" else "🤖"
                lines.append(f"{role_icon} [{msg_dt.strftime('%H:%M:%S')}] {msg.role.upper()}")
                lines.append(f"   {msg.content}")
                lines.append("")
        
        lines.append("=" * 50)
        
        wire_send(TextPart(text="\n".join(lines)))
        
    finally:
        service.close()
