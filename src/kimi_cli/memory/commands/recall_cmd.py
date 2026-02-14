"""/recall 命令实现 - 支持自动检测、多选交互、去重过滤、模式切换"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from kimi_cli.memory.services.memory_service import MemoryService

if TYPE_CHECKING:
    pass  # 避免循环导入


# 模糊词汇模式 - 用于自动触发召回
VAGUE_RECALL_PATTERNS = [
    r'那个|那个\w+|之前|上次|以前|刚才|刚刚',
    r'说过|讨论过|提过|聊过|讲过',
    r'记得|好像|大概|似乎|应该',
    r'之前说的|上次的|之前的|之前那个|刚才的',
    r'怎么.*来.*着|是什么.*来.*着',
]

# 临时触发标记
TEMP_RECALL_MARKERS = ['#recall', '#记忆', '#recall:', '#记忆：']


def get_recall_settings_path() -> Path:
    """获取召回设置文件路径"""
    return Path.home() / ".kimi" / "memory" / "recall_settings.json"


def load_recall_settings() -> dict:
    """加载召回设置"""
    settings_path = get_recall_settings_path()
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "auto_recall": False,  # 默认关闭自动召回
        "default_top_k": 5,
        "auto_inject": False,  # 是否自动注入（否则提示选择）
    }


def save_recall_settings(settings: dict) -> None:
    """保存召回设置"""
    settings_path = get_recall_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def should_auto_recall(text: str) -> bool:
    """检测文本是否包含模糊指代词汇，需要自动召回"""
    # 先检查是否有临时触发标记
    text_stripped = text.strip()
    for marker in TEMP_RECALL_MARKERS:
        if text_stripped.startswith(marker):
            return True
    
    # 检查全局设置
    settings = load_recall_settings()
    if not settings.get("auto_recall", False):
        return False
    
    # 检测模糊指代词汇
    text_lower = text.lower()
    for pattern in VAGUE_RECALL_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def extract_recall_query(text: str) -> str:
    """从文本中提取召回查询（移除临时触发标记）"""
    text_stripped = text.strip()
    for marker in TEMP_RECALL_MARKERS:
        if text_stripped.startswith(marker):
            query = text_stripped[len(marker):].strip()
            # 移除可能的冒号
            if query.startswith(':') or query.startswith('：'):
                query = query[1:].strip()
            return query
    return text


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
        for pattern in VAGUE_RECALL_PATTERNS:
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
    /recall                     - 基于当前会话上下文召回
    /recall "关键词"             - 搜索特定主题
    /recall --auto              - 自动检测并召回（内部使用）
    /recall --list              - 列出最近的会话
    /recall --stats             - 显示记忆统计
    /recall --verbose           - 详细模式
    /recall --mode              - 查看当前模式设置
    /recall --mode auto         - 开启自动召回
    /recall --mode manual       - 关闭自动召回（默认）
    """
    args = args.strip()
    
    # 检查详细模式
    verbose = "--verbose" in args or "-v" in args
    args = args.replace("--verbose", "").replace("-v", "").strip()
    
    # 检查自动模式
    auto_mode = "--auto" in args
    args = args.replace("--auto", "").strip()
    
    # 处理模式设置
    if "--mode" in args:
        await _handle_mode_command(args.replace("--mode", "").strip())
        return
    
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
        
        if args == "":
            # 显示当前模式
            settings = load_recall_settings()
            mode_status = "开启" if settings.get("auto_recall") else "关闭"
            _send_message(f"当前自动召回模式: {mode_status}\n使用 `/recall --mode auto/manual` 切换")
            return
        
        # 执行召回
        await _do_recall(service, soul, args, verbose, auto_mode)
        
    finally:
        service.close()


