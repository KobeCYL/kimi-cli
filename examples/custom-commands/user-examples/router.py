"""
智能模型路由系统 - 根据对话特征自动选择最优模型

目标：用最小的 token 做出最好的效果
"""

import json
import re
from typing import Literal

# 模型配置 - 按能力和成本排序
MODELS = {
    "fast": {
        "name": "kimi-code/kimi-for-coding",
        "description": "快速响应模型 - 适合简单问答、代码补全、日常对话",
        "strengths": ["快速", "代码", "日常对话"],
        "cost_level": "低",
        "max_context": 262144,
        "speed": "快",
    },
    "balanced": {
        "name": "deepseek",
        "description": "平衡模型 - 适合中等复杂度任务、推理",
        "strengths": ["推理", "分析", "中等复杂度"],
        "cost_level": "中",
        "max_context": 64000,
        "speed": "中等",
    },
    "powerful": {
        "name": "glm5",
        "description": "强力模型 - 适合复杂任务、长文本、深度分析",
        "strengths": ["长上下文", "复杂推理", "深度分析"],
        "cost_level": "中高",
        "max_context": 128000,
        "speed": "较慢",
    },
    "expert": {
        "name": "claude-sonnet",
        "description": "专家模型 - 适合高难度代码、复杂架构设计",
        "strengths": ["高难度代码", "架构设计", "复杂调试"],
        "cost_level": "高",
        "max_context": 200000,
        "speed": "慢",
    },
}


def analyze_context(soul) -> dict:
    """分析当前对话上下文特征"""
    from kimi_cli.wire.types import TextPart
    
    analysis = {
        "message_count": 0,
        "total_chars": 0,
        "code_blocks": 0,
        "complexity_score": 0,
        "has_images": False,
        "has_video": False,
        "topics": [],
    }
    
    try:
        ctx = soul.context
        history = ctx.history if hasattr(ctx, 'history') else []
        
        analysis["message_count"] = len(history)
        
        # 分析最近的消息
        recent_messages = history[-10:] if len(history) > 10 else history
        
        code_pattern = r'```[\s\S]*?```'
        complexity_keywords = [
            '架构', '设计', '优化', '重构', '性能', '并发', '分布式',
            'architecture', 'design', 'optimize', 'refactor', 'performance', 
            'concurrent', 'distributed', 'microservice', 'kubernetes', 'docker'
        ]
        simple_keywords = [
            '你好', 'hello', 'hi', '谢谢', '请问', '简单', '快速',
            'how to', 'what is', 'help', 'quick'
        ]
        
        for msg in recent_messages:
            if hasattr(msg, 'content'):
                content = str(msg.content)
                analysis["total_chars"] += len(content)
                
                # 统计代码块
                analysis["code_blocks"] += len(re.findall(code_pattern, content))
                
                # 复杂度评分
                content_lower = content.lower()
                for keyword in complexity_keywords:
                    if keyword.lower() in content_lower:
                        analysis["complexity_score"] += 2
                for keyword in simple_keywords:
                    if keyword.lower() in content_lower:
                        analysis["complexity_score"] -= 1
                
                # 检测媒体
                if '[image:' in content or 'image_url' in content:
                    analysis["has_images"] = True
                if '[video:' in content or 'video_url' in content:
                    analysis["has_video"] = True
                    
    except Exception as e:
        pass
    
    return analysis


def recommend_model(analysis: dict) -> tuple[str, str]:
    """根据分析结果推荐模型"""
    
    score = analysis["complexity_score"]
    code_blocks = analysis["code_blocks"]
    message_count = analysis["message_count"]
    total_chars = analysis["total_chars"]
    has_media = analysis["has_images"] or analysis["has_video"]
    
    # 路由决策逻辑
    if score >= 5 or code_blocks >= 3 or total_chars > 50000:
        return "expert", "高难度任务，需要专家模型"
    elif score >= 3 or code_blocks >= 2 or total_chars > 20000:
        return "powerful", "复杂任务，需要强力模型"
    elif score <= 0 and code_blocks == 0 and message_count < 5 and not has_media:
        return "fast", "简单对话，快速模型即可"
    else:
        return "balanced", "中等复杂度，平衡模型最适合"


