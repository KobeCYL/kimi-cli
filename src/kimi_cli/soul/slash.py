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
from kimi_cli.memory.commands.recall_cmd import recall_command, recall_apply_command
from kimi_cli.memory.services.memory_service import MemoryService


@registry.command
async def memory(soul: KimiSoul, args: str):
    """Memory system management commands"""
    await memory_command(soul, args)


@registry.command
async def recall(soul: KimiSoul, args: str):
    """Recall relevant historical conversations"""
    await recall_command(soul, args)


@registry.command(aliases=["recall-apply"])
async def recall_apply(soul: KimiSoul, args: str):
    """Apply selected recall results to context"""
    await recall_apply_command(soul, args)


def _send_safe(text: str) -> None:
    """安全发送消息, 支持 wire_send 降级到 print"""
    try:
        wire_send(TextPart(text=text))
    except Exception:
        print(text)


@registry.command
async def session(soul: KimiSoul, args: str):
    """View a specific session by ID"""
    session_id = args.strip()
    if not session_id:
        _send_safe("""
Session Viewer

用法:
  /session <session_id>     - 查看指定会话的完整内容
  
获取 session_id:
  1. 使用 /recall 查看搜索结果中的 ID
  2. 使用 /recall --list 查看最近会话

示例:
  /session abc123           - 查看 ID 为 abc123 的会话
""")
        return
    
    service = MemoryService()
    if not service.initialize():
        _send_safe("记忆服务初始化失败")
        return
    
    try:
        session = service.get_session(session_id)
        if not session:
            _send_safe(f"未找到会话: {session_id}")
            return
        
        from datetime import datetime
        dt = datetime.fromtimestamp(session.updated_at)
        
        lines = [
            f"会话详情: {session.title}",
            f"ID: {session.id}",
            f"更新: {dt.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        if session.work_dir:
            lines.append(f"目录: {session.work_dir}")
        
        if session.keywords:
            lines.append(f"关键词: {', '.join(session.keywords)}")
        
        if session.summary:
            lines.append(f"摘要: {session.summary}")
        
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
                role_label = "用户" if msg.role == "user" else "AI"
                lines.append(f"[{msg_dt.strftime('%H:%M:%S')}] {role_label}")
                lines.append(f"  {msg.content}")
                lines.append("")
        
        lines.append("=" * 50)
        
        _send_safe("\n".join(lines))
        
    finally:
        service.close()


# ========== 智能模型路由系统 ==========

# 模型配置
MODELS = {
    "fast": {
        "name": "kimi-code/kimi-for-coding",
        "description": "快速响应模型 - 适合简单问答、代码补全、日常对话",
        "strengths": ["快速", "代码", "日常对话", "长上下文"],
        "cost_level": "低",
        "max_context": 262144,
        "speed": "快",
    },
    "balanced": {
        "name": "deepseek",
        "description": "平衡模型 - 适合中等复杂度任务、推理、代码审查",
        "strengths": ["推理", "分析", "代码审查", "数学"],
        "cost_level": "中",
        "max_context": 64000,
        "speed": "中等",
    },
    "powerful": {
        "name": "deepseek",
        "description": "强力模型 - 适合复杂任务、深度分析",
        "strengths": ["复杂推理", "深度分析", "问题解决"],
        "cost_level": "中",
        "max_context": 64000,
        "speed": "中等",
    },
}


def _analyze_conversation_for_routing(soul: KimiSoul) -> dict:
    """分析对话特征用于模型路由"""
    analysis = {
        "message_count": 0,
        "total_chars": 0,
        "code_blocks": 0,
        "complexity_score": 0,
        "token_count": 0,
        "complexity_indicators": [],
        "is_simple_chat": False,
    }
    
    try:
        ctx = soul.context
        history = list(ctx.history)
        
        analysis["message_count"] = len(history)
        analysis["token_count"] = ctx.token_count
        
        # 分析最近 10 条消息
        recent_messages = history[-10:] if len(history) > 10 else history
        
        # 关键词定义
        complexity_keywords = [
            ('架构', 2), ('设计模式', 2), ('重构', 2), ('优化', 2), ('性能调优', 2),
            ('算法', 2), ('数据结构', 2), ('微服务', 2), ('分布式', 2), ('并发', 2),
            ('多线程', 2), ('K8s', 2), ('Docker', 2), ('Kubernetes', 2),
            ('debug', 2), ('调试', 2), ('排查', 2), ('定位', 2), ('内存泄漏', 2),
            ('深度学习', 2), ('机器学习', 2), ('AI', 1), ('模型训练', 2),
            ('安全', 2), ('加密', 2), ('漏洞', 2), ('攻击', 2),
            ('architecture', 2), ('design pattern', 2), ('refactor', 2), ('optimize', 2),
            ('performance', 2), ('algorithm', 2), ('concurrent', 2), ('distributed', 2),
        ]
        
        simple_patterns = [
            r'^(你好|您好|hello|hi|hey)\s*$',
            r'^(谢谢|感谢|thanks|thank you)\s*$',
            r'^(再见|拜拜|bye|goodbye)\s*$',
        ]
        
        content_text = ""
        for msg in recent_messages:
            content = str(msg.content) if hasattr(msg, 'content') else ""
            content_text += content + " "
            analysis["total_chars"] += len(content)
            
            # 代码块统计
            import re
            analysis["code_blocks"] += len(re.findall(r'```[\s\S]*?```', content))
            
            # 复杂度评分
            content_lower = content.lower()
            for keyword, score in complexity_keywords:
                if keyword.lower() in content_lower:
                    analysis["complexity_score"] += score
                    if keyword not in analysis["complexity_indicators"]:
                        analysis["complexity_indicators"].append(keyword)
            
            # 简单对话检测
            for pattern in simple_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    analysis["is_simple_chat"] = True
                    
    except Exception as e:
        logger.debug(f"对话分析异常: {e}")
    
    return analysis


def _recommend_model(analysis: dict) -> tuple[str, str, dict]:
    """根据分析结果推荐模型
    
    Returns:
        (模型key, 推荐原因, 完整推荐信息)
    """
    score = analysis["complexity_score"]
    code_blocks = analysis["code_blocks"]
    token_count = analysis["token_count"]
    is_simple = analysis["is_simple_chat"]
    
    # 决策逻辑
    if is_simple and token_count < 5000 and score == 0:
        return "fast", "简单对话，快速响应即可", {
            "action": "保持当前模型或切换到 kimi-for-coding",
            "confidence": "high"
        }
    
    if score >= 6 or code_blocks >= 3 or token_count > 40000:
        return "powerful", "复杂任务需要深度推理能力", {
            "action": "建议切换到 deepseek 模型",
            "confidence": "high"
        }
    
    if score >= 3 or code_blocks >= 2 or token_count > 15000:
        return "balanced", "中等复杂度任务", {
            "action": "建议使用 deepseek 模型",
            "confidence": "medium"
        }
    
    # 默认情况
    if token_count < 8000 and score < 2:
        return "fast", "常规任务，当前模型可满足", {
            "action": "保持当前模型",
            "confidence": "medium"
        }
    
    return "balanced", "建议使用平衡模型以获得更好效果", {
        "action": "建议使用 deepseek 模型",
        "confidence": "low"
    }


@registry.command
async def smart_model(soul: KimiSoul, args: str):
    """智能分析对话并推荐最优模型
    
    用法:
    /smart_model           - 分析当前对话并给出模型建议
    /smart_model --switch  - 分析并自动切换到推荐模型
    """
    args = args.strip()
    auto_switch = "--switch" in args
    
    _send_safe("🧠 正在分析对话特征...")
    
    analysis = _analyze_conversation_for_routing(soul)
    model_key, reason, info = _recommend_model(analysis)
    recommended = MODELS[model_key]
    
    # 构建报告
    lines = [
        "",
        "📊 【对话分析报告】",
        f"  消息数量: {analysis['message_count']} 条",
        f"  Token 使用: {analysis['token_count']:,}",
        f"  代码块数: {analysis['code_blocks']}",
        f"  复杂度评分: {analysis['complexity_score']}",
    ]
    
    if analysis["complexity_indicators"]:
        lines.append(f"  复杂度指标: {', '.join(analysis['complexity_indicators'][:5])}")
    
    lines.extend([
        "",
        f"🎯 【推荐: {model_key.upper()}】",
        f"  模型: {recommended['name']}",
        f"  原因: {reason}",
        f"  描述: {recommended['description']}",
        f"  优势: {', '.join(recommended['strengths'][:3])}",
        f"  成本: {recommended['cost_level']} | 速度: {recommended['speed']}",
        f"  建议操作: {info['action']}",
    ])
    
    _send_safe("\n".join(lines))
    
    # 自动切换
    if auto_switch:
        # 注意：实际切换模型需要调用配置系统，这里先给出提示
        _send_safe(f"\n💡 使用 `/model {recommended['name']}` 切换到推荐模型")


@registry.command(aliases=["route"])
async def model_route(soul: KimiSoul, args: str):
    """快速路由到推荐模型
    
    用法:
    /route              - 分析并显示推荐模型
    /route fast         - 切换到快速模型
    /route balanced     - 切换到平衡模型
    /route powerful     - 切换到强力模型
    """
    args = args.strip().lower()
    
    # 如果指定了具体模型级别，直接显示信息
    if args in MODELS:
        model = MODELS[args]
        lines = [
            f"",
            f"🎯 【{args.upper()} 模型】",
            f"  名称: {model['name']}",
            f"  描述: {model['description']}",
            f"  优势: {', '.join(model['strengths'])}",
            f"  成本: {model['cost_level']} | 速度: {model['speed']}",
            f"  最大上下文: {model['max_context']:,} tokens",
            f"",
            f"💡 使用 `/model {model['name']}` 切换到此模型",
        ]
        _send_safe("\n".join(lines))
        return
    
    # 否则进行分析
    _send_safe("🔍 正在分析当前对话...")
    
    analysis = _analyze_conversation_for_routing(soul)
    model_key, reason, info = _recommend_model(analysis)
    recommended = MODELS[model_key]
    
    lines = [
        "",
        f"🎯 【推荐模型: {model_key.upper()}】",
        f"  模型: {recommended['name']}",
        f"  原因: {reason}",
        f"  描述: {recommended['description']}",
        f"  优势: {', '.join(recommended['strengths'][:3])}",
        f"  成本: {recommended['cost_level']} | 速度: {recommended['speed']}",
        f"",
        f"📊 对话特征:",
        f"  复杂度评分: {analysis['complexity_score']} | 代码块: {analysis['code_blocks']} | Token: {analysis['token_count']:,}",
        f"",
        f"💡 使用 `/model {recommended['name']}` 切换",
    ]
    
    _send_safe("\n".join(lines))
