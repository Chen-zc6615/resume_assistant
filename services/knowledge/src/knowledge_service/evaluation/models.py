from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    """一条知识库黄金评测用例。"""

    id: str
    category: str
    difficulty: str
    query: str = Field(min_length=2)
    ground_truth_answer: str

    reference_chunk_ids: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    metadata_filter: dict[str, object] | None = None

    is_adversarial: bool = False
    is_cross_doc: bool = False


class JudgeEvaluation(BaseModel):
    """LLM-as-Judge 对单条回答的评分。"""

    correctness_score: float = Field(ge=0.0, le=1.0)
    groundedness_score: float = Field(ge=0.0, le=1.0)
    completeness_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    reason: str


class CaseEvaluation(BaseModel):
    """单条黄金用例的实际评测结果。"""

    id: str
    category: str
    query: str
    ground_truth_answer: str
    expected_keywords: list[str]

    passed: bool
    is_refused: bool

    retrieved_chunk_ids: list[str]
    reference_chunk_ids: list[str]

    bm25_recall_count: int
    dense_recall_count: int
    rrf_candidate_count: int

    first_relevant_rank: int | None
    hit_at_1: bool
    hit_at_3: bool
    all_references_hit: bool
    keyword_hit: bool

    rank_before_rerank: int | None
    rank_after_rerank: int | None
    rerank_rank_change: int | None

    metadata_filter_compliant: bool | None
    metadata_filter_recall_passed: bool | None

    citation_count: int
    top_score: float | None
    latency_ms: float
    answer: str
    judge: JudgeEvaluation | None = None


class CorpusStats(BaseModel):
    """知识库语料和切片统计。"""

    document_count: int
    chunk_count: int
    average_chunk_length: float
    minimum_chunk_length: int
    maximum_chunk_length: int
    metadata_complete_rate: float


class ChunkingStrategyStats(BaseModel):
    """一种切片策略的语料规模与检索效果。"""

    strategy: str
    chunk_count: int
    average_chunk_length: float
    hit_rate_at_1: float | None
    hit_rate_at_3: float | None
    mrr: float | None


class EvaluationSummary(BaseModel):
    """全部黄金用例的汇总指标。"""

    total_cases: int
    positive_cases: int
    adversarial_cases: int
    passed_cases: int
    pass_rate: float

    hit_rate_at_1: float | None
    hit_rate_at_3: float | None
    mrr: float | None

    citation_coverage: float | None
    cross_doc_recall_rate: float | None
    adversarial_refusal_rate: float | None

    average_bm25_recall_count: float
    average_dense_recall_count: float
    average_rrf_candidate_count: float

    rerank_improvement_rate: float | None
    average_rerank_rank_change: float | None

    metadata_filter_compliance_rate: float | None
    metadata_filter_recall_rate: float | None

    average_judge_correctness: float | None
    average_judge_groundedness: float | None
    average_judge_completeness: float | None
    judge_pass_rate: float | None

    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float


class EvaluationRun(BaseModel):
    """一次完整评测及其运行环境。"""

    generated_at: str
    dataset_path: str
    embedding_model: str
    rerank_model: str
    refusal_threshold: float

    corpus: CorpusStats
    chunking_strategies: list[ChunkingStrategyStats]
    summary: EvaluationSummary
    cases: list[CaseEvaluation]