async def _handle_mode_command(mode: str):
    """处理模式设置命令"""
    settings = load_recall_settings()
    
    if mode == "":
        # 显示当前模式
        mode_status = "开启" if settings.get("auto_recall") else "关闭"
        auto_inject = "开启" if settings.get("auto_inject") else "关闭"
        _send_message(f"""
当前召回模式设置:

  自动召回: {mode_status}
  自动注入: {auto_inject}

用法:
  /recall --mode auto     - 开启自动召回
  /recall --mode manual   - 关闭自动召回
  /recall --mode inject   - 自动召回并自动注入

提示:
  • 手动模式: 只有使用 /recall 命令时才搜索
  • 自动模式: 检测到模糊词汇时自动提示
  • 自动注入: 自动召回并直接添加到上下文
  
  临时触发: 在消息开头添加 #recall 可临时触发
    例: #recall 那个 bug 怎么修
""")
        return
    
    if mode == "auto":
        settings["auto_recall"] = True
        settings["auto_inject"] = False
        save_recall_settings(settings)
        _send_message("✅ 已开启自动召回模式\n检测到模糊词汇时将自动提示相关记忆")
    
    elif mode == "manual":
        settings["auto_recall"] = False
        settings["auto_inject"] = False
        save_recall_settings(settings)
        _send_message("✅ 已切换到手动模式\n使用 `/recall 关键词` 主动搜索")
    
    elif mode == "inject":
        settings["auto_recall"] = True
        settings["auto_inject"] = True
        save_recall_settings(settings)
        _send_message("✅ 已开启自动注入模式\n检测到模糊词汇时将自动添加相关记忆到上下文")
    
    else:
        _send_message(f"❌ 未知模式: {mode}\n可用模式: auto, manual, inject")


def _filter_duplicate_results(results, soul) -> list:
    """过滤掉已在当前上下文中的结果"""
    if not results:
        return []
    
    # 获取当前上下文的所有消息内容
    current_context_texts = set()
    try:
        if hasattr(soul, 'context') and soul.context:
            history = getattr(soul.context, 'history', [])
            for msg in history:
                if hasattr(msg, 'content'):
                    text = msg.extract_text(" ") if hasattr(msg, 'extract_text') else str(msg.content)
                    # 存储前50个字符的指纹用于比对
                    current_context_texts.add(text[:100].lower().strip())
    except Exception:
        pass
    
    # 过滤结果
    filtered = []
    for result in results:
        is_duplicate = False
        
        # 检查会话标题
        title_lower = result.session.title.lower().strip()
        if title_lower in current_context_texts or any(title_lower in ctx for ctx in current_context_texts):
            is_duplicate = True
        
        # 检查上下文消息
        if not is_duplicate and result.context_messages:
            for msg in result.context_messages:
                content = msg.content.lower().strip()[:100]
                if content in current_context_texts or any(content in ctx for ctx in current_context_texts):
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            filtered.append(result)
    
    return filtered


async def _do_recall(
    service: MemoryService, 
    soul, 
    query: str, 
    verbose: bool = False,
    auto_mode: bool = False,
):
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
        if not auto_mode:
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
    settings = load_recall_settings()
    top_k = settings.get("default_top_k", 5)
    
    results = service.recall(
        context_text=context_text,
        current_session_id=current_session_id,
        top_k=top_k * 2,  # 获取更多结果以便过滤
        vector_weight=weights.get("vector", 0.6),
        keyword_weight=weights.get("keyword", 0.4),
    )
    
    # 去重过滤：移除已在当前上下文中的结果
    results = _filter_duplicate_results(results, soul)
    
    if not results:
        if auto_mode:
            _send_message("💭 没有找到新的相关历史对话")
        else:
            _send_message("未找到相关历史对话（或已在当前上下文中）")
        return
    
    # 限制展示数量
    display_results = results[:top_k]
    
    # 保存召回结果到 soul 对象供后续选择
    if not hasattr(soul, '_memory_state'):
        soul._memory_state = {}
    soul._memory_state['last_recall_results'] = display_results
    soul._memory_state['last_recall_query'] = context_text
    
    # 检查是否自动注入
    if auto_mode and settings.get("auto_inject", False):
        # 自动注入模式：直接添加所有结果
        await _inject_selected_context(soul, display_results, context_text)
        return
    
    # 构建增强的结果展示
    lines = [
        f"🔍 找到 {len(results)} 条相关记忆（已过滤当前上下文中的重复内容）:",
        f"   搜索模式: {search_desc} (向量{weights['vector']:.0%} + 关键词{weights['keyword']:.0%})",
        "",
    ]
    
    for i, result in enumerate(display_results, 1):
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
    
    if auto_mode:
        lines.append("💡 使用 /recall-apply 1,3 或 /recall-apply all 选择要引用的记忆")
    else:
        lines.append("💡 选择要添加的记忆: /recall-apply 1,3 或 /recall-apply all")
    
    if not verbose:
        lines.append("💡 使用 /recall --verbose 查看详细信息")
    
    _send_message("\n".join(lines))
    
    # 自动模式下，如果没有找到结果或找到结果但不自动注入，直接返回
    if auto_mode:
        return


