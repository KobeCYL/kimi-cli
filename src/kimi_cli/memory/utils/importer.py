"""Kimi CLI 会话历史导入工具

将 Kimi CLI 现有的会话历史导入到 Memory 系统
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from kimi_cli.memory.services.memory_service import MemoryService
from kimi_cli.memory.models.data import Session, Message


class SessionImporter:
    """会话历史导入器
    
    从 Kimi CLI 的会话存储中导入历史对话到 Memory 系统
    """
    
    def __init__(self, service: MemoryService):
        self.service = service
        self.stats = {
            "total_sessions": 0,
            "imported_sessions": 0,
            "skipped_sessions": 0,
            "total_messages": 0,
            "imported_messages": 0,
            "errors": [],
        }
    
    def import_all(
        self,
        kimi_sessions_dir: Optional[str] = None,
        dry_run: bool = False,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """导入所有会话
        
        Args:
            kimi_sessions_dir: Kimi CLI 会话目录，默认 ~/.kimi/sessions
            dry_run: 试运行模式，不实际写入
            skip_existing: 跳过已存在的会话
            
        Returns:
            导入统计信息
        """
        if kimi_sessions_dir is None:
            kimi_sessions_dir = Path.home() / ".kimi" / "sessions"
        else:
            kimi_sessions_dir = Path(kimi_sessions_dir)
        
        if not kimi_sessions_dir.exists():
            self.stats["errors"].append(f"Sessions directory not found: {kimi_sessions_dir}")
            return self.stats
        
        # 遍历所有工作目录
        for work_dir_hash in kimi_sessions_dir.iterdir():
            if not work_dir_hash.is_dir():
                continue
            
            self._import_work_dir(work_dir_hash, dry_run, skip_existing)
        
        return self.stats
    
    def _import_work_dir(
        self, 
        work_dir_path: Path, 
        dry_run: bool,
        skip_existing: bool
    ):
        """导入单个工作目录的会话"""
        work_dir = str(work_dir_path)
        
        # 每个会话是一个子目录
        for session_dir in work_dir_path.iterdir():
            if not session_dir.is_dir():
                continue
            
            self.stats["total_sessions"] += 1
            session_id = session_dir.name
            
            try:
                # 检查是否已存在
                if skip_existing and self.service.get_session(session_id):
                    self.stats["skipped_sessions"] += 1
                    continue
                
                # 解析会话
                session_data = self._parse_session(session_dir)
                if not session_data:
                    continue
                
                if dry_run:
                    self.stats["imported_sessions"] += 1
                    self.stats["imported_messages"] += len(session_data.get("messages", []))
                    continue
                
                # 导入会话
                self._import_session(session_data, work_dir)
                self.stats["imported_sessions"] += 1
                
            except Exception as e:
                self.stats["errors"].append(f"Failed to import {session_id}: {e}")
    
    def _parse_session(self, session_dir: Path) -> Optional[Dict[str, Any]]:
        """解析会话目录"""
        # 查找 .wire 文件
        wire_files = list(session_dir.glob("*.wire"))
        if not wire_files:
            return None
        
        wire_file = wire_files[0]
        
        # 解析 wire 文件
        messages = []
        title = f"Imported ({session_dir.name[:8]})"
        first_message_time = None
        last_message_time = None
        
        try:
            with open(wire_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    # 跳过元数据
                    if record.get("type") == "metadata":
                        continue
                    
                    # 解析消息
                    msg = self._parse_wire_record(record)
                    if msg:
                        messages.append(msg)
                        
                        # 更新统计
                        if msg["role"] == "user":
                            timestamp = msg.get("timestamp", 0)
                            if first_message_time is None:
                                first_message_time = timestamp
                            last_message_time = timestamp
                            
                            # 使用第一条用户消息作为标题
                            if title.startswith("Imported"):
                                content = msg.get("content", "")
                                if isinstance(content, str):
                                    title = content[:50] + "..." if len(content) > 50 else content
                                elif isinstance(content, list):
                                    # 提取文本内容
                                    texts = []
                                    for part in content:
                                        if isinstance(part, dict) and part.get("type") == "text":
                                            texts.append(part.get("text", ""))
                                    title = " ".join(texts)[:50]
        
        except Exception as e:
            print(f"Error parsing {wire_file}: {e}")
            return None
        
        if not messages:
            return None
        
        return {
            "session_id": session_dir.name,
            "title": title,
            "messages": messages,
            "created_at": int(first_message_time) if first_message_time else int(datetime.now().timestamp()),
            "updated_at": int(last_message_time) if last_message_time else int(datetime.now().timestamp()),
        }
    
    def _parse_wire_record(self, record: Dict) -> Optional[Dict[str, Any]]:
        """解析 wire 记录为统一格式"""
        try:
            timestamp = record.get("timestamp", 0)
            envelope = record.get("message", {})
            
            # 根据消息类型解析
            msg_type = envelope.get("type", "")
            
            if msg_type == "turn_begin":
                # 用户输入
                user_input = envelope.get("user_input", [])
                content = self._extract_content(user_input)
                return {
                    "role": "user",
                    "content": content,
                    "timestamp": timestamp,
                }
            
            elif msg_type == "text":
                # AI 文本回复
                text = envelope.get("text", "")
                return {
                    "role": "assistant",
                    "content": text,
                    "timestamp": timestamp,
                }
            
            elif msg_type == "tool_result":
                # 工具执行结果
                result = envelope.get("result", {})
                content = json.dumps(result, ensure_ascii=False)
                return {
                    "role": "assistant",
                    "content": f"[Tool Result] {content[:200]}",
                    "timestamp": timestamp,
                }
            
            # 其他类型暂时跳过
            return None
            
        except Exception:
            return None
    
    def _extract_content(self, user_input) -> str:
        """提取用户输入内容"""
        if isinstance(user_input, str):
            return user_input
        elif isinstance(user_input, list):
            texts = []
            for item in user_input:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    elif item.get("type") == "image_url":
                        texts.append("[Image]")
            return " ".join(texts)
        return str(user_input)
    
    def _import_session(self, session_data: Dict[str, Any], work_dir: str):
        """导入单个会话语 Memory 系统"""
        session_id = session_data["session_id"]
        
        # 创建会话
        session = Session(
            id=session_id,
            title=session_data["title"],
            created_at=session_data["created_at"],
            updated_at=session_data["updated_at"],
            work_dir=work_dir,
        )
        
        self.service.storage.create_session(session)
        
        # 添加消息
        total_tokens = 0
        for msg_data in session_data["messages"]:
            message = Message(
                session_id=session_id,
                role=msg_data["role"],
                content=msg_data["content"],
                timestamp=msg_data["timestamp"],
                token_count=len(msg_data["content"]) // 4,  # 粗略估计
            )
            self.service.storage.add_message(message)
            total_tokens += message.token_count
            self.stats["total_messages"] += 1
        
        # 更新会话 token 数
        session.token_count = total_tokens
        self.service.storage.update_session(session)
        
        # 触发索引
        self.service.index_session(session_id)
        
        self.stats["imported_messages"] += len(session_data["messages"])
    
    def generate_report(self) -> str:
        """生成导入报告"""
        lines = [
            "📊 Session Import Report",
            "",
            f"Total Sessions Found: {self.stats['total_sessions']}",
            f"Imported: {self.stats['imported_sessions']}",
            f"Skipped (existing): {self.stats['skipped_sessions']}",
            f"Total Messages: {self.stats['total_messages']}",
            f"Imported Messages: {self.stats['imported_messages']}",
        ]
        
        if self.stats["errors"]:
            lines.extend(["", "Errors:"])
            for error in self.stats["errors"][:10]:
                lines.append(f"  - {error}")
            if len(self.stats["errors"]) > 10:
                lines.append(f"  ... and {len(self.stats['errors']) - 10} more")
        
        return "\n".join(lines)
