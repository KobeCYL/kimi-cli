"""/memory 管理命令实现"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import MemoryConfig


def _send_message(text: str) -> None:
    """发送消息到 UI, 支持 wire_send 降级到 print"""
    try:
        from kimi_cli.soul import wire_send
        from kimi_cli.wire.types import TextPart
        wire_send(TextPart(text=text))
    except Exception:
        # wire 不可用, 使用 print
        print(text)


async def memory_command(soul, args: str):
    """
    记忆系统管理
    
    用法:
    /memory init                - 初始化记忆系统
    /memory status              - 显示状态
    /memory index               - 索引当前会话
    /memory index-all           - 批量索引所有会话
    /memory import              - 导入 Kimi 历史会话
    /memory import --dry-run    - 试运行导入
    /memory eval                - 评估召回效果
    /memory config              - 显示配置
    /memory config --edit       - 编辑配置
    """
    args = args.strip()
    parts = args.split()
    subcmd = parts[0] if parts else "status"
    
    if subcmd == "init":
        await _cmd_init(soul)
    elif subcmd == "status":
        await _cmd_status()
    elif subcmd == "index":
        await _cmd_index(soul)
    elif subcmd == "index-all":
        await _cmd_index_all()
    elif subcmd == "import":
        dry_run = "--dry-run" in parts or "-n" in parts
        await _cmd_import(soul, dry_run)
    elif subcmd == "eval":
        await _cmd_eval(soul)
    elif subcmd == "config":
        edit_mode = "--edit" in parts
        await _cmd_config(edit_mode)
    else:
        _send_message(f"""
记忆系统管理

用法:
  /memory init          - 初始化记忆系统
  /memory status        - 显示状态和统计
  /memory index         - 索引当前会话
  /memory index-all     - 批量索引所有会话
  /memory config        - 查看配置
  /memory config --edit - 编辑配置

当前工作目录: {Path.cwd()}
配置目录: ~/.kimi/memory/
""")


async def _cmd_init(soul):
    """初始化命令"""
    _send_message("正在初始化记忆系统...")
    
    try:
        # 创建目录
        memory_dir = Path.home() / ".kimi" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建默认配置
        config = MemoryConfig()
        config_path = memory_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        
        # 初始化服务
        service = MemoryService(config)
        if not service.initialize():
            _send_message("初始化失败")
            return
        
        _send_message("记忆系统初始化成功!")
        _send_message(f"配置目录: {memory_dir}")
        _send_message(f"数据库: {config.storage.db_path}")
        
        # 导入当前会话的历史消息
        _send_message("")
        _send_message("正在导入当前会话...")
        current_count = await _import_current_session(soul, service)
        if current_count > 0:
            _send_message(f"已导入当前会话的 {current_count} 条消息")
        
        # 导入所有历史会话
        _send_message("")
        _send_message("正在导入历史会话...")
        count = await _import_all_sessions(service)
        
        if count > 0:
            _send_message(f"已导入 {count} 个历史会话")
        else:
            _send_message("没有找到需要导入的历史会话")
        
        _send_message("")
        _send_message("记忆系统已就绪! 新对话将自动保存。")
        
        service.close()
        
    except Exception as e:
        _send_message(f"错误: {e}")


async def _import_current_session(soul, service: MemoryService) -> int:
    """导入当前会话的历史消息到记忆系统。
    
    Returns:
        导入的消息数量
    """
    try:
        # 获取当前会话ID
        session_id = ""
        if hasattr(soul, 'context') and soul.context:
            session_id = getattr(soul.context, 'session_id', '')
        
        if not session_id:
            return 0
        
        # 检查是否已存在
        if service.get_session(session_id):
            return 0
        
        # 获取当前会话的历史消息
        history = getattr(soul.context, 'history', [])
        if not history:
            return 0
        
        # 创建会话
        from kimi_cli.memory.models.data import Session, Message
        
        # 生成标题（使用第一条用户消息）
        title = None
        for msg in history:
            if msg.role == "user":
                content = msg.content
                if isinstance(content, list):
                    texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    content = " ".join(texts)
                title = (content[:50] + "...") if len(content) > 50 else content
                break
        
        if not title:
            title = f"Session {session_id[:8]}"
        
        session = Session(
            id=session_id,
            title=title,
            work_dir=str(Path.cwd()),
        )
        service.storage.create_session(session)
        
        # 导入消息
        imported_count = 0
        total_tokens = 0
        for msg in history:
            if msg.role not in ("user", "assistant"):
                continue
            
            # 提取内容
            content = msg.content
            if isinstance(content, list):
                texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                content = " ".join(texts)
            elif not isinstance(content, str):
                content = str(content)
            
            if not content.strip():
                continue
            
            message = Message(
                session_id=session_id,
                role=msg.role,
                content=content,
                token_count=len(content) // 4,  # 粗略估计
            )
            service.storage.add_message(message)
            imported_count += 1
            total_tokens += message.token_count
        
        # 更新会话token数
        session.token_count = total_tokens
        service.storage.update_session(session)
        
        # 触发索引
        try:
            service._index_manager.index_session(session_id)
        except Exception:
            pass
        
        return imported_count
        
    except Exception:
        return 0


async def _import_all_sessions(service: MemoryService) -> int:
    """导入所有历史会话到记忆系统。
    
    Returns:
        导入的会话数量
    """
    try:
        from kimi_cli.memory.utils.importer import SessionImporter
        
        importer = SessionImporter(service)
        stats = importer.import_all(dry_run=False)
        
        return stats.get('imported', 0)
    except Exception:
        return 0


async def _cmd_status():
    """状态命令"""
    service = MemoryService()
    if not service.initialize():
        _send_message("""
