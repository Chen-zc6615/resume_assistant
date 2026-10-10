"""诊断脚本：校验并解析单个 PDF，输出各阶段结果。

用法：python .agents/skills/resume-parse-spec/scripts/check_pdf.py <pdf路径>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from src.core.security import FileValidationError, validate_upload
from src.services.parse_service import effective_chars, extract_with_pdfplumber, extract_with_pymupdf


def main(pdf: str) -> None:
    content = Path(pdf).read_bytes()
    try:
        validate_upload(content)
        print("[1] 上传校验：通过")
    except FileValidationError as e:
        print(f"[1] 上传校验：拒绝 —— {e.reason}")
        return

    t1 = extract_with_pymupdf(Path(pdf))
    print(f"[2] PyMuPDF：有效字符 {effective_chars(t1)}")
    t2 = extract_with_pdfplumber(Path(pdf))
    print(f"[3] pdfplumber：有效字符 {effective_chars(t2)}")
    if effective_chars(t1) < 50 and effective_chars(t2) < 50:
        print("[4] 判定：扫描件/图片型，需走 OCR 链路（qwen-vl-max）")
    else:
        print("[4] 判定：文本型，解析成功")


if __name__ == "__main__":
    main(sys.argv[1])
