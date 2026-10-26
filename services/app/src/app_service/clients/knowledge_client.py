"""知识库服务 HTTP 客户端。

主服务只通过此模块调用 ``services/knowledge``，不直接依赖知识库内部实现。
人才资料发送脱敏结构化数据，由知识库生成 Wiki；通用文档也可直接写入。
写入使用 PUT，同一 ``talent_card_id`` 会被覆盖，因而可以安全重试。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app_service.core.config import get_settings
from app_service.core.logger import get_logger

logger = get_logger(__name__)

DocumentType = Literal["talent_profile", "job_doc", "policy", "other"]


class KnowledgeServiceError(RuntimeError):
    """知识库请求失败；上层可记录同步失败并安排重试。"""


@dataclass(frozen=True)
class DocumentWriteResult:
    talent_card_id: str
    chunk_count: int


@dataclass(frozen=True)
class KnowledgeSearchResult:
    chunk_id: str
    document_id: str
    content: str
    metadata: dict[str, Any]
    rerank_score: float


@dataclass(frozen=True)
class KnowledgeSearchResponse:
    query: str
    results: list[KnowledgeSearchResult]
    latency_ms: float


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("detail") if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        detail = None
    return str(detail) if detail else f"HTTP {response.status_code}"


def _timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.knowledge_http_connect_timeout_seconds,
        read=settings.knowledge_http_read_timeout_seconds,
        write=settings.knowledge_http_connect_timeout_seconds,
        pool=settings.knowledge_http_connect_timeout_seconds,
    )


def upsert_document(
    *,
    talent_card_id: str,
    document_type: DocumentType,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> DocumentWriteResult:
    """新增或覆盖已经生成好的通用知识库文档。"""

    if not talent_card_id.strip():
        raise ValueError("talent_card_id 不能为空")
    if not content.strip():
        raise ValueError("content 不能为空")

    body = {
        "document_type": document_type,
        "content": content,
        "metadata": metadata or {},
    }
    return _put(talent_card_id, f"/api/v1/talent-cards/{talent_card_id}", body)


def upsert_talent_profile(
    *, talent_card_id: str, profile: dict[str, Any]
) -> DocumentWriteResult:
    """发送脱敏归一化数据，由 knowledge 服务生成 Wiki 卡片并建立索引。"""

    if not talent_card_id.strip():
        raise ValueError("talent_card_id 不能为空")
    if not profile:
        raise ValueError("profile 不能为空")
    return _put(talent_card_id, f"/api/v1/talent-profiles/{talent_card_id}", profile)


def _put(talent_card_id: str, path: str, body: dict[str, Any]) -> DocumentWriteResult:
    settings = get_settings()
    url = f"{settings.knowledge_service_base_url.rstrip('/')}{path}"
    attempts = settings.knowledge_http_max_retries + 1
    last_error = "知识库服务不可用"

    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=_timeout()) as client:
                response = client.put(url, json=body)
        except httpx.HTTPError as exc:
            last_error = f"知识库服务不可用：{exc}"
            logger.warning(
                "知识库文档写入失败（%s/%s）talent_card_id=%s: %s",
                attempt,
                attempts,
                talent_card_id,
                exc,
            )
        else:
            if response.status_code == 200:
                try:
                    payload = response.json()
                    return DocumentWriteResult(
                        talent_card_id=str(payload["talent_card_id"]),
                        chunk_count=int(payload["chunk_count"]),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise KnowledgeServiceError("知识库返回了无效的写入结果") from exc

            detail = _detail(response)
            if response.status_code < 500:
                raise KnowledgeServiceError(f"知识库拒绝写入文档：{detail}")
            last_error = f"知识库服务不可用：{detail}"
            logger.warning(
                "知识库文档写入返回 %s（%s/%s）talent_card_id=%s",
                response.status_code,
                attempt,
                attempts,
                talent_card_id,
            )

        if attempt < attempts:
            time.sleep(settings.knowledge_http_retry_backoff_seconds)

    raise KnowledgeServiceError(last_error)


def delete_document(talent_card_id: str) -> None:
    """删除知识库文档；连接错误和服务端错误可按配置重试。"""

    if not talent_card_id.strip():
        raise ValueError("talent_card_id 不能为空")

    settings = get_settings()
    url = (
        f"{settings.knowledge_service_base_url.rstrip('/')}"
        f"/api/v1/talent-cards/{talent_card_id}"
    )
    attempts = settings.knowledge_http_max_retries + 1
    last_error = "知识库服务不可用"

    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=_timeout()) as client:
                response = client.delete(url)
        except httpx.HTTPError as exc:
            last_error = f"知识库服务不可用：{exc}"
            logger.warning(
                "知识库文档删除失败（%s/%s）talent_card_id=%s: %s",
                attempt,
                attempts,
                talent_card_id,
                exc,
            )
        else:
            if response.status_code in (204, 404):
                return
            detail = _detail(response)
            if response.status_code < 500:
                raise KnowledgeServiceError(f"知识库拒绝删除文档：{detail}")
            last_error = f"知识库服务不可用：{detail}"
            logger.warning(
                "知识库文档删除返回 %s（%s/%s）talent_card_id=%s",
                response.status_code,
                attempt,
                attempts,
                talent_card_id,
            )

        if attempt < attempts:
            time.sleep(settings.knowledge_http_retry_backoff_seconds)

    raise KnowledgeServiceError(last_error)


<<<<<<< HEAD
def search_documents(
    *,
    query: str,
    document_types: list[DocumentType] | None = None,
    metadata_filter: dict[str, Any] | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """查询知识库并返回受控结果；Agent 用它发现候选人的 resume_id。"""

    if len(query.strip()) < 2:
        raise ValueError("检索词至少需要 2 个字符")
    if not 1 <= top_k <= 20:
        raise ValueError("top_k 必须在 1 到 20 之间")

    settings = get_settings()
    url = f"{settings.knowledge_service_base_url.rstrip('/')}/api/v1/search"
    body = {
        "query": query.strip(),
        "document_types": document_types,
        "metadata_filter": metadata_filter,
        "top_k": top_k,
    }
    attempts = settings.knowledge_http_max_retries + 1
    last_error = "知识库服务不可用"
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=_timeout()) as client:
                response = client.post(url, json=body)
=======
def search(query: str) -> KnowledgeSearchResponse:
    """检索人才知识库；结果供主服务 Agent 组织最终回答。"""

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query 不能为空")

    settings = get_settings()
    url = f"{settings.knowledge_service_base_url.rstrip('/')}/api/v1/search"
    attempts = settings.knowledge_http_max_retries + 1
    last_error = "知识库服务不可用"

    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=_timeout()) as client:
                response = client.post(url, json={"query": normalized_query})
>>>>>>> origin/develop
        except httpx.HTTPError as exc:
            last_error = f"知识库服务不可用：{exc}"
            logger.warning("知识库检索失败（%s/%s）: %s", attempt, attempts, exc)
        else:
            if response.status_code == 200:
                try:
                    payload = response.json()
<<<<<<< HEAD
                    results = payload["results"]
                    if not isinstance(results, list):
                        raise TypeError("results 不是数组")
                    return [item for item in results if isinstance(item, dict)]
                except (KeyError, TypeError, ValueError) as exc:
                    raise KnowledgeServiceError("知识库返回了无效的检索结果") from exc
            detail = _detail(response)
            if response.status_code < 500 and response.status_code != 429:
                raise KnowledgeServiceError(f"知识库检索失败：{detail}")
            last_error = f"知识库服务不可用：{detail}"
            logger.warning("知识库检索返回 %s（%s/%s）", response.status_code, attempt, attempts)
        if attempt < attempts:
            time.sleep(settings.knowledge_http_retry_backoff_seconds * attempt)
=======
                    results = [
                        KnowledgeSearchResult(
                            chunk_id=str(item["chunk_id"]),
                            document_id=str(item["document_id"]),
                            content=str(item["content"]),
                            metadata=dict(item.get("metadata") or {}),
                            rerank_score=float(item["rerank_score"]),
                        )
                        for item in payload["results"]
                    ]
                    return KnowledgeSearchResponse(
                        query=str(payload["query"]),
                        results=results,
                        latency_ms=float(payload["latency_ms"]),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise KnowledgeServiceError("知识库返回了无效的检索结果") from exc

            detail = _detail(response)
            if response.status_code < 500:
                raise KnowledgeServiceError(f"知识库拒绝检索：{detail}")
            last_error = f"知识库服务不可用：{detail}"
            logger.warning(
                "知识库检索返回 %s（%s/%s）",
                response.status_code,
                attempt,
                attempts,
            )

        if attempt < attempts:
            time.sleep(settings.knowledge_http_retry_backoff_seconds)

>>>>>>> origin/develop
    raise KnowledgeServiceError(last_error)
