from __future__ import annotations

from knowledge_service.evaluation.models import EvaluationRun


def _percentage(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def _number(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(run: EvaluationRun) -> str:
    """把一次完整评测渲染为可审查的 Markdown 报告。"""
    corpus = run.corpus
    summary = run.summary
    lines = [
        "# 知识库评测报告",
        "",
        "## 运行信息",
        "",
        f"- 生成时间：`{run.generated_at}`",
        f"- 黄金数据集：`{run.dataset_path}`",
        f"- Embedding模型：`{run.embedding_model}`",
        f"- Rerank模型：`{run.rerank_model}`",
        f"- 拒答阈值：`{run.refusal_threshold}`",
        "",
        "## 语料与切片",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 文档数 | {corpus.document_count} |",
        f"| 切片数 | {corpus.chunk_count} |",
        f"| 平均切片长度 | {corpus.average_chunk_length:.2f} |",
        f"| 最短切片长度 | {corpus.minimum_chunk_length} |",
        f"| 最长切片长度 | {corpus.maximum_chunk_length} |",
        f"| 必要元数据完整率 | {_percentage(corpus.metadata_complete_rate)} |",
        "",
        "## 切片策略对比",
        "",
        "| 策略 | 切片数 | 平均长度 | Hit@1 | Hit@3 | MRR |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for strategy in run.chunking_strategies:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(strategy.strategy),
                    str(strategy.chunk_count),
                    f"{strategy.average_chunk_length:.2f}",
                    _percentage(strategy.hit_rate_at_1),
                    _percentage(strategy.hit_rate_at_3),
                    _number(strategy.mrr),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 核心问答指标",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            f"| 总用例数 | {summary.total_cases} |",
            f"| 正向用例数 | {summary.positive_cases} |",
            f"| 对抗用例数 | {summary.adversarial_cases} |",
            f"| 通过用例数 | {summary.passed_cases} |",
            f"| 总通过率 | {_percentage(summary.pass_rate)} |",
            f"| Hit Rate@1 | {_percentage(summary.hit_rate_at_1)} |",
            f"| Hit Rate@3 | {_percentage(summary.hit_rate_at_3)} |",
            f"| MRR | {_number(summary.mrr)} |",
            f"| Citation覆盖率 | {_percentage(summary.citation_coverage)} |",
            f"| 跨文档召回率 | {_percentage(summary.cross_doc_recall_rate)} |",
            f"| 对抗问题拒答率 | {_percentage(summary.adversarial_refusal_rate)} |",
            "",
            "## 检索与重排过程",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            f"| BM25平均召回数 | {summary.average_bm25_recall_count:.2f} |",
            f"| Dense平均召回数 | {summary.average_dense_recall_count:.2f} |",
            f"| RRF平均候选数 | {summary.average_rrf_candidate_count:.2f} |",
            f"| Rerank排名提升率 | {_percentage(summary.rerank_improvement_rate)} |",
            f"| Rerank平均排名变化 | {_number(summary.average_rerank_rank_change, 2)} |",
            "| 元数据过滤条件遵守率 | "
            f"{_percentage(summary.metadata_filter_compliance_rate)} |",
            "| 元数据过滤答案保留率 | "
            f"{_percentage(summary.metadata_filter_recall_rate)} |",
            "",
            "## LLM-as-Judge",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            f"| 平均正确性 | {_percentage(summary.average_judge_correctness)} |",
            f"| 平均事实绑定度 | {_percentage(summary.average_judge_groundedness)} |",
            f"| 平均完整性 | {_percentage(summary.average_judge_completeness)} |",
            f"| Judge通过率 | {_percentage(summary.judge_pass_rate)} |",
            "",
            "## 性能",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            f"| 平均延迟 | {summary.average_latency_ms:.2f} ms |",
            f"| P50延迟 | {summary.p50_latency_ms:.2f} ms |",
            f"| P95延迟 | {summary.p95_latency_ms:.2f} ms |",
            "",
            "## 黄金用例明细",
            "",
            "| ID | 分类 | 结果 | Hit@1 | Hit@3 | RRF排名 | "
            "Rerank排名 | Top分数 | 引用数 | 延迟 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in run.cases:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.id,
                    _markdown_cell(case.category),
                    "PASS" if case.passed else "FAIL",
                    "是" if case.hit_at_1 else "否",
                    "是" if case.hit_at_3 else "否",
                    str(case.rank_before_rerank or "N/A"),
                    str(case.rank_after_rerank or "N/A"),
                    _number(case.top_score),
                    str(case.citation_count),
                    f"{case.latency_ms:.2f} ms",
                ]
            )
            + " |"
        )

    lines.extend(["", "## 未通过用例", ""])
    failed_cases = [case for case in run.cases if not case.passed]
    if not failed_cases:
        lines.append("全部用例通过。")
    for case in failed_cases:
        lines.extend(
            [
                f"### {case.id} — {_markdown_cell(case.query)}",
                "",
                f"- 标准答案：{_markdown_cell(case.ground_truth_answer)}",
                f"- 实际答案：{_markdown_cell(case.answer)}",
                f"- 预期切片：`{', '.join(case.reference_chunk_ids) or '无'}`",
                f"- 实际Top-K：`{', '.join(case.retrieved_chunk_ids) or '无'}`",
                f"- 预期关键词：`{', '.join(case.expected_keywords) or '无'}`",
                f"- 是否拒答：{'是' if case.is_refused else '否'}",
                "",
            ]
        )

    lines.extend(["## 能力缺口", ""])
    gap_count = 0
    if len(run.chunking_strategies) < 2:
        lines.append("- 朴素切片对照尚未运行，当前只有结构化切片结果。")
        gap_count += 1
    if summary.judge_pass_rate is None:
        lines.append("- LLM-as-Judge尚未执行，相关指标显示为N/A。")
        gap_count += 1
    if summary.metadata_filter_compliance_rate is None:
        lines.append("- 黄金集中没有元数据过滤用例，相关指标显示为N/A。")
        gap_count += 1
    if gap_count == 0:
        lines.append("- 无。")

    return "\n".join(lines).rstrip() + "\n"
