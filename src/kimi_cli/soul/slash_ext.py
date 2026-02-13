"""Extended slash command support for custom /xxx commands.

This module provides a plugin system for users to define custom slash commands
in external Python files or configuration directories.

Example usage:
    1. Create a custom command file at ~/.kimi/commands/mycommand.py
    2. Or create a project-local .kimi/commands/mycommand.py
    3. The command will be automatically loaded as /mycommand
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from kimi_cli.utils.slashcmd import SlashCommand, SlashCommandRegistry

if TYPE_CHECKING:
    from kimi_cli.soul.kimisoul import KimiSoul
    from kimi_cli.ui.shell import Shell

type SoulSlashCmdFunc = Callable[[KimiSoul, str], None | Awaitable[None]]
type ShellSlashCmdFunc = Callable[[Shell, str], None | Awaitable[None]]


class SlashExtensionLoader:
    """Loader for custom slash command extensions.
    
    Scans the following directories for custom command files:
    1. Project-local: {work_dir}/.kimi/commands/*.py
    2. User-global: ~/.kimi/commands/*.py (or platform equivalent)
    
    Each Python file can define commands using decorators:
    
        @soul_command
        async def mycmd(soul: KimiSoul, args: str):
            \"\"\"Description of mycmd\"\"\"
            pass
            
        @shell_command(aliases=["m"])
        def myshellcmd(shell: Shell, args: str):
            \"\"\"Description of myshellcmd\"\"\"
            pass
    """

    SOUL_REGISTRY: SlashCommandRegistry[SoulSlashCmdFunc] = SlashCommandRegistry()
    SHELL_REGISTRY: SlashCommandRegistry[ShellSlashCmdFunc] = SlashCommandRegistry()

    @classmethod
    def get_commands_dir(cls, work_dir: Path | str | None = None) -> list[Path]:
        """Get list of directories to scan for custom commands.
        
        Args:
            work_dir: Optional project working directory for local commands
            
        Returns:
            List of Path objects representing command directories
        """
        dirs: list[Path] = []
        
        # 1. Project-local commands (highest priority)
        if work_dir is not None:
            local_dir = Path(work_dir) / ".kimi" / "commands"
            if local_dir.exists():
                dirs.append(local_dir)
        
        # 2. User-global commands
        global_dir = cls._get_global_commands_dir()
        if global_dir.exists():
            dirs.append(global_dir)
            
        return dirs

    @classmethod
    def _get_global_commands_dir(cls) -> Path:
        """Get the global user commands directory."""
        # Use platform-appropriate config directory
        if sys.platform == "win32":
            config_dir = Path.home() / ".kimi"
        elif sys.platform == "darwin":
            config_dir = Path.home() / ".kimi"
        else:  # Linux and others
            xdg_config = Path.home() / ".config"
            if xdg_config.exists():
                config_dir = xdg_config / "kimi"
            else:
                config_dir = Path.home() / ".kimi"
        
        return config_dir / "commands"

    @classmethod
    def load_extensions(
        cls, 
        work_dir: Path | str | None = None,
        soul: KimiSoul | None = None,
        shell: Shell | None = None,
    ) -> dict[str, list[str]]:
        """Load all custom slash command extensions.
        
        Args:
            work_dir: Project working directory for local commands
            soul: KimiSoul instance to pass to soul-level commands
            shell: Shell instance to pass to shell-level commands
            
        Returns:
            Dict with 'loaded' and 'errors' lists for reporting
        """
        result = {"loaded": [], "errors": []}
        
        # Create registries for this load session
        soul_registry: SlashCommandRegistry[SoulSlashCmdFunc] = SlashCommandRegistry()
        shell_registry: SlashCommandRegistry[ShellSlashCmdFunc] = SlashCommandRegistry()
        
        # Get decorator functions that register to our local registries
        def soul_command_decorator(
            func: SoulSlashCmdFunc | None = None,
            *,
            name: str | None = None,
            aliases: list[str] | None = None,
        ) -> SoulSlashCmdFunc | Callable[[SoulSlashCmdFunc], SoulSlashCmdFunc]:
            """Decorator for soul-level custom commands."""
            def decorator(f: SoulSlashCmdFunc) -> SoulSlashCmdFunc:
                # Wrap the function to inject soul instance
                async def wrapper(soul_instance: KimiSoul, args: str) -> None:
                    if soul is not None:
                        await f(soul_instance, args)
                    else:
                        logger.warning(f"Soul command {f.__name__} called but no soul available")
                
                # Copy metadata
                wrapper.__name__ = f.__name__
                wrapper.__doc__ = f.__doc__
                
                soul_registry.command(wrapper, name=name, aliases=aliases or [])
                return f
            
            if func is not None:
                return decorator(func)
            return decorator

        def shell_command_decorator(
            func: ShellSlashCmdFunc | None = None,
            *,
            name: str | None = None,
            aliases: list[str] | None = None,
        ) -> ShellSlashCmdFunc | Callable[[ShellSlashCmdFunc], ShellSlashCmdFunc]:
            """Decorator for shell-level custom commands."""
            def decorator(f: ShellSlashCmdFunc) -> ShellSlashCmdFunc:
                # Wrap the function to inject shell instance
                def wrapper(shell_instance: Shell, args: str) -> None:
                    if shell is not None:
                        f(shell_instance, args)
                    else:
                        logger.warning(f"Shell command {f.__name__} called but no shell available")
                
                # Copy metadata
                wrapper.__name__ = f.__name__
                wrapper.__doc__ = f.__doc__
                
                shell_registry.command(wrapper, name=name, aliases=aliases or [])
                return f
            
            if func is not None:
                return decorator(func)
            return decorator

        # Scan and load command files
        for cmd_dir in cls.get_commands_dir(work_dir):
            if not cmd_dir.is_dir():
                continue
                
            for cmd_file in sorted(cmd_dir.glob("*.py")):
                if cmd_file.name.startswith("_"):
                    continue
                    
                try:
                    cls._load_command_file(
                        cmd_file, 
                        soul_command_decorator, 
                        shell_command_decorator,
                        result
                    )
                except Exception as e:
                    error_msg = f"Failed to load {cmd_file.name}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

        # Update class registries
        cls.SOUL_REGISTRY = soul_registry
        cls.SHELL_REGISTRY = shell_registry
        
        return result

    @classmethod
    def _load_command_file(
        cls,
        cmd_file: Path,
        soul_decorator: Callable,
        shell_decorator: Callable,
        result: dict,
    ) -> None:
        """Load a single command file."""
        module_name = f"kimi_cli_custom_{cmd_file.stem}"
        
        spec = importlib.util.spec_from_file_location(module_name, cmd_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec from {cmd_file}")
            
        module = importlib.util.module_from_spec(spec)
        
        # Inject decorator functions into module namespace
        module.__dict__["soul_command"] = soul_decorator
        module.__dict__["shell_command"] = shell_decorator
        
        # Also provide shorthand aliases
        module.__dict__["soul_cmd"] = soul_decorator
        module.__dict__["shell_cmd"] = shell_decorator
        
        spec.loader.exec_module(module)
        
        result["loaded"].append(cmd_file.stem)
        logger.info(f"Loaded custom slash commands from {cmd_file}")

    @classmethod
    def get_soul_commands(cls) -> list[SlashCommand[SoulSlashCmdFunc]]:
        """Get all loaded soul-level commands."""
        return cls.SOUL_REGISTRY.list_commands()

    @classmethod
    def get_shell_commands(cls) -> list[SlashCommand[ShellSlashCmdFunc]]:
        """Get all loaded shell-level commands."""
        return cls.SHELL_REGISTRY.list_commands()

    @classmethod
    def find_soul_command(cls, name: str) -> SlashCommand[SoulSlashCmdFunc] | None:
        """Find a soul-level command by name."""
        return cls.SOUL_REGISTRY.find_command(name)

    @classmethod
    def find_shell_command(cls, name: str) -> SlashCommand[ShellSlashCmdFunc] | None:
        """Find a shell-level command by name."""
        return cls.SHELL_REGISTRY.find_command(name)


def init_custom_commands(
    work_dir: Path | str | None = None,
    soul: KimiSoul | None = None,
    shell: Shell | None = None,
) -> dict[str, list[str]]:
    """Initialize and load all custom slash commands.
    
    This is the main entry point for loading custom commands.
    Should be called during application startup.
    
    Args:
        work_dir: Project working directory
        soul: KimiSoul instance
        shell: Shell instance
        
    Returns:
        Loading results with 'loaded' and 'errors' lists
        
    Example:
        >>> from kimi_cli.soul.slash_ext import init_custom_commands
        >>> result = init_custom_commands(work_dir="/project", soul=my_soul, shell=my_shell)
        >>> print(f"Loaded: {result['loaded']}")
    """
    return SlashExtensionLoader.load_extensions(work_dir, soul, shell)


# Convenience exports for command file authors
__all__ = [
    "SlashExtensionLoader",
    "init_custom_commands",
]
