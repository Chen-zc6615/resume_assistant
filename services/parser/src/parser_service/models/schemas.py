from pydantic import BaseModel


class ParseResponse(BaseModel):
    file_name: str
    text: str
    parse_method: str
    page_count: int
    used_ocr: bool
    effective_chars: int
    warnings: list[str]