记忆系统未初始化

请运行: /memory init
""")
        return
    
    try:
        stats = service.get_stats()
        config = service.config
        
        lines = [
            "记忆系统状态",
            "",
            f"存储后端: {config.storage.backend}",
            f"数据库路径: {config.storage.db_path}",
            f"Embedding: {config.embedding.provider}",
            f"Embedding维度: {config.embedding.dimensions}",
            "",
            "统计信息:",
            f"  总会话: {stats.get('total_sessions', 0)}",
            f"  总消息: {stats.get('total_messages', 0)}",
            f"  总Token: {stats.get('total_tokens', 0):,}",
            f"  向量支持: {'是' if stats.get('vec_available') else '否'}",
        ]
        
        if 'indexed_vectors' in stats:
            lines.append(f"  已索引: {stats['indexed_vectors']}")
        
        _send_message("\n".join(lines))
        
    finally:
        service.close()


async def _cmd_index(soul):
    """索引当前会话"""
    service = MemoryService()
    if not service.initialize():
        _send_message("请先运行 /memory init")
        return
    
    try:
        # 获取当前会话ID
        session_id = ""
        if hasattr(soul, 'context') and soul.context:
            session_id = getattr(soul.context, 'session_id', '')
        
        if not session_id:
            _send_message("无法获取当前会话ID")
            return
        
        _send_message(f"正在索引会话: {session_id[:8]}...")
        
        if service.index_session(session_id, force=True):
            _send_message("索引完成")
        else:
            _send_message("索引失败或会话不存在")
            
    finally:
        service.close()


async def _cmd_index_all():
    """批量索引"""
    service = MemoryService()
    if not service.initialize():
        _send_message("请先运行 /memory init")
        return
    
    try:
        _send_message("正在批量索引会话...")
        
        count = service.batch_index(limit=100)
        
        _send_message(f"已索引 {count} 个会话")
        
    finally:
        service.close()


async def _cmd_import(soul, dry_run: bool):
    """导入历史会话命令"""
    from kimi_cli.memory.utils.importer import SessionImporter
    
    service = MemoryService()
    if not service.initialize():
        _send_message("请先运行 /memory init")
        return
    
    try:
        _send_message("正在导入历史会话...")
        
        importer = SessionImporter(service)
        stats = importer.import_all(dry_run=dry_run)
        
        # 显示报告
        report = importer.generate_report()
        _send_message(report)
        
    finally:
        service.close()


async def _cmd_eval(soul):
    """评估召回效果命令"""
    from kimi_cli.memory.utils.evaluator import RecallEvaluator
    from pathlib import Path
    
    service = MemoryService()
    if not service.initialize():
        _send_message("请先运行 /memory init")
        return
    
    try:
        _send_message("正在运行召回效果评估...")
        
        evaluator = RecallEvaluator(service)
        
        # 自动生成测试用例
        _send_message("从现有会话生成测试用例...")
        test_cases = evaluator.auto_generate_tests(num_tests=10)
        _send_message(f"生成了 {len(test_cases)} 个测试用例")
        
        # 运行评估
        _send_message("执行召回测试...")
        report = evaluator.run_evaluation(top_k=5)
        
        # 保存报告
        output_dir = Path.home() / ".kimi" / "memory" / "evaluations"
        json_path, md_path = evaluator.save_report(report, str(output_dir))
        
        # 显示结果摘要
        summary = f"""
评估结果摘要

总体指标:
  Top-1 准确率: {report.top1_accuracy:.2%}
  Top-3 准确率: {report.top3_accuracy:.2%}
  Top-5 准确率: {report.top5_accuracy:.2%}
  平均 MRR: {report.mean_mrr:.4f}

详细报告已保存:
  JSON: {json_path}
  Markdown: {md_path}

使用 `/recall` 体验记忆召回功能
"""
        _send_message(summary)
        
    finally:
        service.close()


async def _cmd_config(edit_mode: bool):
    """配置命令"""
    config_path = Path.home() / ".kimi" / "memory" / "config.json"
    
    if edit_mode:
        _send_message(f"""
编辑配置文件

路径: {config_path}

请使用编辑器修改后保存, 然后重启 Kimi.

常用配置项:
- storage.db_path: 数据库路径
- embedding.provider: embedding 提供者 (local_onnx/mock)
- recall.auto_recall_enabled: 自动召回开关
- recall.max_results: 最大召回数量
""")
        return
    
    # 显示配置
    if not config_path.exists():
        _send_message("配置文件不存在, 请先运行 /memory init")
        return
    
    try:
        with open(config_path, 'r') as f:
            content = f.read()
        
        _send_message(f"""
当前配置 ({config_path}):

```json
{content}
```

使用 `/memory config --edit` 查看编辑说明
""")
    except Exception as e:
        _send_message(f"读取配置失败: {e}")


__all__ = ["memory_command"]
