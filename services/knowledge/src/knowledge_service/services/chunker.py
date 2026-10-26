import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    content: str
    metadata: dict[str, Any]


class MarkdownChunker:
    """按 Markdown 标题分段，并对长段落执行带重叠的字符切块。"""

    def __init__(self, chunk_size: int = 550, chunk_overlap: int = 80):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @staticmethod
    def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not match:
            return {}, text
        metadata = yaml.safe_load(match.group(1)) or {}
        if not isinstance(metadata, dict):
            raise TypeError("YAML Frontmatter 必须是对象")
        return metadata, text[match.end() :]

    @staticmethod
    def _sections(text: str) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        headings: dict[int, str] = {}
        body: list[str] = []

        def flush() -> None:
            content = "\n".join(body).strip()
            if content:
                breadcrumb = " > ".join(headings[level] for level in sorted(headings))
                sections.append((breadcrumb, content))
            body.clear()

        for line in text.splitlines():
            match = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
            if match:
                flush()
                level = len(match.group(1))
                headings[level] = match.group(2)
                for deeper in tuple(key for key in headings if key > level):
                    del headings[deeper]
                body.append(line)
            else:
                body.append(line)
        flush()
        return sections or [("", text.strip())]

    def _split_long_text(self, text: str) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            if end < len(text):
                boundary = max(
                    text.rfind(separator, start, end)
                    for separator in ("\n\n", "\n", "。", "；", " ")
                )
                if boundary > start + self.chunk_size // 2:
                    end = boundary + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    def split(
        self,
        talent_card_id: str,
        document_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        frontmatter, body = self._frontmatter(content)
        base_metadata = {**frontmatter, **(metadata or {})}
        chunks: list[Chunk] = []

        for section, section_text in self._sections(body):
            for part in self._split_long_text(section_text):
                index = len(chunks)
                digest = hashlib.sha256(f"{talent_card_id}:{index}".encode()).hexdigest()[:16]
                chunk_metadata = {
                    **base_metadata,
                    "talent_card_id": talent_card_id,
                    "document_type": document_type,
                    "section": section or "正文",
                    "chunk_index": index,
                }
                chunks.append(
                    Chunk(
                        chunk_id=f"{talent_card_id}:{digest}",
                        content=part,
                        metadata=chunk_metadata,
                    )
                )
        if not chunks:
            raise ValueError("文档正文为空，无法建立索引")
        return chunks


def chroma_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """将复合元数据转换为 Chroma 支持的基础类型。"""
    result: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[key] = value
        else:
            result[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return result

