# Kimi CLI 对话记忆系统 - 架构设计方案

> 版本: v1.0
> 状态: 设计阶段
> 目标: 轻量级、可配置、跨设备同步的对话记忆召回系统

---

## 1. 项目概述

### 1.1 核心目标

构建一个**轻量级、可插拔、集中式**的对话记忆系统，实现：

1. **智能召回**: 基于向量相似度 + 关键词检索，自动召回相关历史对话
2. **跨设备同步**: 无论在哪台设备使用 Kimi CLI，记忆都集中存储
3. **零服务依赖**: 默认使用 SQLite，无需启动额外服务
4. **可插拔架构**: Embedding、存储后端均可配置

### 1.2 关键指标

| 指标 | 目标值 | 说明 |
|-----|-------|-----|
| 存储占用 | < 500MB/万条消息 | 包含向量和全文索引 |
| 召回延迟 | < 200ms | P95 查询延迟 |
| 同步延迟 | < 5秒 | 跨设备同步延迟 |
| 离线可用 | 100% | 本地缓存完整数据 |

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Presentation Layer                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  /recall    │  │ /memory     │  │ /sync       │  │ Auto-recall Trigger │ │
│  │  (召回命令)  │  │ (管理命令)  │  │ (同步命令)  │  │ (自动触发)           │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└─────────┼────────────────┼────────────────┼───────────────────┼────────────┘
          │                │                │                   │
          └────────────────┴────────────────┘───────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Application Layer                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      Memory Service (单例)                               ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  ││
│  │  │ Recall      │  │ Index       │  │ Sync        │  │ Config        │  ││
│  │  │ Engine      │  │ Manager     │  │ Manager     │  │ Manager       │  ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│   Storage Layer   │   │  Embedding Layer  │   │    Sync Layer     │
│  ┌─────────────┐  │   │  ┌─────────────┐  │   │  ┌─────────────┐  │
│  │ SQLite      │  │   │  │ Local ONNX  │  │   │  │ Local Mode  │  │
│  │ (Primary)   │  │   │  │ (Default)   │  │   │  │ (default)   │  │
│  └─────────────┘  │   │  └─────────────┘  │   │  └─────────────┘  │
│  ┌─────────────┐  │   │  ┌─────────────┐  │   │  ┌─────────────┐  │
│  │ FTS5 Index  │  │   │  │ OpenAI API  │  │   │  │ HTTP API    │  │
│  │ (Full-text) │  │   │  │ (Cloud)     │  │   │  │ (Self-host) │  │
│  └─────────────┘  │   │  └─────────────┘  │   │  └─────────────┘  │
│  ┌─────────────┐  │   │  ┌─────────────┐  │   │  ┌─────────────┐  │
│  │ sqlite-vec  │  │   │  │ Custom API  │  │   │  │ SaaS API    │  │
│  │ (Vector)    │  │   │  │ (Private)   │  │   │  │ (Managed)   │  │
│  └─────────────┘  │   │  └─────────────┘  │   │  └─────────────┘  │
└───────────────────┘   └───────────────────┘   └───────────────────┘
```

### 2.2 模块职责

```
┌─────────────────────────────────────────────────────────────────┐
│                        Module Map                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  CLI Layer   │    │  Core Layer  │    │  Data Layer  │      │
│  ├──────────────┤    ├──────────────┤    ├──────────────┤      │
│  │              │    │              │    │              │      │
│  │ • recall.py  │───►│ • RecallSvc  │───►│ • Storage    │      │
│  │ • memory.py  │    │ • IndexSvc   │    │ • Embedding  │      │
│  │ • sync.py    │    │ • SyncSvc    │    │ • SyncClient │      │
│  │              │    │              │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  Commands (入口)       Services (业务)     Adapters (适配器)      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据模型设计

### 3.1 实体关系图

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│    Session      │       │    Message      │       │    Vector       │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ PK id: TEXT     │◄──────┤ PK id: INTEGER  │       │ PK session_id   │
│    title: TEXT  │   1:N │ FK session_id   │       │    embedding    │
│    summary: TEXT│       │    role: TEXT   │       │    model: TEXT  │
│    keywords: JSON      │    content: TEXT│       │    timestamp    │
│    created_at   │       │    token_count  │       └─────────────────┘
│    updated_at   │       │    timestamp    │
│    work_dir     │       └─────────────────┘
│    token_total  │
│    is_archived  │
└─────────────────┘
         │
         │ 1:1
         ▼
