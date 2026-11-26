from graph_service.models.extraction import ExtractedTriple
from graph_service.services.triple_verifier import verify_triples

# 模拟一张卡片的正文（与真实卡片的渲染格式一致：空白已压成单个空格）
CARD = (
    "## 专业技能\n\n- Python\n- Redis\n\n"
    "## 工作经历\n\n### 腾讯 · 后端工程师\n- 工作内容：负责支付系统开发"
)


def _skill(name, snippet):
    return ExtractedTriple(
        relation="HAS_SKILL", tail_type="Skill", tail_name=name, context_snippet=snippet
    )


def _company(name, snippet):
    return ExtractedTriple(
        relation="WORKED_AT", tail_type="Company", tail_name=name, context_snippet=snippet
    )


def test_passes_when_snippet_and_name_in_card():
    t = _skill("Python", "- Python")
    passed, rejected = verify_triples(CARD, [t])
    assert passed == [t]
    assert rejected == []


def test_rejects_when_snippet_not_in_card():
    # 卡片里根本没有 Java，LLM 编造了这句话
    t = _skill("Java", "- Java")
    passed, rejected = verify_triples(CARD, [t])
    assert passed == []
    assert rejected == [t]


def test_rejects_when_name_not_in_snippet():
    # 原句真实存在，但 tail_name 填的是原句里没有的东西
    t = _skill("Go", "- Python")
    passed, rejected = verify_triples(CARD, [t])
    assert passed == []
    assert rejected == [t]


def test_passes_when_only_whitespace_differs():
    # 卡片里是「腾讯 · 后端工程师」（单个空格），LLM 返回时多打了空格
    t = _company("腾讯", "腾讯  ·  后端工程师")
    passed, rejected = verify_triples(CARD, [t])
    assert passed == [t]
    assert rejected == []


def test_passes_when_name_is_only_part_of_snippet():
    # 规则是「包含」不是「相等」：名字「腾讯」只是原句「腾讯 · 后端工程师」的一部分
    t = _company("腾讯", "腾讯 · 后端工程师")
    passed, rejected = verify_triples(CARD, [t])
    assert passed == [t]
    assert rejected == []


def test_rejects_when_snippet_is_paraphrased():
    # LLM 概括改写的句子不是原文，无法证明没有编造，宁可丢弃
    t = _company("腾讯", "在腾讯做后端")
    passed, rejected = verify_triples(CARD, [t])
    assert passed == []
    assert rejected == [t]


def test_name_match_is_case_sensitive():
    # tail_name「不得改写」，大小写不同也算改写
    t = _skill("python", "- Python")
    passed, rejected = verify_triples(CARD, [t])
    assert passed == []
    assert rejected == [t]


def test_mixed_batch_splits_into_passed_and_rejected():
    ok = _skill("Redis", "- Redis")
    fake = _skill("Java", "- Java")
    passed, rejected = verify_triples(CARD, [ok, fake])
    assert passed == [ok]
    assert rejected == [fake]


def test_empty_input():
    assert verify_triples(CARD, []) == ([], [])