@soul_command(aliases=["r", "switch"])
async def route(soul, args: str):
    """
    🚀 智能模型路由 - 自动分析对话并推荐最优模型
    
    用法:
    /route              - 分析当前对话并推荐模型
    /route auto         - 自动切换到推荐模型
    /route fast         - 切换到快速模型
    /route balanced     - 切换到平衡模型  
    /route powerful     - 切换到强力模型
    /route expert       - 切换到专家模型
    /route list         - 列出所有可用模型
    """
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    args = args.strip().lower()
    
    # 列出所有模型
    if args == "list":
        wire_send(TextPart(text="📋 可用模型列表:\n"))
        for key, model in MODELS.items():
            wire_send(TextPart(
                text=f"\n[bold]/{key}[/bold] - {model['name']}\n"
                f"  描述: {model['description']}\n"
                f"  优势: {', '.join(model['strengths'])}\n"
                f"  成本: {model['cost_level']} | 速度: {model['speed']}\n"
            ))
        return
    
    # 直接切换模型
    if args in MODELS:
        model_key = args
        model_info = MODELS[model_key]
        
        wire_send(TextPart(
            text=f"🔄 正在切换到 [bold]{model_key}[/bold] 模型...\n"
            f"模型: {model_info['name']}\n"
            f"{model_info['description']}"
        ))
        
        # 执行模型切换
        await _switch_model(soul, model_info['name'])
        return
    
    # 自动分析并推荐
    if args in ["", "auto", "analyze"]:
        wire_send(TextPart(text="🔍 正在分析当前对话特征...\n"))
        
        analysis = analyze_context(soul)
        recommended_key, reason = recommend_model(analysis)
        recommended = MODELS[recommended_key]
        
        # 构建分析报告
        report = f"""
📊 [bold]对话分析报告[/bold]

上下文统计:
  • 消息数: {analysis['message_count']}
  • 总字符: {analysis['total_chars']:,}
  • 代码块: {analysis['code_blocks']}
  • 复杂度评分: {analysis['complexity_score']}
  • 包含媒体: {'是' if analysis['has_images'] or analysis['has_video'] else '否'}

🎯 [bold]推荐模型: {recommended_key.upper()}[/bold]
   模型: {recommended['name']}
   原因: {reason}
   
   描述: {recommended['description']}
   优势: {', '.join(recommended['strengths'])}
   成本: {recommended['cost_level']} | 速度: {recommended['speed']}

💡 操作提示:
   • 输入 /route auto 自动切换
   • 输入 /route {recommended_key} 手动切换
   • 输入 /route list 查看所有模型
"""
        wire_send(TextPart(text=report))
        
        if args == "auto":
            wire_send(TextPart(text=f"\n🔄 自动切换到 {recommended_key} 模型..."))
            await _switch_model(soul, recommended['name'])
        return
    
    # 未知参数，显示帮助
    wire_send(TextPart(text="""
❓ 未知命令

用法:
  /route              - 分析并推荐模型
  /route auto         - 自动切换
  /route fast         - 快速模型
  /route balanced     - 平衡模型
  /route powerful     - 强力模型
  /route expert       - 专家模型
  /route list         - 列出模型
"""))


async def _switch_model(soul, model_name: str):
    """切换模型的内部实现"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    from kimi_cli.config import load_config, save_config
    
    try:
        # 这里我们需要调用 kimi 的 model 切换逻辑
        # 由于我们无法直接调用内部方法，我们通过消息提示用户
        wire_send(TextPart(
            text=f"""
✅ 请手动切换模型:

输入以下命令:
  /model

然后在菜单中选择: [bold]{model_name}[/bold]

💡 提示: 你也可以直接编辑 ~/.kimi/config.toml 修改 default_model
"""
        ))
    except Exception as e:
        wire_send(TextPart(text=f"❌ 切换失败: {e}"))


@shell_command(aliases=["models"])
def route_list(shell, args: str):
    """📋 列出所有可用路由模型（Shell 层）"""
    from kimi_cli.ui.shell.console import console
    
    console.print("\n[bold blue]🚀 智能路由模型列表[/bold blue]\n")
    
    table_data = []
    for key, model in MODELS.items():
        table_data.append([
            f"[bold cyan]/{key}[/bold cyan]",
            model['name'],
            model['description'][:40] + "..." if len(model['description']) > 40 else model['description'],
            f"[green]{model['cost_level']}[/green]",
            f"[yellow]{model['speed']}[/yellow]",
        ])
    
    from rich.table import Table
    table = Table(title="模型对比")
    table.add_column("命令", style="cyan")
    table.add_column("模型名", style="white")
    table.add_column("描述", style="dim")
    table.add_column("成本", style="green")
    table.add_column("速度", style="yellow")
    
    for row in table_data:
        table.add_row(*row)
    
    console.print(table)
    
    console.print("\n[dim]💡 使用 /route [模型名] 快速切换[/dim]")
    console.print("[dim]💡 使用 /route 分析当前对话并推荐模型[/dim]\n")
