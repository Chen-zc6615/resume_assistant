from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from parser_service.core.config import get_settings
from parser_service.models.schemas import ParseResponse
from parser_service.services.parser import parse_pdf
from parser_service.services.security import FileValidationError

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "healthy", "ocr_model": settings.ocr_model}


@router.post("/api/v1/parse", response_model=ParseResponse)
async def parse(file: UploadFile = File(...)) -> ParseResponse:  # noqa: B008  FastAPI 惯用写法
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    file_name = file.filename or "resume.pdf"
    try:
        result = await run_in_threadpool(parse_pdf, content, settings)
    except FileValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ParseResponse(
        file_name=file_name,
        text=result.text,
        parse_method=result.parse_method,
        page_count=result.page_count,
        used_ocr=result.used_ocr,
        effective_chars=result.effective_chars,
        warnings=result.warnings,
    )

