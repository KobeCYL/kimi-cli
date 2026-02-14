"""/memory 管理命令实现"""

from __future__ import annotations

import json
from pathlib import Path

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import MemoryConfig


async def memory_command(soul, args: str):
    """
    💾 记忆系统管理
    
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
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    args = args.strip()
    parts = args.split()
    subcmd = parts[0] if parts else "status"
    
    if subcmd == "init":
        await _cmd_init()
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
        wire_send(TextPart(text=f"""
💾 Memory 管理命令

用法:
  /memory init          - 初始化记忆系统
  /memory status        - 显示状态和统计
  /memory index         - 索引当前会话
  /memory index-all     - 批量索引所有会话
  /memory config        - 查看配置
  /memory config --edit - 编辑配置

当前工作目录: {Path.cwd()}
配置目录: ~/.kimi/memory/
"""))


async def _cmd_init():
    """初始化命令"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    wire_send(TextPart(text="🚀 初始化记忆系统..."))
    
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
        if service.initialize():
            wire_send(TextPart(text=f"""
✅ 记忆系统初始化成功！

配置目录: {memory_dir}
数据库: {config.storage.db_path}

下次启动 Kimi 时会自动加载记忆系统。
"""))
        else:
            wire_send(TextPart(text="❌ 初始化失败"))
        
        service.close()
        
    except Exception as e:
        wire_send(TextPart(text=f"❌ 错误: {e}"))


async def _cmd_status():
    """状态命令"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    service = MemoryService()
    if not service.initialize():
        wire_send(TextPart(text="""
⚠️ 记忆系统未初始化

请运行：/memory init
"""))
        return
    
    try:
        stats = service.get_stats()
        config = service.config
        
        lines = [
            "📊 记忆系统状态",
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
            f"  向量支持: {'✅' if stats.get('vec_available') else '❌'}",
        ]
        
        if 'indexed_vectors' in stats:
            lines.append(f"  已索引: {stats['indexed_vectors']}")
        
        wire_send(TextPart(text="\n".join(lines)))
        
    finally:
        service.close()


async def _cmd_index(soul):
    """索引当前会话"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    service = MemoryService()
    if not service.initialize():
        wire_send(TextPart(text="⚠️ 请先运行 /memory init"))
        return
    
    try:
        # 获取当前会话ID
        session_id = ""
        if hasattr(soul, 'context') and soul.context:
            session_id = getattr(soul.context, 'session_id', '')
        
        if not session_id:
            wire_send(TextPart(text="⚠️ 无法获取当前会话ID"))
            return
        
        wire_send(TextPart(text=f"🔄 正在索引会话: {session_id[:8]}..."))
        
        if service.index_session(session_id, force=True):
            wire_send(TextPart(text="✅ 索引完成"))
        else:
            wire_send(TextPart(text="⚠️ 索引失败或会话不存在"))
            
    finally:
        service.close()


async def _cmd_index_all():
    """批量索引"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    service = MemoryService()
    if not service.initialize():
        wire_send(TextPart(text="⚠️ 请先运行 /memory init"))
        return
    
    try:
        wire_send(TextPart(text="🔄 正在批量索引会话..."))
        
        count = service.batch_index(limit=100)
        
        wire_send(TextPart(text=f"✅ 已索引 {count} 个会话"))
        
    finally:
        service.close()


async def _cmd_import(soul, dry_run: bool):
    """导入历史会话命令"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    from kimi_cli.memory.utils.importer import SessionImporter
    
    service = MemoryService()
    if not service.initialize():
        wire_send(TextPart(text="⚠️ 请先运行 /memory init"))
        return
    
    try:
        wire_send(TextPart(text="🔄 正在导入历史会话..."))
        
        importer = SessionImporter(service)
        stats = importer.import_all(dry_run=dry_run)
        
        # 显示报告
        report = importer.generate_report()
        wire_send(TextPart(text=report))
        
    finally:
        service.close()


async def _cmd_eval(soul):
    """评估召回效果命令"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    from kimi_cli.memory.utils.evaluator import RecallEvaluator
    from pathlib import Path
    
    service = MemoryService()
    if not service.initialize():
        wire_send(TextPart(text="⚠️ 请先运行 /memory init"))
        return
    
    try:
        wire_send(TextPart(text="🧪 正在运行召回效果评估..."))
        
        evaluator = RecallEvaluator(service)
        
        # 自动生成测试用例
        wire_send(TextPart(text="📋 从现有会话生成测试用例..."))
        test_cases = evaluator.auto_generate_tests(num_tests=10)
        wire_send(TextPart(text=f"✅ 生成了 {len(test_cases)} 个测试用例"))
        
        # 运行评估
        wire_send(TextPart(text="🔍 执行召回测试..."))
        report = evaluator.run_evaluation(top_k=5)
        
        # 保存报告
        output_dir = Path.home() / ".kimi" / "memory" / "evaluations"
        json_path, md_path = evaluator.save_report(report, str(output_dir))
        
        # 显示结果摘要
        summary = f"""
📊 评估结果摘要

总体指标:
  Top-1 准确率: {report.top1_accuracy:.2%}
  Top-3 准确率: {report.top3_accuracy:.2%}
  Top-5 准确率: {report.top5_accuracy:.2%}
  平均 MRR: {report.mean_mrr:.4f}

详细报告已保存:
  JSON: {json_path}
  Markdown: {md_path}

💡 使用 `/recall` 体验记忆召回功能
"""
        wire_send(TextPart(text=summary))
        
    finally:
        service.close()


async def _cmd_config(edit_mode: bool):
    """配置命令"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    config_path = Path.home() / ".kimi" / "memory" / "config.json"
    
    if edit_mode:
        wire_send(TextPart(text=f"""
📝 编辑配置文件

路径: {config_path}

请使用编辑器修改后保存，然后重启 Kimi。

常用配置项:
- storage.db_path: 数据库路径
- embedding.provider: embedding 提供者 (local_onnx/mock)
- recall.auto_recall_enabled: 自动召回开关
- recall.max_results: 最大召回数量
"""))
        return
    
    # 显示配置
    if not config_path.exists():
        wire_send(TextPart(text="⚠️ 配置文件不存在，请先运行 /memory init"))
        return
    
    try:
        with open(config_path, 'r') as f:
            content = f.read()
        
        wire_send(TextPart(text=f"""
📄 当前配置 ({config_path}):

```json
{content}
```

使用 `/memory config --edit` 查看编辑说明
"""))
    except Exception as e:
        wire_send(TextPart(text=f"❌ 读取配置失败: {e}"))


__all__ = ["memory_command"]
