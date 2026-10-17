from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_service.core.config import get_settings
from knowledge_service.models.schemas import DocumentUpsert
from knowledge_service.services.knowledge import KnowledgeService


def parse_args(default_wiki_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量导入候选人Wiki卡片")
    parser.add_argument(
        "--wiki-dir",
        type=Path,
        default=default_wiki_dir,
        help="候选人Wiki Markdown目录",
    )
    return parser.parse_args()


def document_id_from_path(path: Path) -> str:
    """把“张凯_wiki.md”转换为稳定文档ID“张凯”。"""
    return path.stem.removesuffix("_wiki")


def main() -> None:
    settings = get_settings()
    args = parse_args(settings.knowledge_wiki_dir)
    wiki_dir = args.wiki_dir.resolve()
    wiki_files = sorted(wiki_dir.glob("*_wiki.md"))
    if not wiki_files:
        raise SystemExit(f"未在{wiki_dir}找到任何*_wiki.md文件。")

    documents = [
        (path, path.read_text(encoding="utf-8"))
        for path in wiki_files
    ]
    service = KnowledgeService(settings)
    total_chunks = 0

    for path, content in documents:
        document_id = document_id_from_path(path)
        result = service.upsert(
            document_id=document_id,
            document=DocumentUpsert(
                document_type="talent_profile",
                content=content,
                metadata={"source_file": path.name},
            ),
        )
        total_chunks += result.chunk_count
        print(f"已导入：{path.name} -> {result.chunk_count}个切片")

    print(f"批量入库完成：{len(documents)}份文档，共{total_chunks}个切片。")


if __name__ == "__main__":
    main()
