import pytest
from graph_service.models.extraction import ExtractedTriple, ResumeTriple
from graph_service.services.triple_writer import to_triple
from pydantic import ValidationError


def test_triple_inherits_validation():
    # 继承来的校验仍然生效：关系和尾类型不配套要报错
    with pytest.raises(ValidationError):
        ResumeTriple(
            head_id="cand-1",
            relation="HAS_SKILL",
            tail_type="Company",
            tail_name="腾讯",
            context_snippet="x",
        )


def test_triple_head_type_only_candidate():
    with pytest.raises(ValidationError):
        ResumeTriple(
            head_type="Job",
            head_id="j-1",
            relation="HAS_SKILL",
            tail_type="Skill",
            tail_name="Python",
            context_snippet="x",
        )


def test_to_triple_adds_head():
    t = ExtractedTriple(
        relation="HAS_SKILL", tail_type="Skill", tail_name="JS", context_snippet="熟练使用JS"
    )
    triple = to_triple("cand-1", t)
    assert triple.head_id == "cand-1"
    assert triple.head_type == "Candidate"
    assert triple.tail_name == "JS"
