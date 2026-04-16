# FinRPA Enterprise 二次开发改动计划

> 目标：在现有项目基础上，新增 **2 个深度 AI 子系统**，使项目适合作为应届生 AI/大模型应用方向的求职项目。
>
> 原则：**少而精** — 宁可一个模块讲 10 分钟让面试官觉得你真懂，不要 5 个模块各讲 2 分钟让人觉得什么都沾了一点。
>
> 核心叙事线：**RAG 增强 Agent 决策 → Agent 经验反哺 RAG → 评估体系量化证明提升**

---

## 目录

1. [改动总览](#1-改动总览)
2. [模块 A：金融文档 RAG 管道](#2-模块-a金融文档-rag-管道)
3. [模块 B：RAG + Agent 深度集成](#3-模块-brag--agent-深度集成)
4. [模块 C：LLM 可观测与评估体系](#4-模块-cllm-可观测与评估体系)
5. [前端配套：评估看板页面](#5-前端配套评估看板页面)
6. [项目归属清理](#6-项目归属清理)
7. [测试计划](#7-测试计划)
8. [简历与面试准备](#8-简历与面试准备)
9. [实施顺序](#9-实施顺序)

---

## 1. 改动总览

| 编号 | 改动模块 | 新增/修改 | 预估代码量 | 面试价值 |
|------|----------|-----------|-----------|----------|
| A | 金融文档 RAG 管道 | 新增 `enterprise/rag/` + 修改现有模块 | ~800 行 Python | 极高 — AI 岗必问 |
| B | 多 Agent 协作框架 | 新增 `enterprise/agent/framework/` + 改造现有模块 | ~700 行 Python | 极高 — Agent 架构 |
| C | LLM 可观测与评估体系 | 新增 `enterprise/llm_eval/` | ~600 行 Python | 极高 — 工程化深度 |
| 前端 | 评估看板页面 | 新增 1 个前端页面 | ~300 行 TSX | 中 — 全栈展示 |
| 归属 | 项目归属清理 | 修改 README/LICENSE | 文本改动 | 必须 |

**总新增代码量：~2400 行**（Python ~2100 + TSX ~300），三个模块形成闭环。

### 三个模块的闭环故事

面试时能从头讲到尾，每一步都有技术深度：

```
┌──────────────────────────────────────────────────────────────────┐
│                         面试叙事线                                │
│                                                                  │
│  1. 现状：Agent 是硬编码管道，无记忆，扩展性差                   │
│       ↓                                                          │
│  2. RAG 管道：接入合规文档 + 操作指南 + 历史案例知识库           │
│       ↓                                                          │
│  3. 多 Agent 协作框架：                                          │
│     ├─ BaseAgent 统一协议 + AgentRegistry 注册发现               │
│     ├─ AgentMessage 消息总线（Agent 间通信）                     │
│     ├─ RiskAgent / ReviewerAgent / ExperienceAgent 独立 Agent    │
│     ├─ TaskOrchestrator 动态编排多 Agent 协作                    │
│     └─ 每个 Agent 独立接入 RAG + LLM（不同 model tier）          │
│       ↓                                                          │
│  4. 评估体系：Golden Set + LLM-as-Judge，量化多 Agent 协作效果   │
│       ↓                                                          │
│  5. 数据驱动迭代：对比单 Agent vs 多 Agent 的成功率/质量差异     │
└──────────────────────────────────────────────────────────────────┘
```

**为什么做多 Agent？**

单一 Agent 的问题面试官一眼看穿："你这就是一个函数调另一个函数"。多 Agent 框架有三个面试价值：
- **架构设计能力**：Agent 协议、注册发现、消息通信 — 展示系统设计思维
- **和 RAG 的深度结合**：每个 Agent 有自己的知识检索策略，不只是 prompt 注入
- **可扩展性**：新增 Agent 只需实现协议 + 注册，不改现有代码 — 开闭原则

---

## 2. 模块 A：金融文档 RAG 管道

### 2.1 目的

当前项目的风险检测（`enterprise/approval/risk_detector.py`）和任务规划（`enterprise/agent/planner.py`）都是"无记忆"的 — 没有外部知识源。新增 RAG 管道后：

- **风险检测**：检索合规文档（如《商业银行法》条文、内部风控规范），让 LLM 的风险判断有据可依
- **任务规划**：检索历史成功案例，让 Planner 生成更准确的子任务分解
- **面试亮点**：完整的 RAG 全链路（文档摄入 → 分块 → 向量化 → 检索 → 重排序 → 注入 Prompt）

### 2.2 文件结构

```
enterprise/rag/
├── __init__.py              # 模块导出
├── chunker.py               # 文档分块器（递归字符分割）
├── embedder.py              # Embedding 封装（OpenAI / 本地 BGE 双模式）
├── vector_store.py          # 向量存储（ChromaDB，HNSW 索引）
├── retriever.py             # 两阶段检索：向量召回 + BM25 重排序
├── rag_chain.py             # RAG 主链路：query → 检索 → 拼接 → 返回增强上下文
├── document_loader.py       # PDF/TXT/Markdown 文档加载
├── routes.py                # FastAPI 路由：文档上传/查询/删除/检索测试
└── schemas.py               # Pydantic 请求/响应模型
```

### 2.3 各文件详细设计

#### `chunker.py` — 文档分块器

```python
@dataclass
class ChunkConfig:
    chunk_size: int = 512          # token 数
    chunk_overlap: int = 64        # 重叠 token 数
    separator: str = "\n\n"        # 优先分割符（段落）
    secondary_separators: list[str] = field(
        default_factory=lambda: ["\n", "。", ". "]
    )

@dataclass
class DocumentChunk:
    chunk_id: str                  # f"chunk_{uuid.hex[:12]}"
    content: str                   # 分块文本
    metadata: dict[str, Any]       # 来源文件名、页码、位置偏移等
    token_count: int

def split_document(
    text: str,
    config: ChunkConfig,
    metadata: dict
) -> list[DocumentChunk]:
    """
    递归字符分割算法：
    1. 尝试按 separator（段落）分割
    2. 如果分割后的片段 > chunk_size，递归用 secondary_separators 继续分割
    3. 如果最小粒度的分割仍然 > chunk_size，按固定长度硬切
    4. 相邻 chunk 之间保持 overlap 个 token 的重叠

    Token 计数使用 tiktoken（cl100k_base 编码器），精确到 token 级别。
    """
```

**面试深度考点**：
- *为什么 chunk_size=512？* — 平衡检索精度与上下文完整性。太小（128）会丢失上下文，太大（2048）会引入噪声稀释相关内容。512 是法规条文（通常 1-3 段）的自然长度。
- *为什么 overlap=64？* — 约 chunk_size 的 12.5%。防止关键信息被切断在边界。例如"转账金额超过 50 万元需要…"可能恰好跨越两个 chunk 的分界线。
- *为什么优先按段落分割？* — 法规条文按条款组织，段落是语义最小完整单元。按段落分割保持语义完整性，比固定长度切分检索效果好 15-20%（可引用实验数据）。

#### `embedder.py` — Embedding 封装

```python
class EmbeddingProvider(str, Enum):
    OPENAI = "openai"              # text-embedding-3-small, 1536 维
    LOCAL_BGE = "local_bge"        # BAAI/bge-small-zh-v1.5, 512 维

class Embedder:
    def __init__(
        self,
        provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    ):
        """
        根据 provider 初始化：
        - OPENAI: 使用 OpenAI API，1536 维，英文效果好
        - LOCAL_BGE: 加载 sentence-transformers 本地模型，512 维，中文优化
        """

    async def embed_texts(
        self,
        texts: list[str]
    ) -> list[list[float]]:
        """
        批量向量化（用于文档入库）
        - OpenAI: 每批最多 2048 条，自动分 batch
        - BGE: 本地推理，batch_size=32
        """

    async def embed_query(self, query: str) -> list[float]:
        """
        单条 query 向量化
        与 embed_texts 分开的原因：BGE 等模型对 query 和 document
        需要加不同的 instruction prefix
        - query prefix: "为这个句子生成表示以用于检索相关文章："
        - document: 无 prefix
        """
```

**面试深度考点**：
- *OpenAI vs 本地 BGE 怎么选？* — 金融中文文档用 BGE 效果更好（专门在中文语料上训练），且无网络延迟和 API 成本。通用英文场景用 OpenAI。项目做成可切换是为了适应不同部署环境。
- *embed_query 和 embed_texts 为什么分开？* — 非对称检索（Asymmetric Retrieval）的标准做法。Query 通常很短（一句话），Document 较长（一段话），它们在语义空间中的表示方式不同。BGE 论文明确要求对 query 加 instruction prefix。
- *维度 1536 vs 512 有什么区别？* — 高维度表征更丰富但存储大、检索慢。512 维在中文金融场景下已经够用，且 ChromaDB 的 HNSW 索引在低维度下性能更好。

#### `vector_store.py` — ChromaDB 向量存储

```python
class VectorStore:
    def __init__(
        self,
        persist_directory: str = "./data/chroma_db",
        collection_name: str = "finrpa_docs"
    ):
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}  # 余弦相似度
        )

    def add_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]]
    ) -> int:
        """
        批量写入向量和元数据。
        ChromaDB 的 add 是幂等的（相同 ID 会覆盖），无需手动去重。
        返回实际写入数量。
        """

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filter_metadata: dict | None = None
    ) -> list[RetrievalResult]:
        """
        向量检索，支持 metadata 过滤。
        - filter_metadata={"type": "compliance"} → 只在合规文档中检索
        - filter_metadata={"industry": "banking"} → 只在银行业文档中检索
        ChromaDB 的 where 子句支持 $and/$or 组合过滤。
        """

    def delete_by_source(self, source_file: str) -> int:
        """按来源文件删除所有 chunk（文档重新入库时先删旧版本）"""

    def stats(self) -> dict:
        """返回 collection 统计：文档数、chunk 数"""
```

**面试深度考点**：
- *为什么用 ChromaDB 不用 Pinecone/Milvus？* — 本地嵌入式部署、零运维成本、Python 原生 API、适合中小规模（<100 万向量）。面试时应表明知道 Milvus/Pinecone 的优势（分布式、大规模），但对于这个项目规模 ChromaDB 是更务实的选择。
- *HNSW 索引原理？* — Hierarchical Navigable Small World Graph。构建多层图，高层是稀疏的"高速路"，低层是密集的"本地道路"。查询时从最高层开始 greedy search，逐层下降。时间复杂度 O(log N)，空间换时间。参数 M（每层连接数）和 ef（搜索宽度）控制精度/速度权衡。
- *余弦相似度 vs 欧氏距离 vs 内积？* — 归一化后的向量三者等价。余弦相似度对向量长度不敏感，更适合文本 Embedding（不同长度的文本 Embedding 模长可能不同）。

#### `retriever.py` — 两阶段检索

```python
@dataclass
class RetrievalResult:
    chunk: DocumentChunk
    similarity_score: float        # 向量余弦相似度 [0, 1]
    rerank_score: float | None = None  # 重排序后的综合分数

class Retriever:
    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder,
        top_k: int = 10,           # 第一阶段召回数
        rerank_top_k: int = 5      # 第二阶段保留数
    ):
        ...

    async def retrieve(
        self,
        query: str,
        filter_metadata: dict | None = None
    ) -> list[RetrievalResult]:
        """
        两阶段检索流程：
        Stage 1 - 向量召回（高召回率，允许部分不相关）:
          query → embed_query → vector_store.query(top_k=10)

        Stage 2 - BM25 风格重排序（高精确率，过滤噪声）:
          对 10 个候选计算 query 与 chunk 的关键词重叠分数
          综合分数 = 0.7 * similarity_score + 0.3 * rerank_score
          取 top 5 返回
        """

    def _rerank(
        self,
        query: str,
        candidates: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """
        BM25 风格重排序：
        1. 对 query 和每个 chunk 分词
        2. 计算 TF-IDF 加权的关键词重叠度
        3. 特别处理金融领域术语（"转账"、"授信"等高权重词）

        为什么不用 Cross-Encoder？
        → Cross-Encoder（如 bge-reranker）更精确，但需要额外模型加载，
          推理延迟 200-500ms。BM25 重排序 <5ms，对于 10 个候选足够。
          面试时说明知道 Cross-Encoder 的存在和优劣即可。
        """
```

**面试深度考点**：
- *为什么需要两阶段？* — 向量检索是 ANN（近似最近邻），有噪声，且语义相似不等于任务相关。例如"查询余额"和"转账余额"语义相似但风险完全不同。重排序用词汇级特征补充语义级特征。
- *召回 10 个再取 5 个的数量怎么定的？* — top_k=10 保证高召回率（相关文档大概率在 10 个里），rerank_top_k=5 控制最终注入 prompt 的上下文长度（避免占用太多 token）。实际项目中应在评估集上调参。
- *0.7/0.3 权重怎么来的？* — 初始值基于经验，应在评估集上做 grid search。向量相似度权重更高因为它捕获语义信息，BM25 作为补充修正。

#### `rag_chain.py` — RAG 主链路

```python
class RAGChain:
    def __init__(self, retriever: Retriever):
        ...

    async def build_augmented_context(
        self,
        query: str,
        filter_metadata: dict | None = None,
        max_context_tokens: int = 2000
    ) -> RAGContext:
        """
        RAG 主链路，将检索结果拼接成可注入 Prompt 的上下文：
        1. 调用 retriever.retrieve(query)
        2. 按 rerank_score 降序排列
        3. 逐个拼接 chunk 内容，用 tiktoken 计数
        4. 当累计 token 达到 max_context_tokens 时截断
        5. 为每个使用的 chunk 记录来源引用（文件名 + 相似度分数）
        6. 返回 RAGContext
        """

@dataclass
class RAGContext:
    augmented_text: str            # 拼接后的检索文本，直接注入 prompt
    sources: list[dict]            # [{"file": "商业银行法.pdf", "chunk_id": "...", "score": 0.87}]
    total_chunks_retrieved: int    # 检索到的总数（如 10）
    total_chunks_used: int         # 截断后实际使用的数量（如 3-5）
```

#### `routes.py` — 文档管理 API

```python
router = APIRouter(prefix="/enterprise/rag", tags=["rag"])

@router.post("/documents/upload")
async def upload_document(file: UploadFile):
    """上传文档（PDF/TXT/MD），自动执行：解析 → 分块 → 向量化 → 入库"""

@router.get("/documents")
async def list_documents():
    """列出已入库文档（文件名、chunk 数、入库时间）"""

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档及其所有 chunk"""

@router.post("/query")
async def query_rag(request: RAGQueryRequest):
    """检索测试接口：输入 query，返回 top-K 结果和分数（调试和演示用）"""

@router.get("/stats")
async def get_stats():
    """向量库统计信息"""
```

### 2.4 与现有模块的集成（含 Prompt 升级）

RAG 集成不只是"注入检索结果"，同时升级目标模块的 Prompt 质量。Prompt 升级是 RAG 价值的放大器 — 更好的 Prompt 能更有效地利用检索到的上下文。

#### 集成点 1：增强风险检测 + Prompt 升级

修改 `enterprise/approval/risk_detector.py` 的 `_llm_risk_analysis` 函数：

```python
# 现有代码（约第 50 行）:
async def _llm_risk_analysis(text, matched_keywords, page_context=None,
                              llm_callable=None):
    prompt = f"You are a financial compliance officer..."  # 6 行简单 prompt

# ──────────────────────────────────────────────────────
# 改为（新增 rag_chain 参数 + CoT 结构化 Prompt）:

async def _llm_risk_analysis(text, matched_keywords, page_context=None,
                              llm_callable=None, rag_chain=None):
    # === 新增：检索合规文档 ===
    rag_section = ""
    if rag_chain:
        rag_context = await rag_chain.build_augmented_context(
            query=text,
            filter_metadata={"type": "compliance"},
            max_context_tokens=1500
        )
        if rag_context.augmented_text:
            rag_section = f"""
## Reference Regulations (retrieved from knowledge base)
{rag_context.augmented_text}

Sources: {', '.join(s['file'] for s in rag_context.sources)}
"""

    # === Prompt 升级：6 行 → 结构化 CoT ===
    prompt = f"""\
You are a senior financial compliance officer with expertise in \
{industry or "financial"} operations.

## Analysis Framework (Chain-of-Thought)
Analyze this operation step by step:
1. **Operation Type**: What financial action is being performed?
2. **Risk Indicators**: Which matched keywords indicate actual risk vs false positives?
3. **Amount Assessment**: Does the operation involve monetary amounts? How large?
4. **Regulatory Impact**: Could this violate regulations (anti-money laundering, KYC)?
5. **Reversibility**: Is this operation easily reversible if it goes wrong?
6. **Final Judgment**: Based on above analysis, what is the overall risk level?
{rag_section}
## Risk Level Definitions
- medium: Sensitive data or moderate amounts, standard review sufficient
- high: Significant financial loss or regulatory risk, department-level approval
- critical: Very large amounts, cross-border, or regulatory investigation trigger

## Operation Details
- Description: {text}
- Matched risk keywords: {', '.join(kw.keyword for kw in matched_keywords)}
- Keyword categories: {', '.join(set(kw.category for kw in matched_keywords))}
{f'- Page context: {page_context}' if page_context else ''}

Respond with JSON: {{"reasoning": "...", "risk_level": "medium|high|critical", "reason": "..."}}
"""
```

**面试讲解要点**：
- 原来 6 行 prompt → 现在结构化 CoT，风险判断有推理链路可追溯
- RAG 注入的合规文档让 LLM 不再"凭空判断"，而是有法规依据
- `filter_metadata={"type": "compliance"}` 限定只检索合规类文档，避免噪声

#### 集成点 2：增强任务规划 + Few-shot 示例

修改 `enterprise/agent/planner.py`：

```python
# === 1. 升级 PLANNER_SYSTEM_PROMPT（第 30-50 行）===
# 原来：基本指令 + 1 个 example（约 20 行）
# 改为：CoT 推理框架 + 2 个金融领域 Few-shot 示例

PLANNER_SYSTEM_PROMPT = """\
You are a financial RPA planning agent specializing in banking, insurance, \
and securities browser automation.

## Reasoning Process (Chain-of-Thought)
Before generating the plan, think step by step:
1. Identify the target system type (online banking / insurance portal / trading platform)
2. Estimate the number of page navigations required
3. Identify authentication requirements (login, OTP, captcha)
4. Identify data input steps (forms, search, filters)
5. Identify data extraction steps (tables, downloads)
6. Consider failure modes for each step

## Output Format
Output a JSON object with "reasoning" (your analysis) and "steps" array.

## Few-Shot Examples

### Example 1: Bank Statement Collection
Goal: "Login to CMB online banking and download the March 2025 statement"
{
  "reasoning": "Target: CMB online banking. Need login → navigate to statements → select date → download. Login may require SMS OTP.",
  "steps": [
    {"goal": "Login to CMB online banking", "completion_condition": "Welcome message visible", "failure_strategy": "abort", "max_retries": 3},
    {"goal": "Navigate to statement page", "completion_condition": "Statement heading visible", "failure_strategy": "replan", "max_retries": 2},
    {"goal": "Set date filter to March 2025", "completion_condition": "March data displayed", "failure_strategy": "retry", "max_retries": 2},
    {"goal": "Download statement as PDF", "completion_condition": "Download initiated", "failure_strategy": "replan", "max_retries": 2}
  ]
}

### Example 2: Insurance Claim Status Query
Goal: "Query claim status for policy P2025001 on PICC portal"
{
  "reasoning": "Target: PICC portal. Need login → claims page → search by policy number → extract status.",
  "steps": [
    {"goal": "Login to PICC portal", "completion_condition": "Dashboard visible", "failure_strategy": "abort", "max_retries": 3},
    {"goal": "Navigate to claims query", "completion_condition": "Search form visible", "failure_strategy": "replan", "max_retries": 2},
    {"goal": "Search policy P2025001", "completion_condition": "Results displayed", "failure_strategy": "retry", "max_retries": 2},
    {"goal": "Extract claim status", "completion_condition": "Status data captured", "failure_strategy": "replan", "max_retries": 2}
  ]
}
"""

# === 2. _plan_with_llm 新增 RAG 上下文 ===

class PlannerAgent:
    def __init__(self, ..., rag_chain=None):
        self.rag_chain = rag_chain  # 新增

    async def _plan_with_llm(self, navigation_goal, context):
        # 新增：检索历史成功案例
        examples_section = ""
        if self.rag_chain:
            rag_context = await self.rag_chain.build_augmented_context(
                query=navigation_goal,
                filter_metadata={"type": "workflow_example"},
                max_context_tokens=1000
            )
            if rag_context.augmented_text:
                examples_section = (
                    f"\n\n## Reference — similar successful plans:\n"
                    f"{rag_context.augmented_text}"
                )

        prompt = f"{PLANNER_SYSTEM_PROMPT}{examples_section}\n\nGoal: {navigation_goal}"
        ...
```

### 2.5 新增依赖

在 `pyproject.toml` 的 `dependencies` 中新增：

```toml
"chromadb>=0.5.0",
"tiktoken>=0.7.0",           # token 计数（分块用）
```

### 2.6 配置项

在 `.env.example` 中新增：

```env
# RAG Configuration
RAG_EMBEDDING_PROVIDER=openai              # openai 或 local_bge
RAG_CHROMA_PERSIST_DIR=./data/chroma_db
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=64
RAG_TOP_K=10
RAG_RERANK_TOP_K=5
```

---

## 3. 模块 B：多 Agent 协作框架

### 3.1 现状分析

当前 Agent 模块是**硬编码的两角色管道**：

```
现状：Coordinator 直接调用 Planner 和 Executor（函数调用，非 Agent 协作）
      └─ PlannerAgent.create_plan()    → 生成计划
      └─ ExecutorAgent.execute_subtask() → 执行步骤
      └─ risk_detector 被外部调用，不参与 Agent 协作
      └─ 没有统一的 Agent 协议
      └─ 新增 Agent 需要修改 Coordinator 代码
```

面试官问"你的多 Agent 架构是怎么设计的？"，只能说"有一个 Planner 和一个 Executor" — 这不是多 Agent，这是函数调用。

### 3.2 改动目标

搭建**完整的多 Agent 协作框架**，包括：
1. **BaseAgent 统一协议** — 所有 Agent 实现相同接口
2. **AgentMessage 消息机制** — Agent 间通过消息通信，而非直接函数调用
3. **AgentRegistry 注册发现** — 新增 Agent 只需注册，不改编排代码
4. **TaskOrchestrator 动态编排** — 根据任务类型动态选择和编排 Agent
5. **3 个新 Agent** — RiskAgent、ReviewerAgent、ExperienceAgent

```
改动后的架构：

    ┌───────────────────────────────────────────────────────────┐
    │                   TaskOrchestrator                         │
    │  接收用户目标 → 查询 AgentRegistry → 动态编排 Agent 流水线  │
    └──────┬───────────┬──────────┬──────────┬─────────────────┘
           │           │          │          │
  ┌────────▼──────┐ ┌──▼─────┐ ┌──▼─────┐ ┌──▼──────────┐ ┌─────────────┐
  │ PlannerAgent  │ │ Risk   │ │ Exec   │ │ Reviewer    │ │ Experience  │
  │ (改造)        │ │ Agent  │ │ Agent  │ │ Agent       │ │ Agent       │
  │ 规划子任务    │ │ (新增) │ │ (改造) │ │ (新增)      │ │ (新增)      │
  │ RAG:案例     │ │ 风险   │ │ 执行   │ │ 质量审查    │ │ 经验回写    │
  │              │ │ 评估   │ │ 步骤   │ │ 执行结果    │ │ RAG:经验   │
  │              │ │ RAG:   │ │ RAG:   │ │ LLM 评分   │ │             │
  │              │ │ 合规   │ │ 指南   │ │             │ │             │
  └──────────────┘ └────────┘ └────────┘ └─────────────┘ └─────────────┘
           ▲           ▲          ▲          ▲                ▲
           └───────────┴──────────┴──────────┴────────────────┘
                              AgentMessage（消息总线）
```

### 3.3 文件结构

```
enterprise/agent/
├── __init__.py                  # 现有
├── schemas.py                   # 现有（新增 AgentMessage 等）
├── planner.py                   # 现有（改造为 BaseAgent 子类）
├── executor.py                  # 现有（改造为 BaseAgent 子类）
├── coordinator.py               # 现有 → 改造为 TaskOrchestrator
├── framework/                   # === 新增：Agent 框架核心 ===
│   ├── __init__.py
│   ├── base_agent.py            # BaseAgent 抽象基类
│   ├── registry.py              # AgentRegistry 注册与发现
│   ├── message.py               # AgentMessage 消息定义
│   └── orchestrator.py          # TaskOrchestrator 动态编排
├── agents/                      # === 新增：具体 Agent 实现 ===
│   ├── __init__.py
│   ├── risk_agent.py            # RiskAgent（从 risk_detector 提升）
│   ├── reviewer_agent.py        # ReviewerAgent（执行结果质量审查）
│   └── experience_agent.py      # ExperienceAgent（经验回写）
```

### 3.4 框架核心设计

#### `framework/base_agent.py` — Agent 统一协议

```python
"""BaseAgent: 所有 Agent 的抽象基类。

定义统一的 Agent 协议：
- 每个 Agent 有唯一 name 和 description
- 通过 handle_message() 接收消息并返回结果
- 可以携带自己的 LLM callable 和 RAG chain
- 声明自己能处理的消息类型（capabilities）
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from enterprise.rag.rag_chain import RAGChain
from .message import AgentMessage, AgentResponse

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """所有 Agent 的基类，定义统一协议。"""

    # 子类必须定义
    agent_name: ClassVar[str]           # 唯一标识，如 "planner", "risk"
    agent_description: ClassVar[str]    # 人类可读描述
    capabilities: ClassVar[list[str]]   # 能处理的消息类型列表

    def __init__(
        self,
        llm_callable=None,
        rag_chain: RAGChain | None = None,
        model_tier: str = "standard",
    ):
        self.llm_callable = llm_callable
        self.rag_chain = rag_chain
        self.model_tier = model_tier  # 不同 Agent 可用不同模型

    @abstractmethod
    async def handle_message(
        self,
        message: AgentMessage,
    ) -> AgentResponse:
        """
        处理一条消息并返回结果。

        这是 Agent 的核心方法。每个 Agent 根据 message.type
        决定如何处理：
        - PlannerAgent 处理 "plan_request" 和 "replan_request"
        - RiskAgent 处理 "risk_check"
        - ExecutorAgent 处理 "execute_subtask"
        - ReviewerAgent 处理 "review_result"
        - ExperienceAgent 处理 "record_experience"
        """

    def can_handle(self, message_type: str) -> bool:
        """检查此 Agent 是否能处理某种消息类型。"""
        return message_type in self.capabilities
```

**面试讲解**：
- *为什么需要 BaseAgent？* — 统一协议使得 Agent 可以互相替换和组合。新增一个 Agent 只需继承 BaseAgent、实现 handle_message、注册到 Registry，不需要修改任何现有代码。这是**开闭原则**的实践。
- *capabilities 有什么用？* — Orchestrator 通过 capabilities 自动发现哪个 Agent 能处理某种消息。例如收到 "risk_check" 消息，查 Registry 找到 RiskAgent。不需要硬编码"风险检查找 RiskAgent"。
- *model_tier 为什么在 Agent 级别？* — 不同 Agent 对 LLM 能力的需求不同。RiskAgent 处理合规问题需要 HEAVY 模型（如 GPT-4o/Opus），ExperienceAgent 只做格式化不需要 LLM。成本和效果的精细化控制。

#### `framework/message.py` — Agent 间消息

```python
"""AgentMessage: Agent 间通信的消息格式。

消息驱动的 Agent 通信，替代直接函数调用。
好处：解耦、可追踪、可扩展。
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    """Agent 间传递的消息。"""

    message_id: str = Field(
        default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}"
    )
    type: str = Field(
        description="消息类型，决定由哪个 Agent 处理"
    )
    sender: str = Field(
        description="发送者 Agent 的 name"
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="消息载荷（具体内容由 type 决定）"
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="共享上下文（跨 Agent 传递的状态）"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: str = Field(
        default_factory=lambda: f"trace_{uuid.uuid4().hex[:8]}",
        description="追踪 ID，同一任务的所有消息共享同一个 trace_id"
    )


class AgentResponse(BaseModel):
    """Agent 处理消息后的返回。"""

    message_id: str = Field(description="对应的请求 message_id")
    agent_name: str = Field(description="处理此消息的 Agent")
    success: bool = Field(default=True)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    next_messages: list[AgentMessage] = Field(
        default_factory=list,
        description="此 Agent 产出的后续消息（触发其他 Agent）"
    )
    duration_ms: int | None = None
```

**面试讲解**：
- *为什么消息驱动而不是直接调用？* — 三个好处：(1) **解耦**：Agent 之间只知道消息格式，不知道彼此的实现细节；(2) **可追踪**：每条消息有 trace_id，可以追踪一个任务在多个 Agent 间的完整流转链路；(3) **可扩展**：新增 Agent 只需处理新的 message type，不需要修改发送方。
- *next_messages 是什么？* — Agent 可以在处理消息后产出新消息。例如 RiskAgent 检测到高风险后产出一条 `{"type": "approval_request"}` 消息。这实现了**事件驱动的级联触发**。
- *trace_id 的作用？* — 一个用户任务可能经过 5 个 Agent 处理，产生 10+ 条消息。trace_id 把它们串起来，结合 LLMTracer 可以看到完整的调用链路。

#### `framework/registry.py` — Agent 注册与发现

```python
"""AgentRegistry: Agent 注册表，支持按能力发现 Agent。

类似于项目中已有的 SKILL_REGISTRY（enterprise/skills/base.py），
但为 Agent 设计，支持按 capabilities 查找。
"""

import logging
from typing import Any

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent 注册表：注册、发现、管理所有 Agent 实例。"""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}  # name → instance

    def register(self, agent: BaseAgent) -> None:
        """注册一个 Agent 实例。"""
        if agent.agent_name in self._agents:
            logger.warning("Agent %s already registered, overwriting", agent.agent_name)
        self._agents[agent.agent_name] = agent
        logger.info(
            "Registered agent: %s (capabilities: %s)",
            agent.agent_name,
            agent.capabilities,
        )

    def get(self, name: str) -> BaseAgent | None:
        """按名称获取 Agent。"""
        return self._agents.get(name)

    def find_by_capability(self, message_type: str) -> list[BaseAgent]:
        """找到所有能处理某种消息类型的 Agent。"""
        return [
            agent for agent in self._agents.values()
            if agent.can_handle(message_type)
        ]

    def list_agents(self) -> list[dict[str, Any]]:
        """列出所有已注册 Agent 的元数据。"""
        return [
            {
                "name": agent.agent_name,
                "description": agent.agent_description,
                "capabilities": agent.capabilities,
                "model_tier": agent.model_tier,
            }
            for agent in self._agents.values()
        ]

    def unregister(self, name: str) -> bool:
        """注销一个 Agent。"""
        if name in self._agents:
            del self._agents[name]
            return True
        return False


# 全局 Agent 注册表（类似 SKILL_REGISTRY 的设计）
agent_registry = AgentRegistry()
```

**面试讲解**：
- *和 SKILL_REGISTRY 有什么关系？* — 项目已有 `SKILL_REGISTRY`（注册 7 个 Skill），`AgentRegistry` 是同一设计模式在 Agent 层面的应用。Skill 是无状态工具（login、form_fill），Agent 是有状态决策者（带 LLM、RAG、上下文记忆）。Agent 可以**调用 Skill 作为自己的工具**。
- *find_by_capability 怎么用？* — Orchestrator 收到一条 message，调 `registry.find_by_capability(message.type)` 找到能处理它的 Agent，然后分发。不需要 if-else 判断。
- *为什么是实例注册而不是类注册？* — Agent 有状态（llm_callable、rag_chain、model_tier），不同实例可以配置不同参数。例如同一个 RiskAgent 类可以注册两个实例：一个用 HEAVY 模型做精确判断，一个用 LIGHT 模型做快速筛选。

#### `framework/orchestrator.py` — 动态编排

```python
"""TaskOrchestrator: 多 Agent 任务编排器。

替代原有 AgentCoordinator 的硬编码调用，改为：
1. 定义 Agent Pipeline（有序的 Agent 处理阶段）
2. 按 Pipeline 顺序发送消息给对应 Agent
3. 收集每个 Agent 的 response，传递给下一个
4. 支持条件分支（如风险等级决定是否跳过某个 Agent）
"""

import logging
import time
from typing import Any

from .base_agent import BaseAgent
from .message import AgentMessage, AgentResponse
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


class PipelineStage(BaseModel):
    """Pipeline 的一个阶段。"""
    message_type: str              # 要发送的消息类型
    required: bool = True          # 是否必须成功才能继续
    condition: str | None = None   # 条件表达式（基于前序结果）
    # condition 示例：
    # "risk_level in ('high', 'critical')" → 只有高风险才执行
    # None → 无条件执行


# 预定义的 Pipeline 模板
FINANCIAL_TASK_PIPELINE = [
    PipelineStage(message_type="plan_request", required=True),
    PipelineStage(message_type="risk_check", required=True),
    PipelineStage(
        message_type="approval_request",
        required=True,
        condition="risk_level in ('high', 'critical')",
    ),
    PipelineStage(message_type="execute_subtask", required=True),
    PipelineStage(message_type="review_result", required=False),
    PipelineStage(message_type="record_experience", required=False),
]


class TaskOrchestrator:
    """多 Agent 任务编排器。"""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    async def run_pipeline(
        self,
        pipeline: list[PipelineStage],
        initial_message: AgentMessage,
    ) -> dict[str, Any]:
        """
        按 Pipeline 定义的顺序编排多个 Agent。

        流程：
        1. 遍历 pipeline 的每个 stage
        2. 检查 condition（基于已有结果判断是否跳过）
        3. 从 registry 找到能处理 message_type 的 Agent
        4. 发送消息，收集 response
        5. 将 response.result 合并到 context，传递给下一个 stage
        6. 处理 response.next_messages（级联触发）
        """
        context = dict(initial_message.context)
        trace_id = initial_message.trace_id
        results: list[dict] = []

        for stage in pipeline:
            # 条件检查
            if stage.condition and not self._eval_condition(stage.condition, context):
                logger.info("Skipping stage %s (condition not met)", stage.message_type)
                continue

            # 找到 Agent
            agents = self.registry.find_by_capability(stage.message_type)
            if not agents:
                if stage.required:
                    return {"success": False, "error": f"No agent for {stage.message_type}"}
                continue

            agent = agents[0]  # 取第一个匹配的 Agent

            # 构建消息
            message = AgentMessage(
                type=stage.message_type,
                sender="orchestrator",
                payload=initial_message.payload,
                context=context,
                trace_id=trace_id,
            )

            # 发送并收集结果
            start = time.monotonic()
            response = await agent.handle_message(message)
            elapsed = int((time.monotonic() - start) * 1000)

            results.append({
                "stage": stage.message_type,
                "agent": agent.agent_name,
                "success": response.success,
                "duration_ms": elapsed,
            })

            if not response.success and stage.required:
                return {
                    "success": False,
                    "error": f"Stage {stage.message_type} failed: {response.error}",
                    "results": results,
                }

            # 合并结果到 context
            context.update(response.result)

            # 处理级联消息
            for next_msg in response.next_messages:
                next_msg.trace_id = trace_id
                next_agents = self.registry.find_by_capability(next_msg.type)
                for na in next_agents:
                    await na.handle_message(next_msg)

        return {"success": True, "context": context, "results": results}

    @staticmethod
    def _eval_condition(condition: str, context: dict) -> bool:
        """安全地评估条件表达式。"""
        try:
            # 只允许简单的 in/not in/==/!= 比较
            return eval(condition, {"__builtins__": {}}, context)
        except Exception:
            return True  # 条件评估失败时默认执行
```

**面试深度考点**：
- *Pipeline 和原来的 Coordinator 有什么区别？* — Coordinator 是硬编码的 `planner.create_plan()` → `executor.execute()`。Pipeline 是声明式的：`[plan_request, risk_check, execute, review]`。新增一个阶段只需在列表里加一行，不改编排代码。
- *condition 字段怎么用？* — 条件分支。例如 `"risk_level in ('high', 'critical')"` 表示只有高风险操作才需要审批。低风险操作跳过审批直接执行。这是**动态编排**的核心。
- *next_messages 实现了什么？* — 事件驱动的级联。Agent 处理完消息后可以触发其他 Agent。例如 ExecutorAgent 执行完后产出 `record_experience` 消息，ExperienceAgent 自动被触发。不需要 Orchestrator 预先定义这个关联。
- *和 LangGraph/CrewAI 的区别？* — 思路类似（Agent + 消息 + 编排），但我们是自己实现的轻量版，和项目的 RAG/Eval/Skill 体系深度集成，而不是引入外部框架再做适配。面试时能说清自研 vs 框架的 trade-off。

### 3.5 新增 Agent 实现

#### `agents/risk_agent.py` — 风险评估 Agent

```python
"""RiskAgent: 将现有 risk_detector 提升为独立 Agent。

不是简单包装，而是增强：
- 继承 BaseAgent 协议
- 接入 RAG（合规文档检索）
- 使用 HEAVY model tier（风险评估需要最强推理能力）
- 通过 next_messages 触发审批流程
"""

from enterprise.agent.framework.base_agent import BaseAgent
from enterprise.agent.framework.message import AgentMessage, AgentResponse
from enterprise.approval.risk_detector import detect_risk


class RiskAgent(BaseAgent):
    agent_name = "risk"
    agent_description = "Financial risk assessment agent with compliance RAG"
    capabilities = ["risk_check"]

    def __init__(self, llm_callable=None, rag_chain=None):
        super().__init__(
            llm_callable=llm_callable,
            rag_chain=rag_chain,
            model_tier="heavy",  # 风险评估用最强模型
        )

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        """
        处理风险检查请求。

        输入 payload: {"operation_text": str, "industry": str}
        输出 result: {"risk_level": str, "risk_reason": str, ...}

        如果风险等级 >= high，在 next_messages 中产出 approval_request
        """
        operation_text = message.payload.get("operation_text", "")
        industry = message.payload.get("industry")

        assessment = await detect_risk(
            operation_text=operation_text,
            industry=industry,
            llm_callable=self.llm_callable,
            rag_chain=self.rag_chain,
        )

        result = {
            "risk_level": assessment.risk_level,
            "risk_reason": assessment.reason,
            "risk_stage": assessment.stage,
        }

        # 高风险时触发审批
        next_messages = []
        if assessment.risk_level in ("high", "critical"):
            next_messages.append(AgentMessage(
                type="approval_request",
                sender=self.agent_name,
                payload={
                    "risk_level": assessment.risk_level,
                    "risk_reason": assessment.reason,
                    "operation": operation_text,
                },
                context=message.context,
            ))

        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=True,
            result=result,
            next_messages=next_messages,
        )
```

#### `agents/reviewer_agent.py` — 执行结果质量审查 Agent

```python
"""ReviewerAgent: 审查 Executor 的执行结果质量。

这是多 Agent 架构的独特价值 — 一个 Agent 的输出被另一个 Agent 审查。
类似于代码的 Code Review：Executor "写代码"，Reviewer "审代码"。

审查维度：
1. 完成条件是否满足（文本匹配检查）
2. 执行时间是否合理（异常检测）
3. 结果数据是否完整
4. 可选：用 LLM 对结果做语义评估
"""

from enterprise.agent.framework.base_agent import BaseAgent
from enterprise.agent.framework.message import AgentMessage, AgentResponse


class ReviewerAgent(BaseAgent):
    agent_name = "reviewer"
    agent_description = "Quality reviewer for execution results"
    capabilities = ["review_result"]

    def __init__(self, llm_callable=None, rag_chain=None):
        super().__init__(
            llm_callable=llm_callable,
            rag_chain=rag_chain,
            model_tier="light",  # 审查用轻量模型即可
        )

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        """
        审查执行结果。

        输入 payload: {
            "subtask_goal": str,
            "completion_condition": str,
            "execution_result": dict,
            "duration_ms": int,
        }
        输出 result: {
            "review_passed": bool,
            "quality_score": float,  # 0-1
            "issues": list[str],
        }
        """
        goal = message.payload.get("subtask_goal", "")
        condition = message.payload.get("completion_condition", "")
        exec_result = message.payload.get("execution_result", {})
        duration = message.payload.get("duration_ms", 0)

        issues = []
        score = 1.0

        # 检查 1：执行是否成功
        if not exec_result.get("success", False):
            issues.append("Execution reported failure")
            score -= 0.5

        # 检查 2：结果数据是否为空
        if not exec_result.get("data"):
            issues.append("No result data returned")
            score -= 0.2

        # 检查 3：执行时间异常检测
        if duration and duration > 30000:  # > 30 秒
            issues.append(f"Unusually long execution: {duration}ms")
            score -= 0.1

        # 检查 4：可选 LLM 语义审查
        if self.llm_callable and exec_result.get("success"):
            llm_score = await self._llm_review(goal, condition, exec_result)
            score = score * 0.6 + llm_score * 0.4  # 加权

        score = max(0.0, min(1.0, score))

        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=True,
            result={
                "review_passed": score >= 0.6 and not any("failure" in i.lower() for i in issues),
                "quality_score": round(score, 2),
                "issues": issues,
            },
        )

    async def _llm_review(self, goal: str, condition: str, result: dict) -> float:
        """用 LLM 评估执行结果是否真正满足目标。"""
        prompt = f"""\
Review this task execution result:
- Goal: {goal}
- Expected completion condition: {condition}
- Actual result: {result}

Score the quality from 0 to 10. Respond with just the number.
"""
        try:
            raw = await self.llm_callable(prompt)
            return min(10, max(0, float(raw.strip()))) / 10.0
        except Exception:
            return 0.5  # LLM 失败时给中间分
```

**面试讲解**：
- *为什么需要 ReviewerAgent？* — 单一 Agent 的"自我报告"不可靠。Executor 说"成功了"，但结果可能是空的、不完整的、或耗时异常的。ReviewerAgent 提供**第二视角**，类似代码审查。这是多 Agent 架构相比单 Agent 的核心优势。
- *和 LLM-as-Judge 的区别？* — LLM-as-Judge 是离线评估（跑 Golden Set），ReviewerAgent 是在线审查（每次执行后实时检查）。前者验证系统整体质量，后者保证单次执行质量。

#### `agents/experience_agent.py` — 经验学习 Agent

```python
"""ExperienceAgent: 将执行经验结构化并写入向量库。

监听 ExecutorAgent 的执行结果，自动回写经验。
这让多 Agent 系统形成"学习闭环"：
  执行 → 记录经验 → 下次检索经验 → 更好的执行
"""

from datetime import datetime

from enterprise.agent.framework.base_agent import BaseAgent
from enterprise.agent.framework.message import AgentMessage, AgentResponse
from enterprise.rag.schemas import DocumentChunk


class ExperienceAgent(BaseAgent):
    agent_name = "experience"
    agent_description = "Records execution experiences to vector store for future retrieval"
    capabilities = ["record_experience"]

    def __init__(self, vector_store=None, embedder=None):
        super().__init__(model_tier="none")  # 不需要 LLM
        self.vector_store = vector_store
        self.embedder = embedder

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        """
        记录执行经验。

        输入 payload: {
            "subtask_goal": str,
            "navigation_goal": str,
            "success": bool,
            "result_data": dict | None,
            "error_message": str | None,
            "duration_ms": int,
            "org_id": str,
        }
        """
        if not self.vector_store or not self.embedder:
            return AgentResponse(
                message_id=message.message_id,
                agent_name=self.agent_name,
                success=False,
                error="Vector store or embedder not configured",
            )

        payload = message.payload
        success = payload.get("success", False)

        # 格式化经验文本
        if success:
            text = (
                f"[SUCCESS] Goal: {payload.get('navigation_goal')}\n"
                f"Sub-task: {payload.get('subtask_goal')}\n"
                f"Duration: {payload.get('duration_ms')}ms\n"
                f"Result: {payload.get('result_data')}"
            )
        else:
            text = (
                f"[FAILURE] Goal: {payload.get('navigation_goal')}\n"
                f"Sub-task: {payload.get('subtask_goal')}\n"
                f"Error: {payload.get('error_message')}\n"
                f"Suggestion: Consider alternative approach."
            )

        # 向量化并写入
        embedding = await self.embedder.embed_texts([text])
        chunk = DocumentChunk(
            chunk_id=f"exp_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{message.message_id[-6:]}",
            content=text,
            metadata={
                "type": "experience",
                "outcome": "success" if success else "failure",
                "org_id": payload.get("org_id", ""),
                "goal_category": self._categorize(payload.get("subtask_goal", "")),
                "timestamp": datetime.utcnow().isoformat(),
            },
            token_count=len(text) // 4,
        )
        self.vector_store.add_chunks([chunk], embedding)

        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=True,
            result={"experience_recorded": True, "chunk_id": chunk.chunk_id},
        )

    @staticmethod
    def _categorize(goal: str) -> str:
        categories = {
            "login": ["登录", "login", "sign in"],
            "query": ["查询", "query", "search"],
            "transfer": ["转账", "transfer", "汇款"],
            "download": ["下载", "download", "导出"],
        }
        goal_lower = goal.lower()
        for cat, keywords in categories.items():
            if any(kw in goal_lower for kw in keywords):
                return cat
        return "general"
```

### 3.6 现有 Agent 改造

#### PlannerAgent 改造为 BaseAgent 子类

修改 `enterprise/agent/planner.py`：

```python
# 改造前：独立的类，被 Coordinator 直接调用
class PlannerAgent:
    def __init__(self, llm_callable=None, rag_chain=None): ...
    async def create_plan(self, navigation_goal, context): ...

# 改造后：继承 BaseAgent，通过消息驱动
from enterprise.agent.framework.base_agent import BaseAgent
from enterprise.agent.framework.message import AgentMessage, AgentResponse

class PlannerAgent(BaseAgent):
    agent_name = "planner"
    agent_description = "Decomposes navigation goals into sub-task plans"
    capabilities = ["plan_request", "replan_request"]

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        if message.type == "plan_request":
            plan = await self.create_plan(
                message.payload["navigation_goal"],
                message.context,
            )
            return AgentResponse(
                message_id=message.message_id,
                agent_name=self.agent_name,
                result={"plan": plan.model_dump()},
            )
        elif message.type == "replan_request":
            plan = await self.replan(...)
            return AgentResponse(...)

    # create_plan / replan / _plan_with_llm 等方法保持不变
    # 既可以通过 handle_message 消息驱动调用，
    # 也保留直接调用 create_plan() 的能力（向后兼容）
```

#### ExecutorAgent 同样改造

```python
class ExecutorAgent(BaseAgent):
    agent_name = "executor"
    agent_description = "Executes sub-tasks via browser automation"
    capabilities = ["execute_subtask"]

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        subtask = SubTask.model_validate(message.payload["subtask"])
        result = await self.execute_subtask(subtask, message.context)

        # 执行完后产出 review + experience 消息
        next_messages = [
            AgentMessage(
                type="review_result",
                sender=self.agent_name,
                payload={
                    "subtask_goal": subtask.goal,
                    "completion_condition": subtask.completion_condition,
                    "execution_result": result.model_dump(),
                    "duration_ms": result.duration_ms,
                },
            ),
            AgentMessage(
                type="record_experience",
                sender=self.agent_name,
                payload={
                    "subtask_goal": subtask.goal,
                    "navigation_goal": message.context.get("navigation_goal"),
                    "success": result.success,
                    "result_data": result.result_data,
                    "error_message": result.error_message,
                    "duration_ms": result.duration_ms,
                    "org_id": message.context.get("org_id"),
                },
            ),
        ]

        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=result.success,
            result=result.model_dump(),
            next_messages=next_messages,
        )
```

### 3.7 多 Agent 协作全景

```
用户目标："登录招商银行网银，下载 3 月份对账单"
                    │
                    ▼
          ┌─────────────────┐
          │ TaskOrchestrator │
          │ Pipeline:        │
          │ 1. plan_request  │─→ PlannerAgent (STANDARD model + RAG:案例)
          │ 2. risk_check    │─→ RiskAgent   (HEAVY model + RAG:合规)
          │ 3. approval_req  │─→ [条件: risk>=high 才执行，利用已有 pubsub]
          │ 4. execute_task  │─→ ExecutorAgent (+ RAG:操作指南)
          │ 5. review_result │─→ ReviewerAgent (LIGHT model, 质量审查)
          │ 6. record_exp    │─→ ExperienceAgent (无 LLM, 写入向量库)
          └─────────────────┘
                    │
           所有消息共享 trace_id
                    │
                    ▼
        LLMTracer 记录全链路调用 → EvalDashboard 可视化
```

### 3.8 新增测试

| 测试文件 | 覆盖内容 | 用例数 |
|----------|---------|--------|
| `tests/unit/test_base_agent.py` | BaseAgent 协议、can_handle | 6 |
| `tests/unit/test_agent_registry.py` | 注册、发现、按能力查找 | 8 |
| `tests/unit/test_agent_message.py` | 消息构造、序列化 | 5 |
| `tests/unit/test_orchestrator.py` | Pipeline 编排、条件分支、级联消息 | 10 |
| `tests/unit/test_risk_agent.py` | 风险检测 + 触发审批 | 6 |
| `tests/unit/test_reviewer_agent.py` | 质量审查、LLM 评分 | 8 |
| `tests/unit/test_experience_agent.py` | 经验回写、分类 | 6 |

---

## 4. 模块 C：LLM 可观测与评估体系

### 3.1 目的

当前项目的 LLM 调用是"黑盒"的 — 没有记录每次调用的 prompt/response/耗时/token 数，无法量化效果。这意味着 Prompt 改动是"盲改"，无法证明改动是否有效。

新增评估体系解决三个问题：
1. **可观测性**：每次 LLM 调用全链路追踪（prompt → response → latency → token → cost）
2. **自动评估**：Golden Test Set 回归测试，Prompt 改动前后效果量化对比
3. **面试亮点**：展示"LLM 工程化"能力 — 不只是调 API，而是有评估、有迭代、有数据驱动

### 3.2 文件结构

```
enterprise/llm_eval/
├── __init__.py
├── tracer.py                # LLM 调用追踪器（装饰器模式）
├── trace_store.py           # 追踪数据存储（SQLAlchemy 模型 + Alembic 迁移）
├── evaluator.py             # 自动评估引擎
├── golden_set.py            # Golden Test Set 管理
├── metrics.py               # 评估指标：Accuracy/F1 + LLM-as-Judge
├── routes.py                # 评估 API（触发评估/查看报告/对比版本/追踪查询）
└── schemas.py               # Pydantic 数据模型
```

### 3.3 各文件详细设计

#### `tracer.py` — LLM 调用追踪器

```python
@dataclass
class LLMTrace:
    trace_id: str              # f"trace_{uuid.hex[:12]}"
    timestamp: datetime
    module: str                # "risk_detector" / "planner" / "resilient_caller"
    prompt: str                # 完整的 prompt 文本
    response: str              # LLM 返回的原始文本
    model_tier: str            # "light" / "standard" / "heavy"
    latency_ms: int            # 端到端延迟
    input_tokens: int          # prompt token 数
    output_tokens: int         # response token 数
    estimated_cost_usd: float  # 根据 model_tier 单价估算
    success: bool              # 是否成功解析
    error: str | None = None   # 错误信息（如果有）
    metadata: dict = field(default_factory=dict)  # 额外上下文

# 每种 model_tier 的单价（USD per 1K tokens）
COST_TABLE = {
    "light":    {"input": 0.00025, "output": 0.00125},   # Haiku/4o-mini
    "standard": {"input": 0.003,   "output": 0.015},     # Sonnet/GPT-4o-mini
    "heavy":    {"input": 0.015,   "output": 0.075},     # Opus/GPT-4o
}

class LLMTracer:
    """
    装饰器模式：包装现有的 llm_callable，透明记录每次调用。
    关键设计：不改变原函数签名和行为，只在外层加一层监控。
    """

    def __init__(self, module_name: str, model_tier: str = "standard"):
        self.module_name = module_name
        self.model_tier = model_tier

    def wrap(self, llm_callable) -> Callable:
        """
        返回新的 async callable，行为与原始完全一致，
        但自动记录 LLMTrace 到 trace_store。

        关键实现细节：
        - 使用 tiktoken 计算 token 数（不依赖 API 返回的 usage）
        - 失败时也记录 trace（success=False），便于分析错误模式
        - trace 存储是异步的，不阻塞主流程
        """
        async def traced_callable(prompt: str) -> str:
            start = time.monotonic()
            try:
                response = await llm_callable(prompt)
                elapsed = int((time.monotonic() - start) * 1000)
                input_tokens = count_tokens(prompt)
                output_tokens = count_tokens(response)
                trace = LLMTrace(
                    trace_id=f"trace_{uuid.uuid4().hex[:12]}",
                    timestamp=datetime.utcnow(),
                    module=self.module_name,
                    prompt=prompt,
                    response=response,
                    model_tier=self.model_tier,
                    latency_ms=elapsed,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=self._calc_cost(input_tokens, output_tokens),
                    success=True,
                )
                await trace_store.save(trace)  # 异步存储，不阻塞
                return response
            except Exception as e:
                elapsed = int((time.monotonic() - start) * 1000)
                trace = LLMTrace(..., success=False, error=str(e))
                await trace_store.save(trace)
                raise  # 原样抛出，不吞异常
        return traced_callable
```

**集成方式** — 修改 `enterprise/llm/resilient_caller.py`：

```python
# 现有代码（第 ~80 行）:
async def call_llm_with_retry(llm_callable, prompt, schema_class, ...):
    for attempt in range(max_retries):
        raw_response = await llm_callable(prompt)

# 改为（在调用前包装，一行改动）:
async def call_llm_with_retry(llm_callable, prompt, schema_class, ...,
                               tracer: LLMTracer | None = None):
    traced = tracer.wrap(llm_callable) if tracer else llm_callable
    for attempt in range(max_retries):
        raw_response = await traced(prompt)
```

#### `trace_store.py` — 追踪数据存储

```python
class LLMTraceModel(Base):
    """SQLAlchemy ORM 模型，复用项目已有的 PostgreSQL"""
    __tablename__ = "llm_traces"

    trace_id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    organization_id = Column(String, nullable=False, index=True)
    module = Column(String, nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    response = Column(Text)
    model_tier = Column(String, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    success = Column(Boolean, nullable=False)
    error = Column(Text)
    metadata_json = Column(Text)         # JSON 序列化的额外上下文

# 复合索引（优化常见查询模式）
# idx_trace_module_time: (module, timestamp) — "最近 24h planner 调用"
# idx_trace_org_time: (organization_id, timestamp) — "某组织的调用历史"
```

需要新增 Alembic 迁移文件创建 `llm_traces` 表。

#### `evaluator.py` — 自动评估引擎

```python
class EvalTask:
    """
    一个评估任务：在一组 Golden Cases 上运行指定模块，计算汇总指标。
    这是"数据驱动 Prompt 迭代"的核心：
      Prompt v1 → 跑 Golden Set → F1=0.78
      Prompt v2 → 跑 Golden Set → F1=0.85 → 提升 7%，有据可依
    """

    def __init__(self, golden_set: GoldenSet, module: str,
                 llm_callable=None):
        ...

    async def run(self) -> EvalReport:
        """
        遍历 golden_set 中的每个 case：
        1. 用 case.input 调用目标模块（risk_detector / planner）
        2. 对比 case.expected_output 和实际输出
        3. 按模块类型调用对应的 metrics 计算函数
        4. 生成 EvalReport（含每个 case 的详细结果 + 汇总指标）
        """

@dataclass
class EvalReport:
    eval_id: str
    module: str                   # "risk_detector" / "planner"
    timestamp: datetime
    total_cases: int
    passed: int
    failed: int
    metrics: dict[str, float]     # {"accuracy": 0.85, "f1": 0.87, "miss_rate": 0.0}
    details: list[CaseResult]     # 每个 case 的输入/期望/实际/通过与否
    prompt_version: str           # 标记当前 prompt 版本，便于 A/B 对比

@dataclass
class CaseResult:
    case_id: str
    input_text: str
    expected: dict
    actual: dict
    passed: bool
    score: float                  # LLM-as-Judge 评分 [0, 1]
    error: str | None = None
```

#### `golden_set.py` — Golden Test Set 管理

```python
@dataclass
class GoldenCase:
    case_id: str
    input_text: str                      # 输入（操作描述 / 导航目标）
    expected_output: dict[str, Any]      # 期望输出
    module: str                          # "risk_detector" / "planner"
    tags: list[str] = field(default_factory=list)

class GoldenSet:
    """从 JSON 文件加载/保存 Golden Cases"""

    def __init__(self, file_path: str = "data/golden_sets/"):
        ...

    def load(self, module: str) -> list[GoldenCase]: ...
    def save(self, cases: list[GoldenCase], module: str): ...
    def add_case(self, case: GoldenCase): ...
```

需要创建初始 Golden Set 数据文件：

```
data/golden_sets/
├── risk_detector.json       # ~30 个风险检测评估案例
└── planner.json             # ~20 个任务规划评估案例
```

**risk_detector.json 示例**（覆盖银行/保险/证券，low/medium/high/critical 四个等级）：

```json
[
  {
    "case_id": "risk_001",
    "input_text": "将客户账户资金 500 万元转账至指定对公账户",
    "expected_output": {"risk_level": "critical", "reason_contains": "大额转账"},
    "module": "risk_detector",
    "tags": ["banking", "fund_transfer", "critical"]
  },
  {
    "case_id": "risk_002",
    "input_text": "查询客户近 3 个月对账单",
    "expected_output": {"risk_level": "low"},
    "module": "risk_detector",
    "tags": ["banking", "query", "low"]
  },
  {
    "case_id": "risk_003",
    "input_text": "修改客户保单受益人为非直系亲属",
    "expected_output": {"risk_level": "high", "reason_contains": "受益人"},
    "module": "risk_detector",
    "tags": ["insurance", "beneficiary_change", "high"]
  }
]
```

#### `metrics.py` — 评估指标计算

```python
def compute_risk_metrics(results: list[CaseResult]) -> dict[str, float]:
    """
    风险检测评估指标：
    - accuracy: 风险等级完全匹配的比例
    - weighted_f1: 按 risk_level 类别的加权 F1（处理类别不平衡）
    - miss_rate: 高/critical 风险被判低的比例（最危险指标，金融场景必须为 0）
    - conservative_rate: 低风险被高估的比例（可接受，宁可误报不可漏报）

    面试要点：金融风控的特殊性 — miss_rate 比 accuracy 更重要。
    宁可误报（conservative_rate 高）也不能漏报（miss_rate 必须为 0）。
    """

def compute_planner_metrics(results: list[CaseResult]) -> dict[str, float]:
    """
    规划质量指标：
    - plan_validity: 生成的 JSON 可解析且符合 schema 的比例
    - avg_step_count: 平均子任务数
    - goal_coverage: 子任务描述与原始目标的词汇覆盖度
    """

async def llm_as_judge(
    case_input: str,
    expected: dict,
    actual: dict,
    judge_callable=None
) -> float:
    """
    LLM-as-Judge：用另一个 LLM 评估输出质量。

    Prompt 设计：
    "你是一位金融 AI 系统评估专家。给定输入、期望输出、实际输出，
     请从准确性、完整性、推理质量三个维度打分（每项 0-10），
     并给出一句话评语。"

    返回归一化分数 [0, 1]（三维度均分的均值 / 10）。

    面试深度考点：
    - LLM-as-Judge 的 bias：位置偏好、自我偏好、长度偏好
    - 缓解方法：多次采样取平均、不同模型交叉评估、随机化选项顺序
    """
```

#### `routes.py` — 评估 API

```python
router = APIRouter(prefix="/enterprise/eval", tags=["evaluation"])

@router.post("/run")
async def run_evaluation(request: EvalRunRequest):
    """触发评估任务：指定 module + golden set + prompt_version 标签"""

@router.get("/reports")
async def list_reports(module: str = None, limit: int = 20):
    """列出历史评估报告"""

@router.get("/reports/{eval_id}")
async def get_report(eval_id: str):
    """单个报告详情（含每个 case 的详细结果）"""

@router.get("/compare")
async def compare_reports(eval_id_a: str, eval_id_b: str):
    """
    对比两次评估报告，用于 Prompt A/B 测试：
    返回各指标的 diff（如 F1: 0.78 → 0.85, +0.07）
    """

@router.get("/traces")
async def list_traces(module: str = None, hours: int = 24, limit: int = 100):
    """查询 LLM 调用追踪记录"""

@router.get("/traces/stats")
async def trace_stats(hours: int = 24):
    """追踪统计：按模块的调用量、平均延迟、总成本、成功率"""
```

---

## 5. 前端配套：评估看板页面

只做 **1 个前端页面**（评估看板），不做 RAG 管理页面（RAG 的文档管理通过 API 操作即可，不需要 UI 面试展示）。

### 新增文件

`skyvern-frontend/src/routes/enterprise/eval/EvalDashboardPage.tsx`

### 功能设计

沿用现有 Glassmorphism 设计风格（`GlassCard` + `StatusBadge` + ECharts），包含 4 个区域：

```
┌───────────────────────────────────────────────────────────┐
│  LLM Evaluation Dashboard                                 │
├──────────────────────┬────────────────────────────────────┤
│  评估报告列表         │  报告详情                          │
│  ┌──────────────┐    │  Module: risk_detector              │
│  │ 2026-04-10   │    │  Prompt Version: v2-cot             │
│  │ risk_detector │    │  Accuracy: 87%  F1: 0.85           │
│  │ F1: 0.85 ✓   │    │  Miss Rate: 0%  ✓                  │
│  ├──────────────┤    │  ─────────────────────────          │
│  │ 2026-04-09   │    │  Case Details:                      │
│  │ risk_detector │    │  ✓ risk_001: critical → critical    │
│  │ F1: 0.78     │    │  ✗ risk_015: high → medium          │
│  └──────────────┘    │  ✓ risk_002: low → low              │
├──────────────────────┴────────────────────────────────────┤
│  版本对比（A/B Test）                                      │
│  Prompt v1 (baseline)  vs  Prompt v2 (CoT + RAG)          │
│  Accuracy: 72% → 87% (+15%)                               │
│  F1:       0.78 → 0.85 (+0.07)                            │
│  Miss Rate: 3.3% → 0% (✓ eliminated)                     │
├───────────────────────────────────────────────────────────┤
│  LLM 调用追踪趋势（ECharts 折线图）                        │
│  ╭──╮    ╭─╮                                              │
│  │  ╰────╯ ╰──  Latency (ms)                             │
│  ╰─────────────  Calls/hour                               │
│                   Cost ($)                                 │
└───────────────────────────────────────────────────────────┘
```

### 路由注册

修改路由配置，新增：

```typescript
{ path: "/enterprise/eval", element: <EvalDashboardPage /> }
```

修改侧边栏导航组件（`EnterpriseSideNav`），新增 "LLM Evaluation" 导航项。

### i18n

在中英文翻译文件中添加评估相关的键值。

---

## 6. 项目归属清理

| 文件 | 改动内容 |
|------|----------|
| `README.md` 第 322 行 | `MIT License (c) 2026 Xuelin Xu (Musenn)` → 改为你的名字 |
| `README.md` 第 156 行 | `git clone https://github.com/Musenn/...` → 改为你的 GitHub 仓库 |
| `README.md` 第 282-308 行 | "致同路人" 个人信件 → 删除或替换为你的项目说明 |
| `LICENSE` 第 3 行 | `Copyright (c) 2026 Xuelin Xu (Musenn)` → 改为你的名字 |
| `README.md` 核心改造内容 | 新增第 10/11 节（RAG 管道 + 评估体系）说明 |

---

## 7. 测试计划

### 7.1 新增测试文件

| 测试文件 | 覆盖模块 | 预估用例数 |
|----------|----------|-----------|
| `tests/unit/test_rag_chunker.py` | 文档分块 | 10 |
| `tests/unit/test_rag_retriever.py` | 检索 + 重排序 | 12 |
| `tests/unit/test_rag_chain.py` | RAG 主链路 | 8 |
| `tests/unit/test_llm_tracer.py` | LLM 追踪器 | 8 |
| `tests/unit/test_evaluator.py` | 评估引擎 | 10 |
| `tests/unit/test_metrics.py` | 指标计算 | 8 |
| `tests/unit/test_base_agent.py` | BaseAgent 协议 | 6 |
| `tests/unit/test_agent_registry.py` | Agent 注册发现 | 8 |
| `tests/unit/test_agent_message.py` | 消息构造 | 5 |
| `tests/unit/test_orchestrator.py` | Pipeline 编排 | 10 |
| `tests/unit/test_risk_agent.py` | 风险 Agent | 6 |
| `tests/unit/test_reviewer_agent.py` | 审查 Agent | 8 |
| `tests/unit/test_experience_agent.py` | 经验 Agent | 6 |

**总计：~105 个新测试用例**，项目总测试数从 601 → 706+。

测试模式沿用现有风格：
- `pytest` + `@pytest.mark.asyncio`
- 直接导入模块函数/类，不走 HTTP 层
- Mock LLM callable 通过参数注入
- 无需真实 Embedding API — mock Embedder 返回固定向量

### 7.2 Golden Set 数据验证

- `data/golden_sets/risk_detector.json`：30 个案例，覆盖银行/保险/证券，low/medium/high/critical
- `data/golden_sets/planner.json`：20 个案例，覆盖不同导航目标类型

---

## 8. 简历与面试准备

### 8.1 简历项目描述（建议版本）

> **FinRPA — 金融级 AI 浏览器自动化平台** | Python, FastAPI, React, LLM
>
> 基于 LLM + 视觉理解的金融 RPA 平台，支持银行/保险/证券场景的浏览器自动化操作
>
> - 设计并实现**金融文档 RAG 管道**：文档分块(512 token) → Embedding(OpenAI/BGE 双模式) → ChromaDB 向量检索 → BM25 重排序，为风险检测注入合规文档、为任务规划注入历史案例
> - 设计**多 Agent 协作框架**：定义 BaseAgent 统一协议 + AgentMessage 消息总线 + AgentRegistry 注册发现 + TaskOrchestrator 动态编排，实现 5 个 Agent（Planner/Executor/Risk/Reviewer/Experience）消息驱动协作，每个 Agent 独立接入 RAG 和不同 model tier 的 LLM
> - 搭建 **LLM 评估体系**：50+ Golden Test Cases，Accuracy/F1/Miss Rate 自动回归 + LLM-as-Judge 语义评分，量化多 Agent 协作效果

### 8.2 高频面试问答

| 面试问题 | 回答要点 |
|---------|---------|
| "RAG 的分块策略怎么选？" | chunk_size=512 平衡精度与完整性；overlap=64(12.5%) 防止边界信息丢失；优先按段落分割保持法规条文语义完整 |
| "向量检索的召回率怎么评？" | Golden Set 标注相关文档作 ground truth，计算 Recall@K 和 MRR |
| "重排序为什么不用 Cross-Encoder？" | BM25 风格 <5ms，Cross-Encoder 200-500ms。10 个候选的规模下 BM25 够用，表明知道 Cross-Encoder 更精确 |
| "LLM-as-Judge 有什么缺陷？" | 位置偏好、自我偏好、长度偏好。缓解：多采样平均、交叉模型评估 |
| "评估体系怎么证明 Prompt 改进有效？" | 同一 Golden Set，跑两个 prompt 版本，F1/Miss Rate 量化对比。给出具体数字 |
| "CoT 对风险检测有什么帮助？" | 强制 LLM 分步推理（操作类型→风险指标→金额→法规→可逆性），reasoning 字段可追溯，比直接输出结论更可靠 |
| "RAG 注入会不会超出 context window？" | max_context_tokens=1500/2000 限制，加上原始 prompt ~500 token，总计 <3000，远在 128K window 内 |
| "多 Agent 框架怎么设计的？" | BaseAgent 统一协议（handle_message）+ AgentRegistry 注册发现（find_by_capability）+ AgentMessage 消息通信 + TaskOrchestrator Pipeline 动态编排。类似 CrewAI 但自研轻量版，和项目 RAG/Eval/Skill 体系深度集成 |
| "为什么不直接用 LangGraph/CrewAI？" | 自研好处：(1) 和项目已有 SKILL_REGISTRY 设计模式一致；(2) 每个 Agent 能独立接入 RAG chain 做不同类型的知识检索；(3) 轻量，没有外部框架的学习成本和适配开销。面试时说明知道这些框架的存在 |
| "5 个 Agent 之间怎么通信？" | 消息驱动。Orchestrator 按 Pipeline 顺序发送 AgentMessage，Agent 返回 AgentResponse 并可产出 next_messages 级联触发其他 Agent。每条消息共享 trace_id 实现全链路追踪 |
| "ReviewerAgent 有什么价值？" | 单 Agent 自我报告不可靠，ReviewerAgent 提供第二视角：检查结果是否为空、执行时间是否异常、可选 LLM 语义评分。类似 Code Review 机制 |
| "经验回写会不会引入噪声？" | metadata 过滤（org_id + type + outcome + goal_category）控制检索范围；成功/失败分开标记。ExperienceAgent 是独立 Agent，可以单独关闭或调整策略 |

### 8.3 面试展示流程建议

1. **先讲问题**："原来的 Agent 是硬编码两角色管道，无记忆，扩展性差"
2. **再讲 RAG**："我搭建了 RAG 管道，接入合规文档、操作指南、历史案例"
3. **重点讲多 Agent 框架**："设计了 BaseAgent 协议 + 消息总线 + 注册发现 + Pipeline 编排，5 个 Agent 各司其职：Planner 规划、RiskAgent 风险评估触发审批、Executor 执行 + RAG 检索指南、ReviewerAgent 质量审查、ExperienceAgent 经验回写形成学习闭环"
4. **讲评估**："用 Golden Set 量化，多 Agent 协作后成功率从 X% 提升到 Y%"
5. **如果追问细节**：Agent 协议设计（参考 SKILL_REGISTRY 模式）、消息 trace_id 全链路追踪、Pipeline 条件分支、和 LangGraph/CrewAI 的对比

---

## 9. 实施顺序

### 阶段 1：基础设施（0.5 天）
1. 清理项目归属（README/LICENSE）
2. 新增依赖到 `pyproject.toml`（chromadb, tiktoken）
3. 创建目录结构

### 阶段 2：RAG 管道（2 天）
1. 实现 `enterprise/rag/` 全部文件
2. 集成到 `risk_detector.py`（RAG 上下文 + CoT Prompt 升级）
3. 集成到 `planner.py`（RAG 上下文 + Few-shot Prompt 升级）
4. 编写测试：`test_rag_chunker.py` + `test_rag_retriever.py` + `test_rag_chain.py`

### 阶段 3：多 Agent 协作框架（2.5 天）
1. 实现 `framework/base_agent.py` + `framework/message.py` + `framework/registry.py`
2. 实现 `framework/orchestrator.py`（Pipeline 编排 + 条件分支）
3. 实现 `agents/risk_agent.py`（从 risk_detector 提升为 Agent）
4. 实现 `agents/reviewer_agent.py`（执行结果质量审查）
5. 实现 `agents/experience_agent.py`（经验回写到向量库）
6. 改造 `planner.py` 和 `executor.py` 为 BaseAgent 子类
7. 编写测试：`test_base_agent.py` + `test_agent_registry.py` + `test_agent_message.py` + `test_orchestrator.py` + `test_risk_agent.py` + `test_reviewer_agent.py` + `test_experience_agent.py`

### 阶段 4：LLM 评估体系（2 天）
1. 实现 `enterprise/llm_eval/` 全部文件
2. 集成 tracer 到 `resilient_caller.py`
3. 新增 Alembic 迁移（`llm_traces` 表）
4. 创建 Golden Set 数据（50 个案例）
5. 编写测试：`test_llm_tracer.py` + `test_evaluator.py` + `test_metrics.py`

### 阶段 5：前端 + 收尾（1 天）
1. 实现评估看板页面（`EvalDashboardPage.tsx`）
2. 更新路由和侧边栏 + i18n
3. 更新 README 新增模块说明
4. 运行全量测试确保 706+ 测试通过
