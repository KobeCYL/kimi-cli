"""/recall 命令实现"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kimi_cli.memory.services.memory_service import MemoryService

if TYPE_CHECKING:
    pass  # 避免循环导入


# 这个函数会被装饰器注册到 soul_command
# 但由于我们在独立扩展中，使用简单的函数定义

async def recall_command(soul, args: str):
    """
    🧠 召回相关历史对话
    
    用法:
    /recall              - 基于当前会话上下文召回
    /recall "关键词"      - 搜索特定主题
    /recall --list       - 列出最近的会话
    /recall --stats      - 显示记忆统计
    """
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    args = args.strip()
    
    # 初始化服务
    service = MemoryService()
    if not service.initialize():
        wire_send(TextPart(text="❌ 记忆服务初始化失败"))
        return
    
    try:
        # 处理子命令
        if args == "--stats":
            await _show_stats(service)
            return
        
        if args == "--list":
            await _list_sessions(service)
            return
        
        # 执行召回
        await _do_recall(service, soul, args)
        
    finally:
        service.close()


async def _do_recall(service: MemoryService, soul, query: str):
    """执行召回"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    # 获取当前会话信息
    current_session_id = ""
    context_text = query
    
    try:
        if hasattr(soul, 'context') and soul.context:
            # 获取会话ID
            if hasattr(soul.context, 'session_id'):
                current_session_id = soul.context.session_id
            
            # 如果没有提供查询，使用最近的消息作为上下文
            if not query and hasattr(soul.context, 'history'):
                recent_msgs = soul.context.history[-3:] if len(soul.context.history) > 3 else soul.context.history
                context_text = " ".join([
                    str(m.content) for m in recent_msgs 
                    if hasattr(m, 'content')
                ])
    except Exception:
        pass
    
    if not context_text:
        wire_send(TextPart(text="⚠️ 无法获取上下文，请输入关键词:\n/recall \"你的查询\""))
        return
    
    # 显示加载状态
    wire_send(TextPart(text="🔍 正在搜索相关记忆..."))
    
    # 执行召回
    results = service.recall(
        context_text=context_text,
        current_session_id=current_session_id,
        top_k=5,
    )
    
    if not results:
        wire_send(TextPart(text="📝 未找到相关历史对话"))
        return
    
    # 构建结果展示
    lines = [
        f"✅ 找到 {len(results)} 条相关记忆：",
        "",
    ]
    
    for i, result in enumerate(results, 1):
        from datetime import datetime
        dt = datetime.fromtimestamp(result.session.updated_at)
        date_str = dt.strftime("%Y-%m-%d")
        
        lines.extend([
            f"[{i}] {result.session.title}",
            f"    日期: {date_str} | 相关度: {result.combined_score:.1%}",
        ])
        
        if result.session.keywords:
            lines.append(f"    关键词: {', '.join(result.session.keywords[:5])}")
        
        # 显示上下文摘要
        if result.context_messages:
            user_msg = next(
                (m for m in result.context_messages if m.role == "user"),
                None
            )
            if user_msg:
                preview = user_msg.content[:80] + "..." if len(user_msg.content) > 80 else user_msg.content
                lines.append(f"    💬 {preview}")
        
        lines.append("")
    
    lines.append("💡 提示：相关上下文已自动添加到系统提示中")
    
    wire_send(TextPart(text="\n".join(lines)))
    
    # 构建并发送 prompt 上下文
    prompt_context = service.get_recall_context(
        context_text=context_text,
        current_session_id=current_session_id,
    )
    
    if prompt_context:
        # 将上下文添加到系统提示
        from kimi_cli.soul.message import system
        from kosong.message import Message
        
        system_message = system(prompt_context)
        await soul.context.append_message(
            Message(role="user", content=[system_message])
        )


async def _show_stats(service: MemoryService):
    """显示统计信息"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    stats = service.get_stats()
    
    lines = [
        "📊 记忆库统计：",
        "",
        f"总会话数: {stats.get('total_sessions', 0)}",
        f"总消息数: {stats.get('total_messages', 0)}",
        f"总Token数: {stats.get('total_tokens', 0):,}",
        f"已归档: {stats.get('archived_sessions', 0)}",
    ]
    
    if 'indexed_vectors' in stats:
        lines.append(f"已索引向量: {stats['indexed_vectors']}")
    
    lines.append(f"向量支持: {'✅' if stats.get('vec_available') else '❌'}")
    
    wire_send(TextPart(text="\n".join(lines)))


async def _list_sessions(service: MemoryService):
    """列会话列表"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    sessions = service.storage.list_sessions(limit=20)
    
    if not sessions:
        wire_send(TextPart(text="📝 暂无会话记录"))
        return
    
    lines = ["📋 最近会话：", ""]
    
    for session in sessions:
        from datetime import datetime
        dt = datetime.fromtimestamp(session.updated_at)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
        
        status = "📦" if session.is_archived else "📄"
        lines.append(f"{status} [{date_str}] {session.title}")
        
        if session.keywords:
            lines.append(f"    🏷️ {', '.join(session.keywords[:3])}")
    
    wire_send(TextPart(text="\n".join(lines)))


# 导出供装饰器使用
__all__ = ["recall_command"]