┌─────────────────┐
│   SessionFTS    │  (虚拟表 - FTS5全文索引)
├─────────────────┤
│    title        │
│    summary      │
│    keywords     │
│    content      │
└─────────────────┘
```

### 3.2 数据库 Schema

```sql
-- ============================================
-- Kimi Memory System - Database Schema
-- SQLite + sqlite-vec + FTS5
-- ============================================

-- 启用扩展
.load sqlite-vec

-- 会话表
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,                          -- 会话ID (uuid)
    title TEXT NOT NULL,                          -- 会话标题
    summary TEXT,                                 -- AI生成的摘要
    keywords TEXT,                                -- JSON数组 ["关键词1", "关键词2"]
    created_at INTEGER NOT NULL,                  -- 创建时间戳 (unix seconds)
    updated_at INTEGER NOT NULL,                  -- 更新时间戳
    token_count INTEGER DEFAULT 0,                -- 总token数
    work_dir TEXT,                                -- 工作目录
    is_archived BOOLEAN DEFAULT 0,                -- 是否归档
    sync_status TEXT DEFAULT 'local',             -- 同步状态: local | syncing | synced | error
    sync_version INTEGER DEFAULT 1                -- 同步版本号 (乐观锁)
);

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    timestamp INTEGER NOT NULL,
    has_code BOOLEAN DEFAULT 0,                   -- 是否包含代码块
    code_language TEXT,                           -- 主要代码语言
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_session_time ON messages(session_id, timestamp);

-- 全文搜索虚拟表 (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    title,
    summary,
    keywords,
    content='',                                    -- 外部内容模式
    content_rowid='rowid'
);

-- 触发器: 自动同步FTS索引
CREATE TRIGGER IF NOT EXISTS sessions_fts_insert AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, title, summary, keywords)
    VALUES (new.rowid, new.title, new.summary, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_update AFTER UPDATE ON sessions BEGIN
    UPDATE sessions_fts SET 
        title = new.title,
        summary = new.summary,
        keywords = new.keywords
    WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_delete AFTER DELETE ON sessions BEGIN
    DELETE FROM sessions_fts WHERE rowid = old.rowid;
END;

-- 向量表 (sqlite-vec)
CREATE VIRTUAL TABLE IF NOT EXISTS session_vectors USING vec0(
    session_id TEXT PRIMARY KEY,
    embedding FLOAT[1536] distance_metric=cosine  -- 维度可配置
);

-- 同步日志表
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,                      -- 'upload' | 'download' | 'conflict'
    session_id TEXT,
    status TEXT NOT NULL,                         -- 'success' | 'failed'
    error_message TEXT,
    timestamp INTEGER NOT NULL
);

-- 配置表
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
```

---

## 4. 核心流程设计

### 4.1 会话索引流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Session Indexing Flow                        │
└─────────────────────────────────────────────────────────────────┘

新消息产生
    │
    ▼
┌─────────────────┐
│ 1. Store Message │ ───► 写入 messages 表
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Update Stats  │ ───► 更新 sessions.token_count, updated_at
└────────┬────────┘
         │
         ▼
┌─────────────────┐     No      ┌─────────────────┐
│ 3. Check Index   │────────────►│ Return          │
│    Trigger?      │             │                 │
└────────┬────────┘             └─────────────────┘
         │ Yes
         ▼
┌─────────────────┐
│ 4. Extract      │
│    Keywords     │ ───► 使用简单NLP或LLM提取关键词
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. Generate     │
│    Summary      │ ───► AI生成会话摘要 (批处理，非阻塞)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. Embedding    │ ───► 调用Embedding服务生成向量
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 7. Update FTS   │ ───► 更新全文索引 (自动触发器)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 8. Sync Check   │ ───► 如配置远程同步，加入同步队列
└─────────────────┘

Index Trigger Conditions:
- 每5条新消息
- 或会话结束 (>/exit)
- 或距离上次索引 > 10分钟
```

### 4.2 召回查询流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      Recall Query Flow                          │
└─────────────────────────────────────────────────────────────────┘

