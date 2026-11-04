from __future__ import annotations

import re
from typing import Any

from knowledge_service.clients.embedding_client import EmbeddingClient
from knowledge_service.clients.reranker_client import RerankerClient
from knowledge_service.core.config import Settings
from knowledge_service.models.schemas import (
    DocumentUpsert,
    DocumentWriteResponse,
    SearchRequest,
    SearchResponse,
    TalentProfileUpsert,
)
from knowledge_service.services.chunker import MarkdownChunker
from knowledge_service.services.retriever import HybridRetriever, RetrievalOutcome
from knowledge_service.services.vector_store import VectorStore
from knowledge_service.services.wiki_card import (
    WikiCard,
    _inline,
    _work_months_label,
    build_talent_wiki_card,
)


def _filter_metadata(profile: TalentProfileUpsert) -> dict[str, Any]:
    """切片层过滤键（metadata_filter 查询依赖）；有事实才输出，不占位不编造。"""

    filters: dict[str, Any] = {}
    gender = None if profile.gender is None else {0: "男", 1: "女"}[profile.gender]
    if gender:
        filters["gender"] = gender
    if profile.highest_education:
        filters["highest_education"] = _inline(profile.highest_education)
    if profile.graduation_institution:
        filters["graduation_institution"] = _inline(profile.graduation_institution)
    if profile.total_work_months is not None:
        filters["total_work_months"] = profile.total_work_months
        filters["total_work_years"] = _work_months_label(profile.total_work_months)
    skills = [_inline(skill) for skill in profile.skills if skill.strip()]
    if skills:
        filters["skills"] = skills
        filters["skill_count"] = len(skills)
    return filters


class KnowledgeService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chunker = MarkdownChunker(
            chunk_size=settings.knowledge_chunk_size,
            chunk_overlap=settings.knowledge_chunk_overlap,
        )
        embeddings = EmbeddingClient(settings)
        store = VectorStore(settings, embeddings)
        self.store = store
        self.retriever = HybridRetriever(
            settings=settings,
            store=store,
            embeddings=embeddings,
            reranker=RerankerClient(settings),
        )

    def upsert(self, talent_card_id: str, document: DocumentUpsert) -> DocumentWriteResponse:
        chunks = self.chunker.split(
            talent_card_id=talent_card_id,
            document_type=document.document_type,
            content=document.content,
            metadata=document.metadata,
        )
        count = self.store.upsert_document(talent_card_id, chunks)
        return DocumentWriteResponse(talent_card_id=talent_card_id, chunk_count=count)

    def upsert_talent_profile(
        self, talent_card_id: str, profile: TalentProfileUpsert
    ) -> DocumentWriteResponse:
        if not re.fullmatch(r"talent-[1-9]\d*", talent_card_id):
            raise ValueError("人才卡片 talent_card_id 必须为 talent-{正整数}")
        card = build_talent_wiki_card(profile)
        self._write_wiki_card(card, profile.name, talent_card_id)
        # 切片层键值全部在此装配（卡片展示层不含）：talent_card_id/
        # document_type 由 chunker 强制写入每个切片；source_resume_id
        # 与过滤键在此补入，供 metadata_filter 精确检索。
        metadata = {
            **card.metadata,
            "source_resume_id": profile.source_resume_id,
            **_filter_metadata(profile),
        }
        return self.upsert(
            talent_card_id,
            DocumentUpsert(
                document_type="talent_profile",
                content=card.content,
                metadata=metadata,
            ),
        )

    def delete(self, talent_card_id: str) -> None:
        self.store.delete_document(talent_card_id)
        self._delete_wiki_card(talent_card_id)

    # ---------------------- Wiki 卡片 Markdown 落盘 ----------------------

    def _write_wiki_card(self, card: WikiCard, name: str, talent_card_id: str) -> None:
        """人才卡片同步落盘一份 Markdown 副本（编号_姓名.md）。

        向量库仍是检索的真理之源；磁盘文件仅供人工阅读与 git 管理，
        写入失败不应阻断同步流程。
        """
        wiki_dir = self.settings.knowledge_data_dir / "wiki"
        safe_name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip() or "未知"
        try:
            wiki_dir.mkdir(parents=True, exist_ok=True)
            (wiki_dir / f"{talent_card_id}_{safe_name}.md").write_text(
                card.content, encoding="utf-8"
            )
        except OSError:
            # 落盘是辅助能力：目录只读/磁盘满等故障不阻断向量化主流程
            pass

    def _delete_wiki_card(self, talent_card_id: str) -> None:
        """移除向量文档时清理对应的 Markdown 副本（与 _write_wiki_card 对称）。"""
        wiki_dir = self.settings.knowledge_data_dir / "wiki"
        if not wiki_dir.is_dir():
            return
        for path in wiki_dir.glob(f"{talent_card_id}_*.md"):
            try:
                path.unlink()
            except OSError:
                pass

    def search(self, request: SearchRequest) -> SearchResponse:
        results, latency = self.retriever.search(query=request.query)
        return SearchResponse(query=request.query, results=results, latency_ms=latency)

    def search_with_diagnostics(self, request: SearchRequest) -> RetrievalOutcome:
        """供离线评估使用；线上接口只返回标准检索响应。"""
        return self.retriever.search_with_diagnostics(query=request.query)
