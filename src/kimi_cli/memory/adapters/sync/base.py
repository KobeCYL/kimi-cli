"""同步后端抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from datetime import datetime

from kimi_cli.memory.models.data import Session


class SyncBackend(ABC):
    """同步后端抽象基类
    
    实现类需要支持会话的双向同步
    """
    
    @abstractmethod
    def authenticate(self) -> bool:
        """认证并连接远程服务"""
        pass
    
    @abstractmethod
    def upload_session(self, session: Session, messages: list) -> Tuple[bool, str]:
        """上传会话到远程
        
        Returns:
            (success, message_or_error)
        """
        pass
    
    @abstractmethod
    def download_sessions(self, since: Optional[datetime] = None) -> List[Session]:
        """从远程下载会话列表
        
        Args:
            since: 只下载此时间之后的会话
            
        Returns:
            会话列表
        """
        pass
    
    @abstractmethod
    def download_messages(self, session_id: str) -> list:
        """下载会话的完整消息"""
        pass
    
    @abstractmethod
    def check_conflict(
        self, 
        local: Session, 
        remote: Session
    ) -> Optional[str]:
        """检查冲突
        
        Returns:
            冲突描述，无冲突返回 None
        """
        pass
    
    @abstractmethod
    def resolve_conflict(
        self, 
        local: Session, 
        remote: Session,
        strategy: str = "newest"
    ) -> Session:
        """解决冲突
        
        Args:
            strategy: 'newest' | 'local' | 'remote' | 'merge'
        """
        pass
    
    @abstractmethod
    def get_sync_status(self) -> dict:
        """获取同步状态"""
        pass
    
    def is_configured(self) -> bool:
        """检查是否已配置 (默认True，子类可覆盖)"""
        return True
