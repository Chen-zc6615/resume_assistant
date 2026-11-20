import pytest
from graph_service.models.extraction import ResumeTriple
from pydantic import ValidationError


def test_triple_inherits_validation():
    # 继承来的校验仍然生效：关系和尾类型不配套要报错
    with pytest.raises(ValidationError):
        ResumeTriple(
            resume_id=1001,
            relation="HAS_SKILL",
            tail_type="Company",
            tail_name="腾讯",
            context_snippet="x",
        )


def test_triple_head_type_only_candidate():
    with pytest.raises(ValidationError):
        ResumeTriple(
            head_type="Job",
            resume_id=2,
            relation="HAS_SKILL",
            tail_type="Skill",
            tail_name="Python",
            context_snippet="x",
        )
