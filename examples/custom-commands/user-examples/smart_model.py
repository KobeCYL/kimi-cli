"""
智能模型切换 - 基于对话复杂度自动选择最优模型
"""

import re
from pathlib import Path


def analyze_conversation(soul) -> dict:
    """深度分析对话特征"""
    analysis = {
        "total_tokens": 0,
        "code_blocks": 0,
        "complexity_indicators": [],
        "is_simple_chat": False,
        "needs_reasoning": False,
        "needs_long_context": False,
    }
    
    try:
        ctx = soul.context
        if hasattr(ctx, 'token_count'):
            analysis["total_tokens"] = ctx.token_count
            analysis["needs_long_context"] = ctx.token_count > 30000
        
        history = ctx.history if hasattr(ctx, 'history') else []
        
        # 分析最近 5 轮对话
        recent = history[-5:] if len(history) > 5 else history
        content_text = " ".join([str(m.content) for m in recent if hasattr(m, 'content')])
        
        # 代码块检测
        analysis["code_blocks"] = len(re.findall(r'```[\s\S]*?```', content_text))
        
        # 复杂度指标
        complex_patterns = [
            (r'\b(架构|设计模式|重构|优化|性能调优|算法|数据结构)\b', '架构设计'),
            (r'\b(微服务|分布式|并发|多线程|K8s|Docker|Kubernetes)\b', '系统架构'),
            (r'\b(debug|调试|排查|定位|解决).*?(bug|错误|异常|内存泄漏)', '复杂调试'),
            (r'\b(深度学习|机器学习|AI|模型训练|神经网络)\b', 'AI/ML'),
            (r'\b(安全|加密|漏洞|攻击|防护|认证|授权)\b', '安全领域'),
        ]
        
        for pattern, label in complex_patterns:
            if re.search(pattern, content_text, re.IGNORECASE):
                analysis["complexity_indicators"].append(label)
                analysis["needs_reasoning"] = True
        
        # 简单对话检测
        simple_patterns = [
            r'^(你好|您好|hello|hi|hey)\s*$',
            r'^(谢谢|感谢|thanks|thank you)\s*$',
            r'^(再见|拜拜|bye|goodbye)\s*$',
            r'^( help|帮助|请问).*?\?*$',
        ]
        for pattern in simple_patterns:
            if re.search(pattern, content_text, re.IGNORECASE):
                analysis["is_simple_chat"] = True
                break
                
    except Exception:
        pass
    
    return analysis


def get_model_recommendation(analysis: dict) -> dict:
    """根据分析结果给出模型建议"""
    
    # 决策矩阵
    if analysis["is_simple_chat"] and analysis["total_tokens"] < 5000:
        return {
            "model": "kimi-code/kimi-for-coding",
            "reason": "简单对话，使用快速响应模型节省成本",
            "level": "fast",
            "action": "当前模型已合适",
        }
    
    if analysis["complexity_indicators"]:
        indicators = ", ".join(analysis["complexity_indicators"])
        if len(analysis["complexity_indicators"]) >= 2 or analysis["needs_long_context"]:
            return {
                "model": "deepseek",  # 或者 glm5
                "reason": f"检测到复杂需求: {indicators}",
                "level": "powerful",
                "action": "建议切换到推理能力更强的模型",
            }
        else:
            return {
                "model": "deepseek",
                "reason": f"检测到专业领域: {indicators}",
                "level": "balanced",
                "action": "可使用平衡模型",
            }
    
    if analysis["code_blocks"] >= 2 or analysis["total_tokens"] > 15000:
        return {
            "model": "deepseek",
            "reason": "代码量大或上下文较长",
            "level": "balanced",
            "action": "建议使用平衡模型",
        }
    
    return {
        "model": "kimi-code/kimi-for-coding",
        "reason": "常规开发任务",
        "level": "current",
        "action": "当前模型已合适",
    }


@soul_command
async def smart_model(soul, args: str):
    """
    🧠 智能模型分析 - 分析对话并给出最优模型建议
    
    自动检测:
    - 对话复杂度
    - 代码量
    - 专业领域
    - Token 使用情况
    
    用法: /smart_model
    """
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    wire_send(TextPart(text="🧠 正在分析对话特征...\n"))
    
    analysis = analyze_conversation(soul)
    recommendation = get_model_recommendation(analysis)
    
    # 获取当前模型
    current_model = "Unknown"
    try:
        if soul.runtime.llm and soul.runtime.llm.chat_provider:
            current_model = soul.runtime.llm.chat_provider.model_name
    except:
        pass
    
    # 构建报告
    report_lines = [
        "📊 [bold]智能分析报告[/bold]",
        "",
        "当前状态:",
        f"  当前模型: {current_model}",
        f"  Token 使用: {analysis['total_tokens']:,}",
        f"  代码块数: {analysis['code_blocks']}",
    ]
    
    if analysis["complexity_indicators"]:
        report_lines.append(f"  检测领域: {', '.join(analysis['complexity_indicators'])}")
    
    report_lines.extend([
        "",
        "🎯 [bold]优化建议[/bold]",
        f"  推荐模型: [cyan]{recommendation['model']}[/cyan]",
        f"  推荐级别: {recommendation['level']}",
        f"  分析原因: {recommendation['reason']}",
        f"  建议操作: [yellow]{recommendation['action']}[/yellow]",
        "",
    ])
    
    # 如果建议切换模型
    if recommendation['level'] != 'current':
        report_lines.extend([
            "💡 [bold]快速切换[/bold]",
            f"  输入: /use {recommendation['level']}",
            "",
            "可用快捷命令:",
            "  /use fast     → 快速模型 (日常对话)",
            "  /use balanced → 平衡模型 (一般开发)",
            "  /use powerful → 强力模型 (复杂任务)",
        ])
    else:
        report_lines.append("✅ 当前配置已是最优")
    
    wire_send(TextPart(text="\n".join(report_lines)))


@soul_command
async def use(soul, args: str):
    """
    ⚡ 快速切换模型预设
    
    用法:
    /use fast      - 切换到快速模型
    /use balanced  - 切换到平衡模型  
    /use powerful  - 切换到强力模型
    /use default   - 恢复默认模型
    """
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    preset = args.strip().lower()
    
    # 模型预设映射
    presets = {
        "fast": ("kimi-code/kimi-for-coding", "快速响应模式"),
        "balanced": ("deepseek", "平衡性能模式"),
        "powerful": ("glm5", "强力推理模式"),
        "default": ("kimi-code/kimi-for-coding", "默认模式"),
    }
    
    if preset not in presets:
        wire_send(TextPart(text="""
❓ 未知预设

可用预设:
  /use fast     - 快速模型 (kimi-for-coding)
  /use balanced - 平衡模型 (deepseek)
  /use powerful - 强力模型 (glm5)
  /use default  - 恢复默认
"""))
        return
    
    model_name, mode_desc = presets[preset]
    
    wire_send(TextPart(
        text=f"""
🔄 准备切换到 [bold]{preset}[/bold] 模式
   模型: {model_name}
   模式: {mode_desc}

⚠️  请手动执行切换:

1. 输入: /model
2. 选择: {model_name}

或者编辑配置文件:
  ~/.kimi/config.toml
  修改 default_model = "{model_name}"
"""
    ))
