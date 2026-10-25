from __future__ import annotations

import re

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
from knowledge_service.services.wiki_card import WikiCard, build_talent_wiki_card


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

    def upsert(self, document_id: str, document: DocumentUpsert) -> DocumentWriteResponse:
        chunks = self.chunker.split(
            document_id=document_id,
            document_type=document.document_type,
            content=document.content,
            metadata=document.metadata,
        )
        count = self.store.upsert_document(document_id, chunks)
        return DocumentWriteResponse(document_id=document_id, chunk_count=count)

    def upsert_talent_profile(
        self, document_id: str, profile: TalentProfileUpsert
    ) -> DocumentWriteResponse:
        card = build_talent_wiki_card(document_id, profile)
        self._write_wiki_card(card, profile.name)
        return self.upsert(
            document_id,
            DocumentUpsert(
                document_type="talent_profile",
                content=card.content,
                metadata=card.metadata,
            ),
        )

    def delete(self, document_id: str) -> None:
        self.store.delete_document(document_id)
        self._delete_wiki_card(document_id)

    # ---------------------- Wiki 卡片 Markdown 落盘 ----------------------

    def _write_wiki_card(self, card: WikiCard, name: str) -> None:
        """人才卡片同步落盘一份 Markdown 副本（编号_姓名.md）。

        向量库仍是检索的真理之源；磁盘文件仅供人工阅读与 git 管理，
        写入失败不应阻断同步流程。
        """
        wiki_dir = self.settings.knowledge_data_dir / "wiki"
        safe_name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip() or "未知"
        try:
            wiki_dir.mkdir(parents=True, exist_ok=True)
            (wiki_dir / f"{card.document_id}_{safe_name}.md").write_text(
                card.content, encoding="utf-8"
            )
        except OSError:
            # 落盘是辅助能力：目录只读/磁盘满等故障不阻断向量化主流程
            pass

    def _delete_wiki_card(self, document_id: str) -> None:
        """移除向量文档时清理对应的 Markdown 副本（与 _write_wiki_card 对称）。"""
        wiki_dir = self.settings.knowledge_data_dir / "wiki"
        if not wiki_dir.is_dir():
            return
        for path in wiki_dir.glob(f"{document_id}_*.md"):
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
