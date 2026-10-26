import json
import math
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from knowledge_service.evaluation.models import (
    CaseEvaluation,
    ChunkingStrategyStats,
    CorpusStats,
    EvaluationRun,
    EvaluationSummary,
    GoldenCase,
)
from knowledge_service.models.schemas import SearchRequest
from knowledge_service.services.knowledge import KnowledgeService

golden_cases_adapter = TypeAdapter(list[GoldenCase])


def load_golden_cases(path: Path) -> list[GoldenCase]:
    content = path.read_text(encoding="utf-8")
    raw_cases = json.loads(content)
    return golden_cases_adapter.validate_python(raw_cases)


def _first_reference_rank(
    ranked_chunk_ids: list[str], reference_chunk_ids: list[str]
) -> int | None:
    ranks = [
        ranked_chunk_ids.index(chunk_id) + 1
        for chunk_id in reference_chunk_ids
        if chunk_id in ranked_chunk_ids
    ]
    return min(ranks, default=None)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _optional_average(values: list[float]) -> float | None:
    return _average(values) if values else None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


class KnowledgeEvaluator:
    def __init__(self, service: KnowledgeService):
        self.service = service
        self.chunks = self.service.store.all_chunks()
        self.chunk_aliases = self._build_legacy_chunk_aliases(self.chunks)
        self.chunk_metadata = {
            self.chunk_aliases.get(chunk["chunk_id"], chunk["chunk_id"]): chunk["metadata"]
            for chunk in self.chunks
        }

    def _build_legacy_chunk_aliases(
        self, chunks: list[dict[str, object]]
    ) -> dict[str, str]:
        """把哈希切片 ID 映射为黄金集使用的“文档名_chunk_N”。"""
        aliases: dict[str, str] = {}
        for chunk in chunks:
            metadata = chunk["metadata"]
            if not isinstance(metadata, dict):
                continue
            talent_card_id = str(metadata.get("talent_card_id", ""))
            chunk_index = metadata.get("chunk_index")
            if talent_card_id and isinstance(chunk_index, int):
                chunk_id = str(chunk["chunk_id"])
                aliases[chunk_id] = f"{talent_card_id}_chunk_{chunk_index + 1}"
        return aliases

    def _aliases(self, chunk_ids: list[str]) -> list[str]:
        return [self.chunk_aliases.get(chunk_id, chunk_id) for chunk_id in chunk_ids]

    def corpus_stats(self) -> CorpusStats:
        lengths = [len(str(chunk["content"])) for chunk in self.chunks]
        talent_card_ids = {
            str(chunk["metadata"].get("talent_card_id"))
            for chunk in self.chunks
            if isinstance(chunk["metadata"], dict)
            and chunk["metadata"].get("talent_card_id") is not None
        }
        required_metadata = ("talent_card_id", "document_type", "section", "chunk_index")
        complete_chunks = sum(
            isinstance(chunk["metadata"], dict)
            and all(key in chunk["metadata"] for key in required_metadata)
            for chunk in self.chunks
        )
        return CorpusStats(
            document_count=len(talent_card_ids),
            chunk_count=len(self.chunks),
            average_chunk_length=_average([float(length) for length in lengths]),
            minimum_chunk_length=min(lengths, default=0),
            maximum_chunk_length=max(lengths, default=0),
            metadata_complete_rate=_rate(complete_chunks, len(self.chunks)) or 0.0,
        )

    def evaluate_case(self, case: GoldenCase) -> CaseEvaluation:
        outcome = self.service.search_with_diagnostics(SearchRequest(query=case.query))
        diagnostics = outcome.diagnostics

        bm25_ids = self._aliases(diagnostics.bm25_chunk_ids)
        dense_ids = self._aliases(diagnostics.dense_chunk_ids)
        rrf_ids = self._aliases(diagnostics.rrf_chunk_ids)
        reranked_ids = self._aliases(diagnostics.reranked_chunk_ids)
        retrieved_ids = self._aliases([result.chunk_id for result in outcome.results])

        rank_before = _first_reference_rank(rrf_ids, case.reference_chunk_ids)
        rank_after = _first_reference_rank(reranked_ids, case.reference_chunk_ids)
        all_references_hit = bool(case.reference_chunk_ids) and all(
            chunk_id in retrieved_ids for chunk_id in case.reference_chunk_ids
        )
        evidence = "\n\n".join(result.content for result in outcome.results)
        keyword_hit = all(
            keyword.lower() in evidence.lower() for keyword in case.expected_keywords
        )
        is_refused = (
            not outcome.results
            or outcome.results[0].rerank_score
            < self.service.settings.knowledge_refusal_threshold
        )

        if case.is_adversarial:
            passed = is_refused
        else:
            retrieval_passed = (
                all_references_hit if case.is_cross_doc else rank_after is not None
            )
            passed = not is_refused and retrieval_passed and keyword_hit

        return CaseEvaluation(
            id=case.id,
            category=case.category,
            query=case.query,
            ground_truth_answer=case.ground_truth_answer,
            expected_keywords=case.expected_keywords,
            passed=passed,
            is_refused=is_refused,
            retrieved_chunk_ids=retrieved_ids,
            reference_chunk_ids=case.reference_chunk_ids,
            bm25_recall_count=len(bm25_ids),
            dense_recall_count=len(dense_ids),
            rrf_candidate_count=len(rrf_ids),
            first_relevant_rank=rank_after,
            hit_at_1=rank_after == 1,
            hit_at_3=rank_after is not None and rank_after <= 3,
            all_references_hit=all_references_hit,
            keyword_hit=keyword_hit,
            rank_before_rerank=rank_before,
            rank_after_rerank=rank_after,
            rerank_rank_change=(
                rank_before - rank_after
                if rank_before is not None and rank_after is not None
                else None
            ),
            citation_count=len(outcome.results),
            top_score=(diagnostics.reranked_scores[0] if diagnostics.reranked_scores else None),
            latency_ms=outcome.latency_ms,
            answer=evidence,
            judge=None,
        )

    def summarize(
        self, cases: list[GoldenCase], results: list[CaseEvaluation]
    ) -> EvaluationSummary:
        paired = list(zip(cases, results))
        positive = [result for case, result in paired if not case.is_adversarial]
        adversarial = [result for case, result in paired if case.is_adversarial]
        cross_doc = [result for case, result in paired if case.is_cross_doc]
        judged = [result.judge for result in results if result.judge is not None]
        rank_changes = [
            float(result.rerank_rank_change)
            for result in positive
            if result.rerank_rank_change is not None
        ]
        latencies = [result.latency_ms for result in results]

        return EvaluationSummary(
            total_cases=len(results),
            positive_cases=len(positive),
            adversarial_cases=len(adversarial),
            passed_cases=sum(result.passed for result in results),
            pass_rate=_rate(sum(result.passed for result in results), len(results)) or 0.0,
            hit_rate_at_1=_rate(sum(result.hit_at_1 for result in positive), len(positive)),
            hit_rate_at_3=_rate(sum(result.hit_at_3 for result in positive), len(positive)),
            mrr=(
                round(
                    sum(
                        1 / result.first_relevant_rank
                        for result in positive
                        if result.first_relevant_rank is not None
                    )
                    / len(positive),
                    4,
                )
                if positive
                else None
            ),
            citation_coverage=_rate(
                sum(result.citation_count > 0 for result in positive), len(positive)
            ),
            cross_doc_recall_rate=_rate(
                sum(result.all_references_hit for result in cross_doc), len(cross_doc)
            ),
            adversarial_refusal_rate=_rate(
                sum(result.is_refused for result in adversarial), len(adversarial)
            ),
            average_bm25_recall_count=_average(
                [float(result.bm25_recall_count) for result in results]
            ),
            average_dense_recall_count=_average(
                [float(result.dense_recall_count) for result in results]
            ),
            average_rrf_candidate_count=_average(
                [float(result.rrf_candidate_count) for result in results]
            ),
            rerank_improvement_rate=_rate(
                sum(change > 0 for change in rank_changes), len(rank_changes)
            ),
            average_rerank_rank_change=_optional_average(rank_changes),
            average_judge_correctness=_optional_average(
                [judge.correctness_score for judge in judged]
            ),
            average_judge_groundedness=_optional_average(
                [judge.groundedness_score for judge in judged]
            ),
            average_judge_completeness=_optional_average(
                [judge.completeness_score for judge in judged]
            ),
            judge_pass_rate=_rate(sum(judge.passed for judge in judged), len(judged)),
            average_latency_ms=_average(latencies),
            p50_latency_ms=_percentile(latencies, 0.50),
            p95_latency_ms=_percentile(latencies, 0.95),
        )

    def run(self, cases: list[GoldenCase], dataset_path: Path) -> EvaluationRun:
        results = [self.evaluate_case(case) for case in cases]
        corpus = self.corpus_stats()
        summary = self.summarize(cases, results)
        structured_stats = ChunkingStrategyStats(
            strategy="structured",
            chunk_count=corpus.chunk_count,
            average_chunk_length=corpus.average_chunk_length,
            hit_rate_at_1=summary.hit_rate_at_1,
            hit_rate_at_3=summary.hit_rate_at_3,
            mrr=summary.mrr,
        )
        settings = self.service.settings
        return EvaluationRun(
            generated_at=datetime.now(UTC).isoformat(),
            dataset_path=str(dataset_path),
            embedding_model=settings.embedding_model,
            rerank_model=settings.rerank_model,
            refusal_threshold=settings.knowledge_refusal_threshold,
            corpus=corpus,
            chunking_strategies=[structured_stats],
            summary=summary,
            cases=results,
        )