用户输入: /recall [query]
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Parse Query                                                   │
│    - 提取显式查询 (如有)                                         │
│    - 如无，使用当前会话上下文                                    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Hybrid Search                                                 │
│    ┌─────────────────────┐  ┌─────────────────────┐             │
│    │   Vector Search     │  │   Keyword Search    │             │
│    │                     │  │                     │             │
│    │ query ──► embedding │  │ query ──► fts5      │             │
│    │          │          │  │          │          │             │
│    │          ▼          │  │          ▼          │             │
│    │   vec_top_k()       │  │   match sessions_fts│             │
│    │   RETURN: id, score │  │   RETURN: id, rank  │             │
│    └──────────┬──────────┘  └──────────┬──────────┘             │
│               │                        │                        │
│               └──────────┬─────────────┘                        │
│                          ▼                                      │
│                   Merge & Rerank                                │
│                   Score = 0.6*vec + 0.4*fts                     │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Filter & Sort                                                 │
│    - 排除当前会话                                                │
│    - 时间衰减: score *= exp(-0.001 * days)                       │
│    - 最低相似度阈值: 0.75                                        │
│    - 最多返回: 5条                                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Fetch Details                                                 │
│    - 根据ID查询 sessions 表                                      │
│    - 获取最近3条相关消息 (context window)                        │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Build Context                                                 │
│    [系统提示] 发现以下相关历史对话:                              │
│    ─────────────────────────────────────                        │
│    [相关 #1] 微服务架构设计 (2024-01-15)                         │
│    用户: 如何设计高并发...                                      │
│    AI: 建议从...                                                │
│    ─────────────────────────────────────                        │
│    [相关 #2] Redis 性能优化 (2024-01-10)                         │
│    ...                                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 接口设计

### 5.1 内部接口 (Python)

```python
# storage/base.py
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class Session:
    id: str
    title: str
    summary: Optional[str]
    keywords: List[str]
    created_at: int
    updated_at: int
    token_count: int

@dataclass
class RecallResult:
    session: Session
    vector_score: float
    keyword_score: float
    combined_score: float
    context_messages: List[dict]  # 最近3条消息

class StorageBackend(ABC):
    """存储后端抽象"""
    
    @abstractmethod
    def create_session(self, session: Session) -> None: ...
    
    @abstractmethod
    def add_message(self, session_id: str, role: str, content: str) -> None: ...
    
    @abstractmethod
    def update_embedding(self, session_id: str, embedding: List[float]) -> None: ...
    
    @abstractmethod
    def search_hybrid(
        self, 
        query_embedding: Optional[List[float]], 
        query_text: Optional[str],
        top_k: int = 5,
        min_score: float = 0.75
    ) -> List[RecallResult]: ...

# embedding/base.py
class EmbeddingProvider(ABC):
    """Embedding服务抽象"""
    
    dimensions: int
    
    @abstractmethod
    def embed(self, text: str) -> List[float]: ...
    
    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]: ...

# sync/base.py
class SyncBackend(ABC):
    """同步后端抽象"""
    
    @abstractmethod
    def upload_session(self, session: Session) -> bool: ...
    
    @abstractmethod
    def download_sessions(self, since: int) -> List[Session]: ...
    
    @abstractmethod
    def resolve_conflict(self, local: Session, remote: Session) -> Session: ...
```

### 5.2 命令行接口

```bash
# 记忆系统管理
kimi memory init              # 初始化记忆系统
kimi memory status            # 查看存储状态
kimi memory config            # 交互式配置

# 会话内命令
/recall                       # 自动召回相关记忆
/recall "query"               # 显式查询
/recall --limit 10            # 调整返回数量
/recall --with-context        # 包含完整上下文
/recall --jump-to <id>        # 跳转到指定会话

# 同步控制
/memory sync                  # 手动触发同步
/memory sync --force          # 强制全量同步
/memory sync --status         # 查看同步状态

# 记忆管理
/memory list                  # 列出所有会话
/memory search "keyword"      # 关键词搜索
/memory archive <id>          # 归档会话
/memory delete <id>           # 删除会话
/memory export --format json  # 导出记忆
```

---

## 6. 配置规范

### 6.1 配置文件

```yaml
# ~/.kimi/memory/config.yaml

version: "1.0"

# ============ 存储配置 ============
storage:
  # 本地数据库路径
  db_path: "~/.kimi/memory/memory.db"
  
  # 最大存储限制 (MB)
  max_size_mb: 2048
  
  # 自动清理策略
  cleanup:
    enabled: true
    archive_after_days: 90      # 90天后归档
    delete_archived_after_days: 365  # 归档后1年删除

# ============ Embedding 配置 ============
embedding:
  # 提供者: local_onnx | openai | custom
  provider: "local_onnx"
  
  local_onnx:
    model: "all-MiniLM-L6-v2"   # 默认384维
    model_path: "~/.kimi/models/"
    device: "auto"              # auto | cpu | cuda | mps
    batch_size: 32
  
  openai:
    api_key: "${OPENAI_API_KEY}"
    model: "text-embedding-ada-002"
    dimensions: 1536
    base_url: "https://api.openai.com/v1"
  
  custom:
    api_key: "${CUSTOM_API_KEY}"
    base_url: "https://your-api.com/v1"
    model: "bge-large-zh"
    dimensions: 1024

# ============ 同步配置 ============
sync:
  # 模式: disabled | local | remote | saas
  mode: "local"
  
  # 自动同步间隔 (秒)
  auto_sync_interval: 300
  
  remote:
    endpoint: "https://your-server.com/api/v1"
    token: "${MEMORY_SYNC_TOKEN}"
    timeout: 30
  
  saas:
    provider: "kimi-cloud"
    api_key: "${KIMI_CLOUD_KEY}"

# ============ 召回配置 ============
recall:
  # 自动召回触发
  auto_recall:
    enabled: true
    trigger_on_start: true      # 新会话开始时
    trigger_token_threshold: 0.8  # Token使用80%时
  
  # 混合搜索权重
  hybrid_weights:
    vector: 0.6
    keyword: 0.4
  
  # 结果过滤
  filters:
    min_similarity: 0.75
    max_results: 5
    exclude_current_session: true
    time_decay_factor: 0.001    # 时间衰减系数
  
  # 上下文构建
  context:
    max_messages_per_session: 3
    max_total_tokens: 2000

# ============ 隐私配置 ============
privacy:
  # 敏感词过滤 (不索引包含这些词的消息)
  sensitive_keywords:
    - "password"
    - "secret"
    - "api_key"
  
  # 是否加密本地存储
  encrypt_local: false
  
  # 同步时排除工作目录
  exclude_work_dirs:
    - "*/secret-project/*"
```

---

## 7. 实现路线图

### Phase 1: MVP (2周)
- [ ] SQLite 存储层实现
- [ ] Local ONNX Embedding (默认)
- [ ] 基础 /recall 命令
- [ ] 手动索引触发

### Phase 2: 优化 (1周)
- [ ] 自动索引触发器
- [ ] 混合搜索 (向量 + FTS5)
- [ ] 关键词提取
- [ ] 会话摘要生成

### Phase 3: 同步 (1周)
- [ ] 配置系统
- [ ] HTTP Sync Backend
- [ ] 冲突解决策略
- [ ] 加密传输

### Phase 4: 增强 (1周)
- [ ] SaaS Provider 支持
- [ ] 自动召回触发
- [ ] 智能过滤
- [ ] 性能优化

---

## 8. 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|-----|---------|
| SQLite 并发性能瓶颈 | 中 | 中 | 使用 WAL 模式，读写分离 |
| Embedding 模型过大 | 中 | 低 | 默认使用 MiniLM (80MB) |
| 跨设备同步冲突 | 高 | 中 | 实现向量时钟/版本号机制 |
| 隐私数据泄露 | 低 | 高 | 敏感词过滤，可选加密 |
| API 兼容性变化 | 低 | 中 | 抽象接口，版本隔离 |

---

## 9. 附录

### 9.1 依赖清单

```txt
# Core
sqlite-vec>=0.1.0
sqlite-utils>=3.30

# Embedding (optional)
onnxruntime>=1.15.0
sentence-transformers>=2.2.0  # For model conversion

# Sync
httpx>=0.24.0
 tenacity>=8.0.0  # Retry

# Utils
pyyaml>=6.0
pydantic>=2.0
click>=8.0

# Dev
pytest>=7.0
pytest-asyncio>=0.20
```

### 9.2 参考文档

- [sqlite-vec 文档](https://alexgarcia.xyz/sqlite-vec/)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [ONNX Runtime](https://onnxruntime.ai/)

---

**下一步**: 确定方案后，进入详细设计和实现阶段。
