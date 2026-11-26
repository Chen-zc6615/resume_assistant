from graph_service.models.extraction import ExtractedTriple


def _norm(text: str) -> str:
    """把任意空白（空格、换行、制表符）压成单个空格。"""
    return " ".join(text.split())


def _is_grounded(card: str, triple: ExtractedTriple) -> bool:
    """原句是卡片的一部分，且名字是原句的一部分。"""
    snippet = _norm(triple.context_snippet)
    name = _norm(triple.tail_name)
    return snippet in card and name in snippet


def verify_triples(
    card_text: str, triples: list[ExtractedTriple]
) -> tuple[list[ExtractedTriple], list[ExtractedTriple]]:
    """返回 (通过核对的, 被丢弃的)，保持输入顺序。"""
    card = _norm(card_text)
    passed: list[ExtractedTriple] = []
    rejected: list[ExtractedTriple] = []
    for t in triples:
        if _is_grounded(card, t):
            passed.append(t)
        else:
            rejected.append(t)
    return passed, rejected
