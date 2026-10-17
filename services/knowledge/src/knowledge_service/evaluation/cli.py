from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_service.core.config import REPOSITORY_ROOT, get_settings
from knowledge_service.evaluation.evaluator import KnowledgeEvaluator, load_golden_cases
from knowledge_service.evaluation.reporter import render_markdown
from knowledge_service.services.knowledge import KnowledgeService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行知识库黄金集评测并生成报告")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPOSITORY_ROOT / "evals" / "knowledge_retrieval" / "golden_dataset_v1.0.json",
        help="黄金数据集JSON路径",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "reports" / "knowledge_retrieval",
        help="评测结果输出目录",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_path = args.dataset.resolve()
    output_dir = args.output_dir.resolve()

    cases = load_golden_cases(dataset_path)
    evaluator = KnowledgeEvaluator(KnowledgeService(get_settings()))
    if not evaluator.chunks:
        raise SystemExit("知识库索引为空，请先写入待评测文档后再生成报告。")

    run = evaluator.run(cases, dataset_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "evaluation_result.json"
    markdown_path = output_dir / "evaluation_report.md"
    json_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(run), encoding="utf-8")

    print(f"评测完成：{run.summary.passed_cases}/{run.summary.total_cases}条通过")
    print(f"JSON结果：{json_path}")
    print(f"Markdown报告：{markdown_path}")


if __name__ == "__main__":
    main()
