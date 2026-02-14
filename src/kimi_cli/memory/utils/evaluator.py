"""召回效果评估工具

用于测试和评估记忆系统的召回质量
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import RecallResult, Session


@dataclass
class TestCase:
    """召回测试用例"""
    query: str
    expected_session_ids: List[str]
    description: str
    category: str  # "keyword", "semantic", "hybrid"


@dataclass
class TestResult:
    """测试结果"""
    test_case: TestCase
    recall_results: List[RecallResult]
    
    # 指标
    top1_hit: bool = False
    top3_hit: bool = False
    top5_hit: bool = False
    mrr: float = 0.0  # Mean Reciprocal Rank
    
    def calculate_metrics(self):
        """计算评估指标"""
        result_ids = [r.session.id for r in self.recall_results]
        
        for i, result_id in enumerate(result_ids):
            if result_id in self.test_case.expected_session_ids:
                rank = i + 1
                if rank == 1:
                    self.top1_hit = True
                if rank <= 3:
                    self.top3_hit = True
                if rank <= 5:
                    self.top5_hit = True
                self.mrr = 1.0 / rank
                break


@dataclass
class EvaluationReport:
    """评估报告"""
    total_tests: int
    top1_accuracy: float
    top3_accuracy: float
    top5_accuracy: float
    mean_mrr: float
    by_category: Dict[str, Dict[str, float]]
    details: List[TestResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tests": self.total_tests,
            "top1_accuracy": self.top1_accuracy,
            "top3_accuracy": self.top3_accuracy,
            "top5_accuracy": self.top5_accuracy,
            "mean_mrr": self.mean_mrr,
            "by_category": self.by_category,
            "timestamp": datetime.now().isoformat(),
        }
    
    def to_markdown(self) -> str:
        """生成 Markdown 报告"""
        lines = [
            "# Memory Recall Evaluation Report",
            "",
            f"**Test Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Total Tests**: {self.total_tests}",
            "",
            "## Overall Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Top-1 Accuracy | {self.top1_accuracy:.2%} |",
            f"| Top-3 Accuracy | {self.top3_accuracy:.2%} |",
            f"| Top-5 Accuracy | {self.top5_accuracy:.2%} |",
            f"| Mean MRR | {self.mean_mrr:.4f} |",
            "",
            "## By Category",
            "",
            "| Category | Top-1 | Top-3 | Top-5 | MRR |",
            "|----------|-------|-------|-------|-----|",
        ]
        
        for cat, metrics in self.by_category.items():
            lines.append(
                f"| {cat} | {metrics['top1']:.2%} | {metrics['top3']:.2%} | "
                f"{metrics['top5']:.2%} | {metrics['mrr']:.4f} |"
            )
        
        lines.extend([
            "",
            "## Failed Cases",
            "",
        ])
        
        failed = [r for r in self.details if not r.top5_hit]
        if failed:
            for i, result in enumerate(failed[:10], 1):
                lines.extend([
                    f"### {i}. {result.test_case.description}",
                    "",
                    f"- **Query**: `{result.test_case.query}`",
                    f"- **Expected**: {result.test_case.expected_session_ids}",
                    f"- **Got**: {[r.session.id for r in result.recall_results]}",
                    "",
                ])
        else:
            lines.append("🎉 All tests passed!")
        
        return "\n".join(lines)


class RecallEvaluator:
    """召回效果评估器"""
    
    def __init__(self, service: MemoryService):
        self.service = service
        self.test_cases: List[TestCase] = []
    
    def load_test_cases(self, path: Optional[str] = None) -> int:
        """加载测试用例
        
        如果未提供路径，则生成默认测试用例
        """
        if path and Path(path).exists():
            with open(path, 'r') as f:
                data = json.load(f)
                self.test_cases = [
                    TestCase(**item) for item in data
                ]
        else:
            self.test_cases = self._generate_default_test_cases()
        
        return len(self.test_cases)
    
    def _generate_default_test_cases(self) -> List[TestCase]:
        """生成默认测试用例"""
        return [
            # 关键词测试
            TestCase(
                query="微服务架构设计",
                expected_session_ids=[],
                description="关键词匹配测试",
                category="keyword"
            ),
            TestCase(
                query="Redis 缓存优化",
                expected_session_ids=[],
                description="技术关键词测试",
                category="keyword"
            ),
            # 语义测试
            TestCase(
                query="怎么让系统跑得更快",
                expected_session_ids=[],
                description="语义理解测试 (性能优化)",
                category="semantic"
            ),
            TestCase(
                query="数据库总是连不上",
                expected_session_ids=[],
                description="语义理解测试 (连接问题)",
                category="semantic"
            ),
            # 混合测试
            TestCase(
                query="Python 多线程性能问题",
                expected_session_ids=[],
                description="混合查询测试",
                category="hybrid"
            ),
        ]
    
    def auto_generate_tests(self, num_tests: int = 10) -> List[TestCase]:
        """从现有会话自动生成测试用例"""
        sessions = self.service.storage.list_sessions(limit=100)
        
        if len(sessions) < num_tests:
            num_tests = len(sessions)
        
        # 随机选择会话作为测试目标
        selected = random.sample(sessions, num_tests)
        
        test_cases = []
        for session in selected:
            # 获取会话的消息
            messages = self.service.storage.get_messages(session.id, limit=5)
            if not messages:
                continue
            
            # 使用第一条用户消息作为查询
            user_messages = [m for m in messages if m.role == "user"]
            if not user_messages:
                continue
            
            query = user_messages[0].content[:50]  # 取前50字符
            
            test_cases.append(TestCase(
                query=query,
                expected_session_ids=[session.id],
                description=f"Auto-generated from session {session.id[:8]}",
                category="auto"
            ))
        
        self.test_cases = test_cases
        return test_cases
    
    def run_evaluation(self, top_k: int = 5) -> EvaluationReport:
        """运行评估"""
        results: List[TestResult] = []
        
        for test_case in self.test_cases:
            # 执行召回
            recall_results = self.service.recall(
                context_text=test_case.query,
                current_session_id=None,
                top_k=top_k,
            )
            
            # 记录结果
            result = TestResult(
                test_case=test_case,
                recall_results=recall_results
            )
            result.calculate_metrics()
            results.append(result)
        
        # 计算总体指标
        total = len(results)
        if total == 0:
            return EvaluationReport(
                total_tests=0,
                top1_accuracy=0,
                top3_accuracy=0,
                top5_accuracy=0,
                mean_mrr=0,
                by_category={},
                details=[]
            )
        
        top1_hits = sum(1 for r in results if r.top1_hit)
        top3_hits = sum(1 for r in results if r.top3_hit)
        top5_hits = sum(1 for r in results if r.top5_hit)
        mean_mrr = sum(r.mrr for r in results) / total
        
        # 按分类统计
        by_category: Dict[str, List[TestResult]] = {}
        for r in results:
            cat = r.test_case.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(r)
        
        by_category_metrics = {}
        for cat, cat_results in by_category.items():
            cat_total = len(cat_results)
            by_category_metrics[cat] = {
                "top1": sum(1 for r in cat_results if r.top1_hit) / cat_total,
                "top3": sum(1 for r in cat_results if r.top3_hit) / cat_total,
                "top5": sum(1 for r in cat_results if r.top5_hit) / cat_total,
                "mrr": sum(r.mrr for r in cat_results) / cat_total,
            }
        
        return EvaluationReport(
            total_tests=total,
            top1_accuracy=top1_hits / total,
            top3_accuracy=top3_hits / total,
            top5_accuracy=top5_hits / total,
            mean_mrr=mean_mrr,
            by_category=by_category_metrics,
            details=results
        )
    
    def save_report(self, report: EvaluationReport, output_dir: str):
        """保存评估报告"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存 JSON
        json_path = output_path / f"evaluation_{timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        # 保存 Markdown
        md_path = output_path / f"evaluation_{timestamp}.md"
        with open(md_path, 'w') as f:
            f.write(report.to_markdown())
        
        return json_path, md_path