async def recall_apply_command(soul, args: str):
    """
    应用召回结果 - 选择并注入选中的记忆
    
    用法:
    /recall-apply 1,3    - 选择第1和第3条记忆
    /recall-apply all    - 选择所有记忆
    """
    args = args.strip()
    
    # 获取上次的召回结果
    if not hasattr(soul, '_memory_state') or 'last_recall_results' not in soul._memory_state:
        _send_message("❌ 没有可用的召回结果，请先运行 /recall")
        return
    
    results = soul._memory_state['last_recall_results']
    query_text = soul._memory_state.get('last_recall_query', '')
    
    if not results:
        _send_message("❌ 没有可用的召回结果")
        return
    
    if not args:
        _send_message("""
请选择要应用的记忆:
  /recall-apply 1,3    - 选择第1和第3条记忆
  /recall-apply all    - 选择所有记忆
  
上次的召回结果:
""")
        for i, result in enumerate(results, 1):
            _send_message(f"[{i}] {result.session.title}")
        return
    
    # 解析选择
    selected_indices = []
    if args.lower() == 'all':
        selected_indices = list(range(1, len(results) + 1))
    else:
        try:
            # 解析逗号分隔的数字
            parts = args.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    # 支持范围，如 1-3
                    start, end = part.split('-', 1)
                    selected_indices.extend(range(int(start), int(end) + 1))
                else:
                    selected_indices.append(int(part))
        except ValueError:
            _send_message("❌ 无效的选择格式，请使用: 1,3 或 1-3 或 all")
            return
    
    # 去重并排序
    selected_indices = sorted(set(selected_indices))
    
    # 验证范围
    valid_indices = [i for i in selected_indices if 1 <= i <= len(results)]
    if not valid_indices:
        _send_message(f"❌ 无效的选择，请输入 1-{len(results)} 之间的数字")
        return
    
    # 获取选中的结果
    selected_results = [results[i - 1] for i in valid_indices]
    
    # 注入上下文
    await _inject_selected_context(soul, selected_results, query_text)


async def _inject_selected_context(soul, selected_results: list, query_text: str):
    """将选中的记忆注入上下文"""
    try:
        from kimi_cli.soul.message import system
        from kosong.message import Message
        
        # 构建上下文内容
        context_parts = ["📚 以下是从历史对话中召回的相关上下文：\n"]
        
        for i, result in enumerate(selected_results, 1):
            context_parts.append(f"\n--- 相关记忆 {i} ---")
            context_parts.append(f"主题: {result.session.title}")
            
            if result.context_messages:
                for msg in result.context_messages:
                    if msg.role == "user":
                        context_parts.append(f"用户: {msg.content[:500]}")
                    elif msg.role == "assistant":
                        context_parts.append(f"助手: {msg.content[:500]}")
            
            context_parts.append("")
        
        context_parts.append("--- 召回内容结束 ---")
        context_parts.append(f"\n用户当前问题: {query_text}")
        
        full_context = "\n".join(context_parts)
        
        # 创建系统消息
        system_message = system(full_context)
        
        # 追加到上下文
        await soul.context.append_message(
            Message(role="user", content=[system_message])
        )
        
        _send_message(f"✅ 已添加 {len(selected_results)} 条记忆到上下文")
        
    except Exception as e:
        _send_message(f"❌ 添加上下文失败: {e}")


async def _show_stats(service: MemoryService):
    """显示统计信息"""
    stats = service.get_stats()
    settings = load_recall_settings()
    
    mode_status = "开启" if settings.get("auto_recall") else "关闭"
    auto_inject = "开启" if settings.get("auto_inject") else "关闭"
    
    lines = [
        "记忆库统计:",
        "",
        f"总会话数: {stats.get('total_sessions', 0)}",
        f"总消息数: {stats.get('total_messages', 0)}",
        f"总Token数: {stats.get('total_tokens', 0):,}",
        f"已归档: {stats.get('archived_sessions', 0)}",
        "",
        f"自动召回: {mode_status}",
        f"自动注入: {auto_inject}",
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
__all__ = ["recall_command", "recall_apply_command", "should_auto_recall", "extract_recall_query"]
