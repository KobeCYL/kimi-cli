"""/recall 命令实现"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from kimi_cli.memory.services.memory_service import MemoryService

if TYPE_CHECKING:
    pass  # 避免循环导入


# 这个函数会被装饰器注册到 soul_command
# 但由于我们在独立扩展中, 使用简单的函数定义


class QueryAnalyzer:
    """查询分析器 - 根据查询类型调整搜索策略"""
    
    # 查询类型权重配置
    WEIGHTS = {
        "file_lookup": {"vector": 0.3, "keyword": 0.7, "desc": "文件查找"},
        "vague_recall": {"vector": 0.8, "keyword": 0.2, "desc": "模糊回忆"},
        "technical": {"vector": 0.6, "keyword": 0.4, "desc": "技术问题"},
        "error_debug": {"vector": 0.5, "keyword": 0.5, "desc": "错误调试"},
    }
    
    @classmethod
    def analyze(cls, query: str) -> tuple[str, dict]:
        """
        分析查询类型, 返回类型和权重配置
        
        Returns:
            (类型名称, 权重配置)
        """
        query_lower = query.lower()
        
        # 1. 文件查找特征
        file_patterns = [
            r'[\w\-]+\.(py|js|ts|go|rs|java|cpp|c|h|md|json|yml|yaml|toml|sh|bash|zsh)',
            r'\.\w+$',  # 以扩展名结尾
            r'文件|file|路径|path|目录|folder|config|配置',
        ]
        for pattern in file_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return "file_lookup", cls.WEIGHTS["file_lookup"]
        
        # 2. 错误调试特征
        error_patterns = [
            r'错误|error|exception|bug|崩溃|crash|fail|失败|报错|traceback|stack trace',
            r'\b\d{3,4}\b',  # 错误码
        ]
        for pattern in error_patterns:
            if re.search(pattern, query_lower):
                return "error_debug", cls.WEIGHTS["error_debug"]
        
        # 3. 模糊回忆特征(指代性词汇)
        vague_patterns = [
            r'那个|上次|之前|说过|讨论过|提过|记得|好像|大概|似乎',
            r'之前说的|上次的|之前的|之前那个',
        ]
        for pattern in vague_patterns:
            if re.search(pattern, query_lower):
                return "vague_recall", cls.WEIGHTS["vague_recall"]
        
        # 4. 默认技术问题
        return "technical", cls.WEIGHTS["technical"]


def _send_message(text: str) -> None:
    """发送消息到 UI, 支持 wire_send 降级到 print"""
    try:
        from kimi_cli.soul import wire_send
        from kimi_cli.wire.types import TextPart
        wire_send(TextPart(text=text))
    except Exception:
        # wire 不可用, 使用 print
        print(text)


async def recall_command(soul, args: str):
    """
    召回相关历史对话
    
    用法:
    /recall              - 基于当前会话上下文召回
    /recall "关键词"      - 搜索特定主题
    /recall --list       - 列出最近的会话
    /recall --stats      - 显示记忆统计
    /recall --verbose    - 详细模式(显示消息ID和完整预览)
    """
    args = args.strip()
    
    # 检查详细模式
    verbose = "--verbose" in args or "-v" in args
    args = args.replace("--verbose", "").replace("-v", "").strip()
    
    # 初始化服务
    service = MemoryService()
    if not service.initialize():
        _send_message("记忆服务初始化失败, 请先运行 /memory init")
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
        await _do_recall(service, soul, args, verbose)
        
    finally:
        service.close()


async def _do_recall(service: MemoryService, soul, query: str, verbose: bool = False):
    """执行召回"""
    # 获取当前会话信息
    current_session_id = ""
    context_text = query
    
    try:
        if hasattr(soul, 'context') and soul.context:
            # 获取会话ID
            if hasattr(soul.context, 'session_id'):
                current_session_id = soul.context.session_id
            
            # 如果没有提供查询, 使用最近的消息作为上下文
            if not query and hasattr(soul.context, 'history'):
                recent_msgs = soul.context.history[-3:] if len(soul.context.history) > 3 else soul.context.history
                context_text = " ".join([
                    str(m.content) for m in recent_msgs 
                    if hasattr(m, 'content')
                ])
    except Exception:
        pass
    
    if not context_text:
        _send_message("无法获取上下文, 请输入关键词:\n/recall \"你的查询\"")
        return
    
    # 分析查询类型
    query_type, weights = QueryAnalyzer.analyze(context_text)
    search_desc = weights.get("desc", "技术问题")
    
    # 显示加载状态
    loading_text = f"正在搜索相关记忆... [{search_desc}]"
    if verbose:
        loading_text += f"\n   搜索策略: 向量{weights['vector']:.0%} + 关键词{weights['keyword']:.0%}"
    _send_message(loading_text)
    
    # 执行召回(传递权重)
    results = service.recall(
        context_text=context_text,
        current_session_id=current_session_id,
        top_k=5,
        vector_weight=weights.get("vector", 0.6),
        keyword_weight=weights.get("keyword", 0.4),
    )
    
    if not results:
        _send_message("未找到相关历史对话")
        return
    
    # 构建增强的结果展示
    lines = [
        f"找到 {len(results)} 条相关记忆:",
        f"   搜索模式: {search_desc} (向量{weights['vector']:.0%} + 关键词{weights['keyword']:.0%})",
        "",
    ]
    
    for i, result in enumerate(results, 1):
        from datetime import datetime
        dt = datetime.fromtimestamp(result.session.updated_at)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
        
        # 主标题行
        lines.append(f"[{i}] {result.session.title}")
        
        # 元信息行
        meta_info = f"    日期: {date_str} | 相关度: {result.combined_score:.1%}"
        if verbose:
            meta_info += f" | ID: {result.session.id[:8]}"
        lines.append(meta_info)
        
        # 关键词
        if result.session.keywords:
            lines.append(f"    关键词: {', '.join(result.session.keywords[:5])}")
        
        # 工作目录(如果与当前不同)
        if result.session.work_dir:
            try:
                import os
                current_dir = os.getcwd()
                if result.session.work_dir != current_dir:
                    lines.append(f"    目录: {result.session.work_dir}")
            except Exception:
                pass
        
        # 上下文消息预览
        if result.context_messages:
            user_msg = next(
                (m for m in result.context_messages if m.role == "user"),
                None
            )
            ai_msg = next(
                (m for m in result.context_messages if m.role == "assistant"),
                None
            )
            
            if user_msg:
                preview_len = 200 if verbose else 80
                preview = user_msg.content[:preview_len] + "..." if len(user_msg.content) > preview_len else user_msg.content
                lines.append(f"    你: {preview}")
            
            if ai_msg and verbose:
                preview = ai_msg.content[:150] + "..." if len(ai_msg.content) > 150 else ai_msg.content
                lines.append(f"    AI: {preview}")
            
            # 显示消息ID(用于溯源)
            if verbose and result.context_messages:
                msg_ids = [str(m.id)[:8] for m in result.context_messages if hasattr(m, 'id')]
                if msg_ids:
                    lines.append(f"    消息ID: {', '.join(msg_ids)}")
        
        # 查看命令提示
        lines.append(f"    查看完整: /session {result.session.id}")
        lines.append("")
    
    lines.append("提示: 相关上下文已自动添加到系统提示中")
    if not verbose:
        lines.append("提示: 使用 /recall --verbose 查看详细信息和消息ID")
    
    _send_message("\n".join(lines))
    
    # 构建并发送 prompt 上下文
    prompt_context = service.get_recall_context(
        context_text=context_text,
        current_session_id=current_session_id,
    )
    
    if prompt_context:
        # 将上下文添加到系统提示
        try:
            from kimi_cli.soul.message import system
            from kosong.message import Message
            
            system_message = system(prompt_context)
            await soul.context.append_message(
                Message(role="user", content=[system_message])
            )
        except Exception as e:
            # 静默失败, 不影响主流程
            pass


async def _show_stats(service: MemoryService):
    """显示统计信息"""
    stats = service.get_stats()
    
    lines = [
        "记忆库统计:",
        "",
        f"总会话数: {stats.get('total_sessions', 0)}",
        f"总消息数: {stats.get('total_messages', 0)}",
        f"总Token数: {stats.get('total_tokens', 0):,}",
        f"已归档: {stats.get('archived_sessions', 0)}",
    ]
    
    if 'indexed_vectors' in stats:
        lines.append(f"已索引向量: {stats['indexed_vectors']}")
    
    lines.append(f"向量支持: {'是' if stats.get('vec_available') else '否'}")
    
    # 添加搜索策略说明
    lines.extend([
        "",
        "支持的搜索策略:",
        "  * 文件查找 - 识别文件路径/扩展名",
        "  * 模糊回忆 - 处理\"那个\"、\"上次\"等指代",
        "  * 错误调试 - 识别错误码和异常信息",
        "  * 技术问题 - 默认混合检索",
    ])
    
    _send_message("\n".join(lines))


async def _list_sessions(service: MemoryService):
    """列会话列表"""
    sessions = service.storage.list_sessions(limit=20)
    
    if not sessions:
        _send_message("暂无会话记录")
        return
    
    lines = ["最近会话:", ""]
    
    for session in sessions:
        from datetime import datetime
        dt = datetime.fromtimestamp(session.updated_at)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
        
        status = "已归档" if session.is_archived else "活跃"
        lines.append(f"[{status}] [{date_str}] {session.title}")
        
        if session.keywords:
            lines.append(f"    关键词: {', '.join(session.keywords[:3])}")
        
        # 添加查看命令
        lines.append(f"    查看: /session {session.id}")
    
    _send_message("\n".join(lines))


# 导出供装饰器使用
__all__ = ["recall_command"]
