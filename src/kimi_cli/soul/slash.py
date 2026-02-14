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


@registry.command
async def memory(soul: KimiSoul, args: str):
    """Memory system management commands"""
    await memory_command(soul, args)


@registry.command
async def recall(soul: KimiSoul, args: str):
    """Recall relevant historical conversations"""
    await recall_command(soul, args)
